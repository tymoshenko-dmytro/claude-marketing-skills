#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = ["google-auth>=2.30", "requests>=2.31", "matplotlib>=3.8"]
# ///
"""Weekly organic digest: what organic search brought (visits -> sign-ups -> trials by source), search
visibility (Google GSC, Bing Webmaster), the technical-audit backlog, and candidate actions for the week.

Inputs: [digest].sources_sql (GA4 + backend, see references/config.md), the local GSC archive (gsc_pull.py),
BING_WMT_API_KEY (optional), <data>/audit_backlog.json from seo-tech-audit's backlog.py (optional).
Outputs in <data>/reports/: <week>.digest.json (all numbers + action candidates), <week>.digest.md (Slack text in
[report].language with an {{ACTIONS}} line for the caller to fill), <week>.trend.png (stacked weekly visits).
With [report].sheet_id set, the "Summary"/"Сводка" tab gets one row per week.

Usage: weekly_digest.py [--site S] [--week 2026-W42] [--no-sheet] [--no-bing]
Default week: the last full ISO week (Mon-Sun) before today. It stops when GA4 lacks any day of that week.
"""
from __future__ import annotations

import argparse
import collections
import datetime as dt
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import seoconf  # noqa: E402
from gsc_pull import connect  # noqa: E402

CHANNELS = ["Google", "AI assistants", "Bing", "Other search"]
COLORS = {"Google": "#2a78d6", "AI assistants": "#1baf7a", "Bing": "#eb6834", "Other search": "#888780"}
RU = {"Google": "Google", "AI assistants": "ИИ-ассистенты", "Bing": "Bing", "Other search": "Другие поисковики"}
RU_MONTHS = ["янв", "фев", "мар", "апр", "мая", "июн", "июл", "авг", "сен", "окт", "ноя", "дек"]
MINUS = "−"


# ---------- formatting ----------

def num(n, lang):
    if n is None:
        return "н/д" if lang == "ru" else "n/a"
    s = f"{n:,.0f}" if isinstance(n, (int, float)) else str(n)
    return s.replace(",", " ") if lang == "ru" else s


def chg(now, prev, lang):
    """Signed % change; explicit words for missing or zero baselines."""
    if now is None or prev is None:
        return "н/д" if lang == "ru" else "n/a"
    if prev == 0:
        return ("новое" if lang == "ru" else "new") if now else "0%"
    p = round(100 * (now - prev) / prev)
    return f"+{p}%" if p > 0 else (f"{MINUS}{abs(p)}%" if p < 0 else "0%")


def plural(n, one, few, many):
    """Russian noun form for a count: 1 визит, 2 визита, 5 визитов."""
    n = abs(int(n or 0))
    if n % 10 == 1 and n % 100 != 11:
        return one
    if 2 <= n % 10 <= 4 and not 12 <= n % 100 <= 14:
        return few
    return many


def ru_n(n, one, few, many):
    return f"{num(n, 'ru')} {plural(n, one, few, many)}"


def day_ru(d: str) -> str:
    x = dt.date.fromisoformat(d)
    return f"{x.day} {RU_MONTHS[x.month - 1]}"


def span(mon: dt.date, lang) -> str:
    sun = mon + dt.timedelta(6)
    if lang == "ru":
        if mon.month == sun.month:
            return f"{mon.day}–{sun.day} {RU_MONTHS[sun.month - 1]}"
        return f"{mon.day} {RU_MONTHS[mon.month - 1]} – {sun.day} {RU_MONTHS[sun.month - 1]}"
    return f"{mon:%d %b} – {sun:%d %b}"


def iso(d: dt.date) -> str:
    y, w, _ = d.isocalendar()
    return f"{y}-W{w:02d}"


# ---------- data ----------

