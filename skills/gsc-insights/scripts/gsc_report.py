#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = ["google-auth>=2.30", "requests>=2.31"]
# ///
"""Weekly Search Console report: Markdown + Slack text + Google Sheet tabs.

Usage:
  gsc_report.py [--site S] [--week 2026-W41] [--no-sheet] [--no-conversions]

The week is ISO (Mon-Sun, GSC dates are US Pacific). Default: the last week whose 7 days are all
final in the archive. Run gsc_pull.py first. Outputs go to <data dir>/reports/<week>.{md,json,slack.txt}.
If [report].sheet_id is set, the 'Weekly' tab gets one row per week and the detail tabs are
overwritten with the current lists. If SLACK_WEBHOOK_URL is set, the Slack text is posted;
otherwise the caller (Claude with a Slack connector) posts the .slack.txt content.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import seoconf  # noqa: E402
from gsc_pull import connect  # noqa: E402
from gsc_recipes import run as _run, pct  # noqa: E402


def run(name, cfg, **kw):
    """A recipe whose window is not final becomes an 'unavailable' section instead of aborting the report."""
    try:
        return _run(name, cfg, **kw)
    except SystemExit as e:
        return [], f"unavailable: {e}"


def final_days(con, s, e) -> int:
    return con.execute("SELECT COUNT(*) FROM pull_log WHERE final=1 AND date BETWEEN ? AND ?", (s, e)).fetchone()[0]


def pick_week(con, week: str | None) -> tuple[str, str, str]:
    if week:
        y, w = week.split("-W")
        mon = dt.date.fromisocalendar(int(y), int(w), 1)
        sun = mon + dt.timedelta(6)
        n = final_days(con, mon.isoformat(), sun.isoformat())
        if n < 7:
            sys.exit(f"Week {week} ({mon}..{sun}) has only {n}/7 final days. Run gsc_pull.py or pick an earlier week.")
    else:
        last = con.execute("SELECT MAX(date) FROM pull_log WHERE final=1").fetchone()[0]
        if not last:
            sys.exit("Archive is empty. Run gsc_pull.py first.")
        last = dt.date.fromisoformat(last)
        mon = last - dt.timedelta(days=last.weekday())
        for _ in range(104):  # newest ISO week whose 7 days are all final (R69F-08)
            if final_days(con, mon.isoformat(), (mon + dt.timedelta(6)).isoformat()) == 7:
                break
            mon -= dt.timedelta(7)
        else:
            sys.exit("No complete (7 final days) week in the last two years of the archive.")
        sun = mon + dt.timedelta(6)
    iso = mon.isocalendar()
    return f"{iso.year}-W{iso.week:02d}", mon.isoformat(), sun.isoformat()


def totals(con, s, e):
    """Totals for s..e, or None values with complete=False when any day is missing or provisional (R69F-09)."""
    need = (dt.date.fromisoformat(e) - dt.date.fromisoformat(s)).days + 1
    if final_days(con, s, e) < need:
        return {"clicks": None, "impressions": None, "ctr_pct": None, "position": None, "complete": False}
    c, i, px = con.execute("SELECT SUM(clicks), SUM(impressions), SUM(pos_x_impr) FROM site_daily "
                           "WHERE date BETWEEN ? AND ?", (s, e)).fetchone()
    return {"clicks": c or 0, "impressions": i or 0, "ctr_pct": round(100 * c / i, 2) if i else None,
            "position": round(px / i, 1) if i else None, "complete": True}


def fmt_pct(now, prev) -> str:
    """Signed change, or a plain reason when it cannot be computed (R69F-07)."""
    if prev is None:
        return "n/a (comparison period incomplete)"
    if prev == 0:
        return "n/a (zero baseline)"
    return f"{pct(now, prev):+}%"


def shift(d: str, days: int) -> str:
    return (dt.date.fromisoformat(d) + dt.timedelta(days)).isoformat()


def page_movers(con, s, e, n=10):
    ps, pe = shift(s, -7), shift(e, -7)
    if final_days(con, ps, pe) < 7:
        return None, None  # comparison unavailable, not "no movers" (R958-07)
    rows = {}
    for w, k in (((s, e), "now"), ((ps, pe), "prev")):
        for p, c in con.execute("SELECT page, SUM(clicks) FROM page_daily WHERE date BETWEEN ? AND ? GROUP BY page", w):
            rows.setdefault(p, {})[k] = c
    lst = [{"page": p, "clicks": d.get("now", 0), "clicks_prev_week": d.get("prev", 0),
            "change": d.get("now", 0) - d.get("prev", 0)} for p, d in rows.items()]
    lst.sort(key=lambda r: r["change"])
    return lst[:n], lst[::-1][:n]


def conversions(cfg, s, e):
    c = cfg.get("conversions", {})
    path = seoconf.expand(c.get("sql"))
    if not path or not os.path.exists(path):
        return None, "no conversions SQL configured"
    sql = open(path).read().replace("{{start}}", s).replace("{{end}}", e)
    sess = seoconf.service_account_session(cfg, ["https://www.googleapis.com/auth/bigquery"])
    r = sess.post(f"https://bigquery.googleapis.com/bigquery/v2/projects/{c['bq_project']}/queries",
                  json={"query": sql, "useLegacySql": False, "location": c.get("bq_location", "US"),
                        "timeoutMs": 180000}, timeout=240)
    if r.status_code != 200:
        return None, f"BigQuery error {r.status_code}: {r.text[:300]}"
    j = r.json()
    if not j.get("jobComplete"):
        return None, "BigQuery query did not finish in time"
    cols = [f["name"] for f in j["schema"]["fields"]]
    raw = list(j.get("rows", []))
    token, ref = j.get("pageToken"), j.get("jobReference", {})
    while token:  # follow result pages (R69F-11)
        r = sess.get(f"https://bigquery.googleapis.com/bigquery/v2/projects/{ref.get('projectId', c['bq_project'])}"
                     f"/queries/{ref.get('jobId')}", params={"pageToken": token, "location": c.get("bq_location", "US")},
                     timeout=240)
        if r.status_code != 200:
            return None, f"BigQuery paging error {r.status_code}: {r.text[:300]}"
        page = r.json()
        raw += page.get("rows", [])
        token = page.get("pageToken")
    rows = [dict(zip(cols, [x["v"] for x in row["f"]])) for row in raw]
    for row in rows:
        for k in cols[1:]:
            row[k] = int(float(row[k] or 0))
    return rows, "GA4 sessions from google/organic by landing page; registrations and trials credited to the person's last google/organic landing page before the event (associated, not query-level attribution)"


def md_table(rows, cols, limit=15, note=""):
    if not rows:
        return f"_{note}_\n" if str(note).startswith("unavailable") else "_none_\n"
    out = ["| " + " | ".join(cols) + " |", "|" + "---|" * len(cols)]
    for r in rows[:limit]:
        out.append("| " + " | ".join("" if r.get(c) is None else str(r.get(c)) for c in cols) + " |")
    return "\n".join(out) + "\n"


def short(url: str) -> str:
    return url.split("://", 1)[-1]


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--site")
    ap.add_argument("--week")
    ap.add_argument("--no-sheet", action="store_true")
    ap.add_argument("--no-conversions", action="store_true")
    a = ap.parse_args()
    cfg = seoconf.load(a.site)
    con = connect(cfg)
    week, s, e = pick_week(con, a.week)
    now, prev = totals(con, s, e), totals(con, shift(s, -7), shift(e, -7))
    base4 = totals(con, shift(s, -28), shift(s, -1))
    for k in ("clicks", "impressions"):
        base4[k] = round(base4[k] / 4) if base4[k] is not None else None
    cov = _run("coverage", cfg, days=7, end=e)[0][0]
    brand_rows, _ = run("brand", cfg, days=7, end=e)
    brand_wk = next((r for r in brand_rows if r["week"] == week), {})
    striking, n_strike = run("striking", cfg, days=28, end=e)
    decay, n_decay = run("decay", cfg, days=28, end=e)
    newq, n_new = run("new_queries", cfg, days=7, end=e)
    gaps, n_gap = run("ctr_gap", cfg, days=28, end=e)
    cann, n_cann = run("cannibal", cfg, days=28, end=e)
    countries, n_countries = run("countries", cfg, days=7, end=e)
    losers, gainers = page_movers(con, s, e)
    n_movers = "unavailable: previous week is not complete" if losers is None else ""
    losers, gainers = losers or [], gainers or []
    conv, conv_note = (None, "skipped") if a.no_conversions else conversions(cfg, s, e)
    conv_status = "skipped" if a.no_conversions else ("ok" if conv is not None else "unavailable")  # R958-07

    rep = {"week": week, "start": s, "end": e, "property": cfg["site"]["gsc_property"], "totals": now,
           "prev_week": prev, "avg_prev_4_weeks": base4, "coverage": cov, "brand": brand_wk,
           "striking": striking[:25], "decay": decay[:15], "new_queries": newq[:25], "ctr_gap": gaps[:15],
           "cannibal": cann[:15], "countries": countries[:15], "page_losers": losers, "page_gainers": gainers,
           "conversions": conv, "conversions_note": conv_note,
           # per-section availability, so an unavailable calculation is never read as an empty result (RA35-03)
           "sections": {**{k: {"status": "unavailable" if str(n).startswith("unavailable") else "ok", "note": n}
                           for k, n in (("striking", n_strike), ("decay", n_decay), ("new_queries", n_new),
                                        ("ctr_gap", n_gap), ("cannibal", n_cann), ("countries", n_countries),
                                        ("page_losers", n_movers), ("page_gainers", n_movers))},
                        "conversions": {"status": conv_status, "note": conv_note}}}

    # ---- Markdown ----
    L = [f"# Search Console weekly · {week} ({s} – {e})", "",
         f"Property `{cfg['site']['gsc_property']}`. Dates are US Pacific. Query rows explain "
         f"{cov['click_coverage_pct']}% of clicks; the rest are anonymized queries.", "",
         "## Totals", "",
         "| | Clicks | Impressions | CTR % | Avg position |", "|---|---|---|---|---|",
         f"| This week | {now['clicks']} | {now['impressions']} | {now['ctr_pct']} | {now['position']} |",
         f"| Previous week | {prev['clicks']} | {prev['impressions']} | {prev['ctr_pct']} | {prev['position']} |",
         f"| Avg of 4 weeks before | {base4['clicks']} | {base4['impressions']} | | |", "",
         f"Clicks {fmt_pct(now['clicks'], prev['clicks'])} vs previous week. Brand {brand_wk.get('brand_clicks')}, "
         f"ambiguous {brand_wk.get('ambiguous_clicks')}, non-brand {brand_wk.get('non-brand_clicks')}, "
         f"hidden {brand_wk.get('hidden_clicks')} clicks.", ""]
    if conv is not None:
        L += ["## Organic landing pages → registrations and trials", "", conv_note, "",
              md_table(sorted(conv, key=lambda r: -r.get("organic_sessions", 0)),
                       list(conv[0].keys()) if conv else [], 15)]
    else:
        L += [f"_Conversions: {conv_note}_", ""]
    L += ["## Pages that lost the most clicks vs previous week", "", md_table(losers, ["page", "clicks", "clicks_prev_week", "change"], 10, n_movers),
          "## Pages that gained the most", "", md_table(gainers, ["page", "clicks", "clicks_prev_week", "change"], 10, n_movers),
          "## Striking distance (28 days, positions 5–20, non-brand)", "", n_strike, "",
          md_table(striking, ["query", "page", "impressions", "clicks", "position", "potential_clicks"], 15, n_strike),
          "## Decaying pages (28 days vs previous 28)", "", n_decay, "",
          md_table(decay, ["page", "clicks_prev", "clicks_now", "clicks_change_pct", "reason"], 10, n_decay),
          "## CTR below our curve (28 days, top 10)", "", n_gap, "",
          md_table(gaps, ["query", "page", "position", "impressions", "clicks", "expected_clicks"], 10, n_gap),
          "## New queries this week", "", n_new, "",
          md_table(newq, ["query", "top_page", "impressions", "clicks", "position", "script"], 15, n_new),
          "## Cannibalization candidates (28 days)", "", n_cann, "",
          md_table(cann, ["query", "locale", "impressions", "pages"], 10, n_cann),
          "## Countries this week", "",
          n_countries, "",
          md_table(countries, ["country", "clicks", "clicks_change_pct", "impressions", "ctr_pct", "position", "query_scripts"], 10, n_countries)]
    md = "\n".join(L)

    # ---- Slack text (short) ----
    top = striking[:3]
    S = [f"*Search Console · {week}* ({s} – {e})",
         f"Clicks {now['clicks']} ({fmt_pct(now['clicks'], prev['clicks'])} w/w) · impressions {now['impressions']} "
         f"({fmt_pct(now['impressions'], prev['impressions'])}) · CTR {now['ctr_pct']}% · avg position {now['position']}",
         f"Non-brand clicks {brand_wk.get('non-brand_clicks')} · brand {brand_wk.get('brand_clicks')} · "
         f"hidden {brand_wk.get('hidden_clicks')}"]
    if conv:
        S.append(f"Organic sessions {sum(r.get('organic_sessions', 0) for r in conv)} · registrations "
                 f"{sum(r.get('registrations', 0) for r in conv)} · trials {sum(r.get('trials', 0) for r in conv)}")
    if top:
        S.append("Closest wins: " + "; ".join(f"“{r['query']}” pos {r['position']} → {short(r['page'])}" for r in top))
    if decay:
        S.append("Biggest drop (28 days vs previous 28): " + "; ".join(f"{short(r['page'])} {r['clicks_prev']}→{r['clicks_now']}" for r in decay[:2]))
    if newq:
        S.append("New queries: " + ", ".join(f"“{r['query']}”" for r in newq[:5]))
    sid = cfg.get("report", {}).get("sheet_id")
    if sid:
        S.append(f"Full lists: https://docs.google.com/spreadsheets/d/{sid}")
    slack = "\n".join(S)

    out = seoconf.data_dir(cfg, "reports")
    base = os.path.join(out, week)
    open(base + ".md", "w").write(md)
    open(base + ".slack.txt", "w").write(slack)
    json.dump(rep, open(base + ".json", "w"), ensure_ascii=False, indent=1, default=str)

    # ---- Google Sheet ----
    if sid and not a.no_sheet:
        from sheets import Sheet
        sh = Sheet(cfg, sid)
        hdr = ["week", "start", "end", "clicks", "impressions", "ctr_pct", "avg_position", "brand_clicks",
               "ambiguous_clicks", "non_brand_clicks", "hidden_clicks", "query_click_coverage_pct",
               "organic_sessions", "registrations", "trials"]
        row = [week, s, e, now["clicks"], now["impressions"], now["ctr_pct"], now["position"],
               brand_wk.get("brand_clicks"), brand_wk.get("ambiguous_clicks"), brand_wk.get("non-brand_clicks"),
               brand_wk.get("hidden_clicks"), cov["click_coverage_pct"],
               sum(r.get("organic_sessions", 0) for r in conv) if conv else "",
               sum(r.get("registrations", 0) for r in conv) if conv else "",
               sum(r.get("trials", 0) for r in conv) if conv else ""]
        sh.upsert_row("Weekly", hdr, row)
        for title, rows, note in (("Striking distance", striking[:200], n_strike), ("Decaying pages", decay[:200], n_decay),
                                  ("CTR gaps", gaps[:200], n_gap), ("New queries", newq[:200], n_new),
                                  ("Cannibalization", cann[:200], n_cann),
                                  ("Organic landing pages", conv or [], conv_note)):
            head = [f"{week} ({s} – {e}). {note}"]
            if rows:
                cols = list(rows[0].keys())
                sh.overwrite(title, [head, cols] + [["" if r.get(c) is None else r.get(c) for c in cols] for r in rows])
            else:  # never leave last week's list looking current (R69F-10)
                sh.overwrite(title, [head, ["No rows for this week."]])
        print(f"Sheet updated: https://docs.google.com/spreadsheets/d/{sid}")

    hook = os.environ.get("SLACK_WEBHOOK_URL")
    if hook:
        import requests
        r = requests.post(hook, json={"text": slack}, timeout=30)
        print("Slack webhook:", r.status_code)
    print(f"Report: {base}.md\nSlack text: {base}.slack.txt")


if __name__ == "__main__":
    main()
