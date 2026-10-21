#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Analysis recipes over the local Search Console archive (run gsc_pull.py first).

Usage:
  gsc_recipes.py RECIPE [--site S] [--days 28] [--end YYYY-MM-DD] [--limit 50]
                 [--format table|json|csv] [--include-brand] [--date YYYY-MM-DD]

Recipes:
  coverage        what the archive holds; share of clicks the query rows explain
  striking        query+page at avg position 5-20 with enough impressions (non-brand)
  ctr_gap         query+page in the top 10 getting < 80% of the clicks our own CTR curve expects
  cannibal        queries where 2+ pages of the same locale each take >= 20% of impressions
  decay           pages whose clicks fell >= 20% vs the previous window, with the reason
  new_queries     queries seen in the window but not in the 84 days before it
  page_map        per page: top queries, query count, share of the page's clicks from its top query
  brand           weekly clicks/impressions: brand, ambiguous, non-brand, hidden (anonymized)
  countries       country totals now vs previous window, with the writing system of queries
  devices         device totals now vs previous window
  questions       question queries (EN/ES/PT/FR/DE/ID/AR) grouped by landing page
  update_impact   pages before vs after --date (equal windows, the week after --date skipped)

Windows: the current window is the last --days complete (final) days ending at --end or at the
last final day in the archive; the previous window is the same length right before it.
All thresholds are starting heuristics, not Google rules; change them with flags.
"""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import json
import os
import sqlite3
import sys
from collections import defaultdict

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import seoconf  # noqa: E402

GENERIC_CTR = {1: .25, 2: .13, 3: .08, 4: .055, 5: .04, 6: .03, 7: .024, 8: .02, 9: .017, 10: .015}


# ---------- windows and helpers ----------

def windows(con, days: int, end: str | None):
    if not end:
        end = con.execute("SELECT MAX(date) FROM pull_log WHERE final=1").fetchone()[0]
        if not end:
            sys.exit("Archive is empty. Run gsc_pull.py first.")
    e = dt.date.fromisoformat(end)
    cur = ((e - dt.timedelta(days - 1)).isoformat(), e.isoformat())
    ps = e - dt.timedelta(days)
    prev = ((ps - dt.timedelta(days - 1)).isoformat(), ps.isoformat())
    require_final(con, cur, "current window")
    return cur, prev


def require_final(con, w, what="window"):
    """Stop unless every day in w=(start, end) is in the archive and final (R69F-02)."""
    s, e = dt.date.fromisoformat(w[0]), dt.date.fromisoformat(w[1])
    need = (e - s).days + 1
    have = con.execute("SELECT COUNT(*) FROM pull_log WHERE final=1 AND date BETWEEN ? AND ?", w).fetchone()[0]
    if have < need:
        bad = [d for (d,) in con.execute("SELECT date FROM pull_log WHERE final=0 AND date BETWEEN ? AND ?", w)]
        sys.exit(f"The {what} {w[0]}..{w[1]} has {have}/{need} final days (provisional: {bad[:5]}; the rest missing). "
                 "Run gsc_pull.py, or pick --end/--days inside the final archive.")


def qp(con, w, by="query, page"):
    return con.execute(f"""SELECT {by}, SUM(clicks), SUM(impressions), SUM(pos_x_impr)/SUM(impressions)
                           FROM query_daily WHERE date BETWEEN ? AND ? GROUP BY {by}""", w).fetchall()


def pct(a, b):
    return None if not b else round(100.0 * (a - b) / b, 1)


def ctr_curve(con, end: str, brand) -> tuple[dict, str]:
    """Own CTR by rounded position (1-20) over 90 days of non-brand query rows."""
    s = (dt.date.fromisoformat(end) - dt.timedelta(89)).isoformat()
    agg = defaultdict(lambda: [0, 0])
    n_final = con.execute("SELECT COUNT(*) FROM pull_log WHERE final=1 AND date BETWEEN ? AND ?", (s, end)).fetchone()[0]
    # train only on final days (RA35-02)
    for q, c, i, pos in con.execute("""SELECT query, SUM(clicks), SUM(impressions), SUM(pos_x_impr)/SUM(impressions)
                                       FROM query_daily WHERE date BETWEEN ? AND ?
                                         AND date IN (SELECT date FROM pull_log WHERE final=1)
                                       GROUP BY query, page""", (s, end)):
        if brand(q) != "non-brand":
            continue
        b = min(20, max(1, round(pos)))
        agg[b][0] += c
        agg[b][1] += i
    curve, src = {}, f"own data, {n_final}/90 final days, non-brand"
    for b in range(1, 21):
        c, i = agg.get(b, [0, 0])
        if i >= 500:
            curve[b] = c / i
    if len(curve) < 5:
        return {b: GENERIC_CTR.get(b, .01 if b <= 15 else .005) for b in range(1, 21)}, "generic fallback (too little own data)"
    observed = dict(curve)  # fill gaps only from buckets with real data, never from filled ones (R69F-04)
    for b in range(1, 21):
        if b not in observed:
            curve[b] = observed[min(observed, key=lambda k: (abs(k - b), k))]
    return curve, src


# ---------- recipes ----------

def r_coverage(con, a, cfg, brand):
    cur, _ = windows(con, a.days, a.end)
    span = con.execute("SELECT MIN(date), MAX(date), COUNT(*), SUM(final), SUM(query_truncated) FROM pull_log").fetchone()
    site = con.execute("SELECT SUM(clicks), SUM(impressions) FROM site_daily WHERE date BETWEEN ? AND ?", cur).fetchone()
    q = con.execute("SELECT SUM(clicks), SUM(impressions) FROM query_daily WHERE date BETWEEN ? AND ?", cur).fetchone()
    return [{"archive_from": span[0], "archive_to": span[1], "days": span[2], "final_days": span[3],
             "truncated_days": span[4], "window": f"{cur[0]}..{cur[1]}", "site_clicks": site[0],
             "site_impressions": site[1], "query_rows_clicks": q[0], "query_rows_impressions": q[1],
             "click_coverage_pct": round(100 * (q[0] or 0) / (site[0] or 1), 1),
             "impression_coverage_pct": round(100 * (q[1] or 0) / (site[1] or 1), 1)}]


def r_striking(con, a, cfg, brand):
    cur, _ = windows(con, a.days, a.end)
    curve, src = ctr_curve(con, cur[1], brand)
    min_impr = a.min_impr or round(100 * a.days / 28)
    out = []
    for q, p, c, i, pos in qp(con, cur):
        cls = brand(q)
        if (cls != "non-brand" and not a.include_brand) or not (5 <= pos <= 20) or i < min_impr:
            continue
        target = curve[3]  # what the pair would get at position ~3
        out.append({"query": q, "page": p, "clicks": c, "impressions": i, "ctr_pct": round(100 * c / i, 2),
                    "position": round(pos, 1), "script": seoconf.script_of(q), "brand": cls,
                    "potential_clicks": round(max(0, i * target - c))})
    out.sort(key=lambda r: -r["potential_clicks"])
    return out, f"window {cur[0]}..{cur[1]}; potential = impressions x own CTR at position 3 ({src}) - clicks"


def r_ctr_gap(con, a, cfg, brand):
    cur, _ = windows(con, a.days, a.end)
    curve, src = ctr_curve(con, cur[1], brand)
    min_impr = a.min_impr or round(100 * a.days / 28)
    out = []
    for q, p, c, i, pos in qp(con, cur):
        cls = brand(q)
        if (cls != "non-brand" and not a.include_brand) or pos > 10 or i < min_impr:
            continue
        exp = i * curve[min(20, max(1, round(pos)))]
        if c < 0.8 * exp:
            out.append({"query": q, "page": p, "clicks": c, "expected_clicks": round(exp, 1), "impressions": i,
                        "position": round(pos, 1), "ctr_pct": round(100 * c / i, 2),
                        "gap_clicks": round(exp - c, 1), "script": seoconf.script_of(q)})
    out.sort(key=lambda r: -r["gap_clicks"])
    return out, f"window {cur[0]}..{cur[1]}; expected CTR from {src}; flagged when clicks < 80% of expected"


def r_cannibal(con, a, cfg, brand):
    cur, _ = windows(con, a.days, a.end)
    locales = cfg["site"].get("locales", [])
    groups = defaultdict(list)
    for q, p, c, i, pos in qp(con, cur):
        if brand(q) != "non-brand" and not a.include_brand:
            continue
        groups[(q, seoconf.locale_of(p, locales))].append((p, c, i, pos))
    # day-level switching: how many distinct top pages a query had across days
    daily = defaultdict(lambda: defaultdict(int))
    for q, d, p, i in con.execute("""SELECT query, date, page, SUM(impressions) FROM query_daily
                                     WHERE date BETWEEN ? AND ? GROUP BY query, date, page""", cur):
        daily[(q, seoconf.locale_of(p, locales), d)][p] += i
    tops = defaultdict(set)  # distinct daily leaders within the same locale (R69F-05)
    for (q, loc, d), pages in daily.items():
        tops[(q, loc)].add(max(pages, key=pages.get))
    min_impr = a.min_impr or round(50 * a.days / 28)
    out = []
    for (q, loc), rows in groups.items():
        tot = sum(r[2] for r in rows)
        big = [r for r in rows if r[2] >= 0.2 * tot]
        if len(big) >= 2 and tot >= min_impr:
            big.sort(key=lambda r: -r[2])
            out.append({"query": q, "locale": loc, "impressions": tot, "clicks": sum(r[1] for r in rows),
                        "pages": " | ".join(f"{r[0]} ({round(100 * r[2] / tot)}% impr, pos {round(r[3], 1)})" for r in big),
                        "top_page_switches": len(tops.get((q, loc), ()))})
    out.sort(key=lambda r: -r["impressions"])
    return out, ("same-locale pages only (different /xx/ locales are legitimate); "
                 "a candidate is not proof of harm, inspect intent before merging")


def r_decay(con, a, cfg, brand):
    cur, prev = windows(con, a.days, a.end)
    require_final(con, prev, "comparison window")
    rows = {}
    for w, key in ((cur, "c"), (prev, "p")):
        for p, c, i, px in con.execute("""SELECT page, SUM(clicks), SUM(impressions), SUM(pos_x_impr)
                                          FROM page_daily WHERE date BETWEEN ? AND ? GROUP BY page""", w):
            rows.setdefault(p, {})[key] = (c, i, px / i if i else None)
    min_prev = a.min_clicks or max(5, round(20 * a.days / 28))
    out = []
    for p, d in rows.items():
        pc, pi, ppos = d.get("p", (0, 0, None))
        cc, ci, cpos = d.get("c", (0, 0, None))
        if pc < min_prev or cc > 0.8 * pc:
            continue
        reasons = []
        if pi and ci < 0.8 * pi:
            reasons.append("fewer impressions")
        if ppos and cpos and cpos - ppos >= 1:
            reasons.append("lower position")
        if pi and ci and (cc / ci) < 0.8 * (pc / pi):
            reasons.append("lower CTR")
        out.append({"page": p, "clicks_prev": pc, "clicks_now": cc, "clicks_change_pct": pct(cc, pc),
                    "impr_prev": pi, "impr_now": ci, "pos_prev": round(ppos, 1) if ppos else None,
                    "pos_now": round(cpos, 1) if cpos else None, "reason": ", ".join(reasons) or "mixed"})
    out.sort(key=lambda r: r["clicks_now"] - r["clicks_prev"])
    return out, f"{cur[0]}..{cur[1]} vs {prev[0]}..{prev[1]}; check technical changes and query mix before refreshing"


def r_new_queries(con, a, cfg, brand):
    cur, _ = windows(con, a.days, a.end)
    base_start = (dt.date.fromisoformat(cur[0]) - dt.timedelta(84)).isoformat()
    base_end = (dt.date.fromisoformat(cur[0]) - dt.timedelta(1)).isoformat()
    require_final(con, (base_start, base_end), "84-day baseline")
    seen = {r[0] for r in con.execute("SELECT DISTINCT query FROM query_daily WHERE date BETWEEN ? AND ?",
                                      (base_start, base_end))}
    min_impr = a.min_impr or 20
    agg = defaultdict(lambda: [0, 0, 0.0, defaultdict(int)])
    for q, p, c, i, pos in qp(con, cur):
        if q in seen or (brand(q) != "non-brand" and not a.include_brand):
            continue
        g = agg[q]
        g[0] += c
        g[1] += i
        g[2] += pos * i
        g[3][p] += i
    out = [{"query": q, "clicks": g[0], "impressions": g[1], "position": round(g[2] / g[1], 1),
            "top_page": max(g[3], key=g[3].get), "script": seoconf.script_of(q)}
           for q, g in agg.items() if g[1] >= min_impr]
    out.sort(key=lambda r: -r["impressions"])
    note = f"not seen {base_start}..{base_end}; 'newly observed' is not the same as new demand"
    return out, note


def r_page_map(con, a, cfg, brand):
    cur, _ = windows(con, a.days, a.end)
    per = defaultdict(list)
    for q, p, c, i, pos in qp(con, cur):
        per[p].append((q, c, i, pos))
    pages = {p: (c, i) for p, c, i in con.execute(
        "SELECT page, SUM(clicks), SUM(impressions) FROM page_daily WHERE date BETWEEN ? AND ? GROUP BY page", cur)}
    out = []
    for p, (c, i) in pages.items():
        qs = sorted(per.get(p, []), key=lambda r: -r[2])
        out.append({"page": p, "clicks": c, "impressions": i, "queries": len(qs),
                    "top_queries": "; ".join(f"{q} ({qi})" for q, _, qi, _ in qs[:5]),
                    "clicks_without_query_pct": round(100 * (c - sum(r[1] for r in qs)) / c, 1) if c else None})
    out.sort(key=lambda r: -r["clicks"])
    return out, f"window {cur[0]}..{cur[1]}; clicks_without_query = anonymized queries for that page"


def r_brand(con, a, cfg, brand):
    cur, _ = windows(con, a.days, a.end)
    end = dt.date.fromisoformat(cur[1])
    start = (end - dt.timedelta(days=a.days * 4 - 1)).isoformat()
    w = (start, cur[1])
    wk = lambda d: "{0}-W{1:02d}".format(*dt.date.fromisoformat(d).isocalendar()[:2])  # noqa: E731
    final = {d for (d,) in con.execute("SELECT date FROM pull_log WHERE final=1 AND date BETWEEN ? AND ?", w)}
    weeks = defaultdict(lambda: defaultdict(lambda: [0, 0]))
    site = defaultdict(lambda: [0, 0])
    days = defaultdict(int)
    for d, c, i in con.execute("SELECT date, clicks, impressions FROM site_daily WHERE date BETWEEN ? AND ?", w):
        if d in final:
            site[wk(d)][0] += c
            site[wk(d)][1] += i
            days[wk(d)] += 1
    for d, q, c, i in con.execute("SELECT date, query, SUM(clicks), SUM(impressions) FROM query_daily "
                                  "WHERE date BETWEEN ? AND ? GROUP BY date, query", w):
        if d in final:
            v = weeks[wk(d)][brand(q)]
            v[0] += c
            v[1] += i
    out = []
    for k in sorted(set(site) | set(weeks)):  # a week with only hidden queries still appears (R69F-03)
        known = sum(v[0] for v in weeks[k].values())
        row = {"week": k, "days": days[k], "site_clicks": site[k][0]}
        for cls in ("brand", "ambiguous", "non-brand"):
            row[f"{cls}_clicks"] = weeks[k][cls][0]
            row[f"{cls}_impr"] = weeks[k][cls][1]
        row["hidden_clicks"] = site[k][0] - known
        out.append(row)
    return out, f"{start}..{cur[1]}, final days only; hidden = site total minus clicks on query rows; days<7 = partial week"


def _final(con, w):
    need = (dt.date.fromisoformat(w[1]) - dt.date.fromisoformat(w[0])).days + 1
    return con.execute("SELECT COUNT(*) FROM pull_log WHERE final=1 AND date BETWEEN ? AND ?", w).fetchone()[0] == need


def _dim(con, a, col):
    cur, prev = windows(con, a.days, a.end)
    res = {}
    # an incomplete comparison window withholds the changes but keeps current totals (RA35-03)
    for w, key in ((cur, "now"),) + (((prev, "prev"),) if _final(con, prev) else ()):
        for v, c, i, px in con.execute(f"""SELECT {col}, SUM(clicks), SUM(impressions), SUM(pos_x_impr)
                                           FROM query_daily WHERE date BETWEEN ? AND ? GROUP BY {col}""", w):
            res.setdefault(v, {})[key] = (c, i, px / i if i else None)
    return res, cur, prev


def r_countries(con, a, cfg, brand):
    res, cur, prev = _dim(con, a, "country")
    scripts = defaultdict(lambda: defaultdict(int))
    for co, q, i in con.execute("""SELECT country, query, SUM(impressions) FROM query_daily
                                   WHERE date BETWEEN ? AND ? GROUP BY country, query""", cur):
        scripts[co][seoconf.script_of(q)] += i
    out = []
    for co, d in res.items():
        c, i, pos = d.get("now", (0, 0, None))
        pc, pi, _ = d.get("prev", (0, 0, None))  # absent from a complete baseline = 0
        sc = scripts.get(co, {})
        tot = sum(sc.values()) or 1
        if not _final(con, prev):  # unknown only when the baseline window is incomplete (R958-08)
            pc = pi = None
        out.append({"country": co, "clicks": c, "clicks_prev": pc, "clicks_change_pct": pct(c, pc) if pc is not None else None,
                    "impressions": i, "impr_change_pct": pct(i, pi) if pi is not None else None, "ctr_pct": round(100 * c / i, 2) if i else None,
                    "position": round(pos, 1) if pos else None,
                    "query_scripts": ", ".join(f"{k} {round(100 * v / tot)}%" for k, v in
                                               sorted(sc.items(), key=lambda x: -x[1])[:3])})
    out.sort(key=lambda r: -r["clicks"])
    cmp = f"vs {prev[0]}..{prev[1]}" if _final(con, prev) else "comparison unavailable (previous window not final)"
    return out, f"query rows only (anonymized queries excluded); {cur[0]}..{cur[1]} {cmp}"


def r_devices(con, a, cfg, brand):
    res, cur, prev = _dim(con, a, "device")
    out = []
    for dv, d in res.items():
        c, i, pos = d.get("now", (0, 0, None))
        pc, pi, ppos = d.get("prev", (0, 0, None) if _final(con, prev) else (None, None, None))
        out.append({"device": dv, "clicks": c, "clicks_change_pct": pct(c, pc) if pc is not None else None, "impressions": i,
                    "impr_change_pct": pct(i, pi) if pi is not None else None, "ctr_pct": round(100 * c / i, 2) if i else None,
                    "position": round(pos, 1) if pos else None, "position_prev": round(ppos, 1) if ppos else None})
    out.sort(key=lambda r: -r["clicks"])
    cmp = f"vs {prev[0]}..{prev[1]}" if _final(con, prev) else "comparison unavailable (previous window not final)"
    return out, f"query rows only; {cur[0]}..{cur[1]} {cmp}"


def r_questions(con, a, cfg, brand):
    cur, _ = windows(con, a.days, a.end)
    min_impr = a.min_impr or max(3, round(10 * a.days / 28))
    out = []
    for q, p, c, i, pos in qp(con, cur):
        if i >= min_impr and seoconf.QUESTION_RX.search(q) and (brand(q) == "non-brand" or a.include_brand):
            out.append({"page": p, "query": q, "clicks": c, "impressions": i, "position": round(pos, 1)})
    out.sort(key=lambda r: -r["impressions"])
    return out, "answer these on the matching page; do not create a thin page per phrasing"


def r_update_impact(con, a, cfg, brand):
    if not a.date:
        sys.exit("update_impact needs --date (the rollout end date or the change date)")
    d0 = dt.date.fromisoformat(a.date)
    before = ((d0 - dt.timedelta(a.days)).isoformat(), (d0 - dt.timedelta(1)).isoformat())
    a_start = d0 + dt.timedelta(7)  # skip the first week after the date
    after = (a_start.isoformat(), (a_start + dt.timedelta(a.days - 1)).isoformat())
    require_final(con, before, "window before the date")
    require_final(con, after, "window after the date")
    rows = {}
    for w, key in ((before, "b"), (after, "a")):
        for p, c, i, px in con.execute("""SELECT page, SUM(clicks), SUM(impressions), SUM(pos_x_impr)
                                          FROM page_daily WHERE date BETWEEN ? AND ? GROUP BY page""", w):
            rows.setdefault(p, {})[key] = (c, i, px / i if i else None)
    out = []
    for p, d in rows.items():
        bc, bi, bp = d.get("b", (0, 0, None))
        ac, ai, ap_ = d.get("a", (0, 0, None))
        if max(bc, ac) < 5:
            continue
        out.append({"page": p, "clicks_before": bc, "clicks_after": ac, "change": ac - bc,
                    "change_pct": pct(ac, bc), "pos_before": round(bp, 1) if bp else None,
                    "pos_after": round(ap_, 1) if ap_ else None})
    out.sort(key=lambda r: r["change"])
    return out, f"before {before[0]}..{before[1]}, after {after[0]}..{after[1]} (first week after the date skipped)"


RECIPES = {k[2:]: v for k, v in globals().items() if k.startswith("r_")}


def emit(rows, note, fmt, limit):
    if isinstance(rows, tuple):
        rows, note = rows
    rows = rows[:limit] if limit else rows
    if fmt == "json":
        print(json.dumps({"note": note, "rows": rows}, ensure_ascii=False, indent=1))
        return
    if not rows:
        print(f"(no rows) {note or ''}")
        return
    cols = list(rows[0].keys())
    if fmt == "csv":
        w = csv.DictWriter(sys.stdout, fieldnames=cols)
        w.writeheader()
        w.writerows(rows)
    else:
        print("\t".join(cols))
        for r in rows:
            print("\t".join("" if r[c] is None else str(r[c]) for c in cols))
    if note:
        print(f"\n# {note}", file=sys.stderr)


def run(name: str, cfg: dict, **kw):
    """Programmatic entry for gsc_report.py: returns (rows, note)."""
    ns = argparse.Namespace(days=28, end=None, limit=None, include_brand=False, date=None,
                            min_impr=None, min_clicks=None)
    for k, v in kw.items():
        setattr(ns, k, v)
    from gsc_pull import connect
    res = RECIPES[name](connect(cfg), ns, cfg, seoconf.BrandClassifier(cfg))
    return res if isinstance(res, tuple) else (res, "")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("recipe", choices=sorted(RECIPES))
    ap.add_argument("--site")
    ap.add_argument("--days", type=int, default=28)
    ap.add_argument("--end")
    ap.add_argument("--limit", type=int, default=50)
    ap.add_argument("--format", default="table", choices=["table", "json", "csv"])
    ap.add_argument("--include-brand", action="store_true")
    ap.add_argument("--date")
    ap.add_argument("--min-impr", type=int)
    ap.add_argument("--min-clicks", type=int)
    a = ap.parse_args()
    cfg = seoconf.load(a.site)
    from gsc_pull import connect
    emit(RECIPES[a.recipe](connect(cfg), a, cfg, seoconf.BrandClassifier(cfg)), "", a.format, a.limit)


if __name__ == "__main__":
    main()