def bq_rows(cfg, sql):
    c = cfg.get("conversions", {})
    sess = seoconf.service_account_session(cfg, ["https://www.googleapis.com/auth/bigquery"])
    project, loc = c.get("bq_project"), c.get("bq_location", "US")
    r = sess.post(f"https://bigquery.googleapis.com/bigquery/v2/projects/{project}/queries",
                  json={"query": sql, "useLegacySql": False, "location": loc, "timeoutMs": 240000}, timeout=300)
    if r.status_code != 200:
        sys.exit(seoconf.redact(f"BigQuery error {r.status_code}: {r.text}")[:400])
    j = r.json()
    if not j.get("jobComplete"):
        sys.exit("BigQuery query did not finish in time")
    cols = [f["name"] for f in j["schema"]["fields"]]
    raw, token, ref = list(j.get("rows", [])), j.get("pageToken"), j.get("jobReference", {})
    while token:
        p = sess.get(f"https://bigquery.googleapis.com/bigquery/v2/projects/{ref.get('projectId', project)}/queries/{ref.get('jobId')}",
                     params={"pageToken": token, "location": loc}, timeout=300)
        if p.status_code != 200:
            sys.exit(seoconf.redact(f"BigQuery paging error {p.status_code}: {p.text}")[:400])
        raw += p.json().get("rows", [])
        token = p.json().get("pageToken")
    return [dict(zip(cols, [x["v"] for x in row["f"]])) for row in raw]


def sources(cfg, start: dt.date, end: dt.date):
    path = seoconf.expand(cfg.get("digest", {}).get("sources_sql"))
    if not path or not os.path.exists(path):
        sys.exit("[digest].sources_sql is not configured; the digest needs organic sessions by source.")
    sql = open(path).read().replace("{{start}}", start.isoformat()).replace("{{end}}", end.isoformat())
    by = collections.defaultdict(lambda: collections.defaultdict(lambda: {"sessions": 0, "registrations": 0, "trials": 0}))
    days = {}
    for r in bq_rows(cfg, sql):
        if r["channel"] == "_days":
            days[r["week"]] = int(float(r["sessions"] or 0))
            continue
        for k in ("sessions", "registrations", "trials"):
            by[r["week"]][r["channel"]][k] += int(float(r[k] or 0))
    return by, days


def gsc_week(con, mon: dt.date):
    s, e = mon.isoformat(), (mon + dt.timedelta(6)).isoformat()
    n = con.execute("SELECT COUNT(*) FROM pull_log WHERE final=1 AND date BETWEEN ? AND ?", (s, e)).fetchone()[0]
    if n < 7:
        return None
    c, i, px = con.execute("SELECT SUM(clicks), SUM(impressions), SUM(pos_x_impr) FROM site_daily WHERE date BETWEEN ? AND ?",
                           (s, e)).fetchone()
    return {"clicks": c or 0, "impressions": i or 0, "position": round(px / i, 1) if i else None}


def bing_weeks(cfg):
    key = os.environ.get("BING_WMT_API_KEY")
    site = cfg["site"].get("bing_site")
    if not key or not site:
        return None, "Bing key or bing_site not configured"
    import requests
    try:
        r = requests.get("https://ssl.bing.com/webmaster/api.svc/json/GetRankAndTrafficStats",
                         params={"siteUrl": site, "apikey": key}, timeout=60)
    except requests.RequestException as e:
        return None, seoconf.redact(f"{type(e).__name__}: {e}")[:200]
    if r.status_code != 200:
        return None, seoconf.redact(f"{r.status_code} {r.text}")[:200]
    out = collections.defaultdict(lambda: {"clicks": 0, "impressions": 0})
    for x in r.json().get("d") or []:
        m = re.search(r"\d+", str(x.get("Date", "")))
        if not m:
            continue
        d = dt.datetime.fromtimestamp(int(m.group()) / 1000, dt.UTC).date()
        out[iso(d)]["clicks"] += x.get("Clicks", 0)
        out[iso(d)]["impressions"] += x.get("Impressions", 0)
    return out, None


# ---------- chart ----------

def chart(path, weeks, by, lang):
    """Two stacked-bar panels on one image: organic visits and trials per week by source (no dual axis)."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    fig, axes = plt.subplots(2, 1, figsize=(10, 6.4), dpi=144, gridspec_kw={"height_ratios": [3, 2]}, sharex=True)
    labels = [span(dt.date.fromisocalendar(int(w[:4]), int(w[-2:]), 1), lang) for w in weeks]
    titles = (("Органические визиты по источникам", "Триалы из органики") if lang == "ru"
              else ("Organic visits by source", "Trials from organic"))
    for ax, metric, title in zip(axes, ("sessions", "trials"), titles):
        bottom = [0] * len(weeks)
        for ch in CHANNELS:
            vals = [by.get(w, {}).get(ch, {}).get(metric, 0) for w in weeks]
            ax.bar(range(len(weeks)), vals, bottom=bottom, color=COLORS[ch], width=0.6,
                   label=RU[ch] if lang == "ru" else ch, edgecolor="white", linewidth=1)
            bottom = [b + v for b, v in zip(bottom, vals)]
        top = max(bottom) or 1
        for x, total in enumerate(bottom):
            ax.text(x, total + top * 0.015, num(total, lang), ha="center", va="bottom", fontsize=9, color="#52514e")
        ax.set_ylim(0, top * 1.15)
        ax.tick_params(axis="y", labelsize=9, colors="#898781")
        for sp in ("top", "right", "left"):
            ax.spines[sp].set_visible(False)
        ax.spines["bottom"].set_color("#c3c2b7")
        ax.grid(axis="y", color="#e1e0d9", linewidth=0.8)
        ax.set_axisbelow(True)
        ax.set_title(title, loc="left", fontsize=12, color="#0b0b0b")
    axes[1].set_xticks(range(len(weeks)), labels, fontsize=9, color="#52514e")
    axes[1].legend(loc="upper center", bbox_to_anchor=(0.5, -0.22), ncol=4, frameon=False, fontsize=9)
    fig.tight_layout()
    fig.savefig(path, facecolor="white")
    plt.close(fig)


# ---------- main ----------

def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--site")
    ap.add_argument("--week")
    ap.add_argument("--no-sheet", action="store_true")
    ap.add_argument("--no-bing", action="store_true")
    a = ap.parse_args()
    cfg = seoconf.load(a.site)
    rep = cfg.get("report", {})
    lang = rep.get("language", "en")
    n_weeks = int(rep.get("trend_weeks", 8))
    if a.week:
        mon = dt.date.fromisocalendar(int(a.week[:4]), int(a.week.split("W")[1]), 1)
    else:
        today = dt.date.today()
        mon = today - dt.timedelta(days=today.weekday() + 7)
    week, prev_week = iso(mon), iso(mon - dt.timedelta(7))
    start = mon - dt.timedelta(weeks=n_weeks - 1)
    weeks = [iso(start + dt.timedelta(weeks=i)) for i in range(n_weeks)]
    by, days = sources(cfg, start, mon + dt.timedelta(6))
    if days.get(week, 0) < 7:
        sys.exit(f"GA4 has {days.get(week, 0)}/7 days for {week}; the digest needs the full week. Try again later.")
    prev_ok = days.get(prev_week, 0) == 7

    def tot(w, k):
        return sum(by.get(w, {}).get(ch, {}).get(k, 0) for ch in CHANNELS)
    now = {k: tot(week, k) for k in ("sessions", "registrations", "trials")}
    prev = {k: (tot(prev_week, k) if prev_ok else None) for k in ("sessions", "registrations", "trials")}
    rows = []
    for ch in CHANNELS:
        c, p = by.get(week, {}).get(ch, {}), by.get(prev_week, {}).get(ch, {})
        s = c.get("sessions", 0)
        rows.append({"channel": ch, "sessions": s, "sessions_prev": p.get("sessions", 0) if prev_ok else None,
                     "registrations": c.get("registrations", 0), "trials": c.get("trials", 0),
                     "visit_to_trial_pct": round(100 * c.get("trials", 0) / s, 1) if s else None})

    con = connect(cfg)
    g_now, g_prev = gsc_week(con, mon), gsc_week(con, mon - dt.timedelta(7))
    nb_now = nb_prev = None
    if g_now:
        from gsc_recipes import run as recipe  # noqa: PLC0415
        try:
            br = {r["week"]: r for r in recipe("brand", cfg, days=7, end=(mon + dt.timedelta(6)).isoformat())[0]}
            nb_now = br.get(week, {}).get("non-brand_clicks")
            nb_prev = br.get(prev_week, {}).get("non-brand_clicks")
        except SystemExit:
            pass
    bing, bing_err = (None, "skipped") if a.no_bing else bing_weeks(cfg)
    b_now = bing.get(week) if bing else None
    b_prev = bing.get(prev_week) if bing else None

    bpath = os.path.join(seoconf.expand(cfg["data"]["dir"]), "audit_backlog.json")
    backlog = json.load(open(bpath)).get("last_summary") if os.path.exists(bpath) else None

    # action candidates: facts only; the caller words at most three of them
    cands = []
    if backlog:
        for t in backlog.get("top", [])[:4]:
            cands.append({"type": "audit", **t})
    try:
        from gsc_recipes import run as recipe  # noqa: PLC0415
        end = con.execute("SELECT MAX(date) FROM pull_log WHERE final=1").fetchone()[0]
        for r in recipe("striking", cfg, days=28, end=end)[0][:5]:
            cands.append({"type": "striking", "query": r["query"], "page": r["page"], "position": r["position"],
                          "impressions_28d": r["impressions"], "clicks_28d": r["clicks"]})
        for r in recipe("decay", cfg, days=28, end=end)[0][:2]:
            cands.append({"type": "decay", "page": r["page"], "clicks_prev_28d": r["clicks_prev"],
                          "clicks_28d": r["clicks_now"], "reason": r["reason"]})
    except SystemExit:
        pass
    try:
        from gsc_report import conversions  # noqa: PLC0415
        conv, _ = conversions(cfg, mon.isoformat(), (mon + dt.timedelta(6)).isoformat())
        for r in conv or []:
            if r.get("registrations", 0) >= 10 and r.get("trials", 0) == 0:
                cands.append({"type": "conversion_gap", "page": r["landing_page"], "organic_sessions": r["organic_sessions"],
                              "registrations": r["registrations"], "trials": 0})
    except SystemExit:
        pass

    out_dir = seoconf.data_dir(cfg, "reports")
    png = os.path.join(out_dir, f"{week}.trend.png")
    chart(png, weeks, by, lang)

    ai = next(r for r in rows if r["channel"] == "AI assistants")
    share_visits = round(100 * ai["sessions"] / now["sessions"]) if now["sessions"] else 0
    share_trials = round(100 * ai["trials"] / now["trials"]) if now["trials"] else 0
    data = {"week": week, "start": mon.isoformat(), "end": (mon + dt.timedelta(6)).isoformat(), "prev_week": prev_week,
            "prev_week_complete": prev_ok, "totals": now, "totals_prev": prev, "by_source": rows,
            "trend": {w: {ch: by.get(w, {}).get(ch, {}).get("sessions", 0) for ch in CHANNELS} for w in weeks},
            "google": {"now": g_now, "prev": g_prev, "non_brand_clicks": nb_now, "non_brand_clicks_prev": nb_prev},
            "bing": {"now": b_now, "prev": b_prev, "error": bing_err}, "audit": backlog, "action_candidates": cands,
            "chart": png}

    L = []
    if lang == "ru":
        L.append(f"**SEO за неделю · {span(mon, lang)}** (сравнение с {span(mon - dt.timedelta(7), lang)})")
        L.append(f"Органика принесла {ru_n(now['sessions'], 'визит', 'визита', 'визитов')} ({chg(now['sessions'], prev['sessions'], lang)}), "
                 f"{ru_n(now['registrations'], 'регистрацию', 'регистрации', 'регистраций')} ({chg(now['registrations'], prev['registrations'], lang)}) "
                 f"и {ru_n(now['trials'], 'триал', 'триала', 'триалов')} ({chg(now['trials'], prev['trials'], lang)}).")
        if now["trials"] and ai["trials"]:
            L.append(f"ИИ-ассистенты дали {share_visits}% визитов и {share_trials}% триалов.")
        L += ["", "| Источник | Визиты | К прошлой неделе | Регистрации | Триалы | Визит → триал |", "|---|---|---|---|---|---|"]
        for r in rows:
            L.append(f"| {RU[r['channel']]} | {num(r['sessions'], lang)} | {chg(r['sessions'], r['sessions_prev'], lang)} | "
                     f"{num(r['registrations'], lang)} | {num(r['trials'], lang)} | "
                     f"{'—' if r['visit_to_trial_pct'] is None else ('0%' if not r['trials'] else str(r['visit_to_trial_pct']).replace('.', ',') + '%')} |")
        L += ["", "**Видимость в поиске**"]
        if g_now:
            nb = f", из них не по бренду {num(nb_now, lang)} ({chg(nb_now, nb_prev, lang)})" if nb_now is not None else ""
            L.append(f"Google: {ru_n(g_now['clicks'], 'клик', 'клика', 'кликов')} ({chg(g_now['clicks'], (g_prev or {}).get('clicks'), lang)}){nb}, "
                     f"{ru_n(g_now['impressions'], 'показ', 'показа', 'показов')} ({chg(g_now['impressions'], (g_prev or {}).get('impressions'), lang)}), "
                     f"средняя позиция {str(g_now['position']).replace('.', ',')}")
        else:
            L.append("Google: Search Console ещё не закрыл эту неделю, данные будут в следующем отчёте.")
        if b_now:
            L.append(f"Bing: {ru_n(b_now['clicks'], 'клик', 'клика', 'кликов')} ({chg(b_now['clicks'], (b_prev or {}).get('clicks'), lang)}), "
                     f"{ru_n(b_now['impressions'], 'показ', 'показа', 'показов')} ({chg(b_now['impressions'], (b_prev or {}).get('impressions'), lang)})")
        elif bing_err and bing_err != "skipped":
            L.append(f"Bing: данные недоступны ({bing_err[:80]})")
        if backlog:
            o = backlog["open"]
            L += ["", f"**Технический аудит** · открыто {backlog['open_total']} (P1 — {o['P1']}, P2 — {o['P2']}) · "
                      f"новых {len(backlog['new'])} · исправлено {len(backlog['fixed'])} · проверка {day_ru(backlog['date'])}"]
            for t in backlog.get("top", [])[:4]:
                L.append(f"{t['priority']}: {t['title']} · {ru_n(t['count'], 'адрес', 'адреса', 'адресов')} · "
                         f"висит {ru_n(t['weeks_open'], 'неделю', 'недели', 'недель')}")
        L += ["", "**На этой неделе**", "{{ACTIONS}}", ""]
        if rep.get("sheet_id"):
            L.append(f"Все цифры и бэклог: https://docs.google.com/spreadsheets/d/{rep['sheet_id']}")
    else:
        L.append(f"**SEO weekly · {span(mon, lang)}** (vs {span(mon - dt.timedelta(7), lang)})")
        L.append(f"Organic brought {num(now['sessions'], lang)} visits ({chg(now['sessions'], prev['sessions'], lang)}), "
                 f"{num(now['registrations'], lang)} sign-ups ({chg(now['registrations'], prev['registrations'], lang)}) and "
                 f"{num(now['trials'], lang)} trials ({chg(now['trials'], prev['trials'], lang)}).")
        L += ["", "| Source | Visits | w/w | Sign-ups | Trials | Visit→trial |", "|---|---|---|---|---|---|"]
        for r in rows:
            L.append(f"| {r['channel']} | {num(r['sessions'], lang)} | {chg(r['sessions'], r['sessions_prev'], lang)} | "
                     f"{r['registrations']} | {r['trials']} | {'' if r['visit_to_trial_pct'] is None else str(r['visit_to_trial_pct']) + '%'} |")
        L += ["", "**This week**", "{{ACTIONS}}"]
    text = "\n".join(L)

    base = os.path.join(out_dir, week)
    json.dump(data, open(base + ".digest.json", "w"), ensure_ascii=False, indent=1, default=str)
    open(base + ".digest.md", "w").write(text)

    sid = rep.get("sheet_id")
    if sid and not a.no_sheet:
        from sheets import Sheet  # noqa: PLC0415
        tab = "Сводка" if lang == "ru" else "Summary"
        hdr = (["Неделя", "Даты", "Визиты всего", "Google", "ИИ-ассистенты", "Bing", "Другие", "Регистрации", "Триалы",
                "Клики Google (GSC)", "Клики Bing", "Аудит: открыто", "Аудит: P1"] if lang == "ru" else
               ["Week", "Dates", "Visits", "Google", "AI assistants", "Bing", "Other", "Sign-ups", "Trials",
                "Google clicks (GSC)", "Bing clicks", "Audit open", "Audit P1"])
        vis = {r["channel"]: r["sessions"] for r in rows}
        Sheet(cfg, sid).upsert_row(tab, hdr, [week, span(mon, lang), now["sessions"], vis["Google"], vis["AI assistants"],
                                              vis["Bing"], vis["Other search"], now["registrations"], now["trials"],
                                              g_now["clicks"] if g_now else "", b_now["clicks"] if b_now else "",
                                              backlog["open_total"] if backlog else "", backlog["open"]["P1"] if backlog else ""])
        print(f"Sheet tab '{tab}' updated")
    print(f"Digest {week}: {base}.digest.md\nChart: {png}\nData: {base}.digest.json")


if __name__ == "__main__":
    main()
