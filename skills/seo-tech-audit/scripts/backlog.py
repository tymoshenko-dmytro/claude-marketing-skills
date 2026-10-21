#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = ["google-auth>=2.30", "requests>=2.31"]
# ///
"""Audit backlog with memory: compare this audit's findings with earlier runs and keep a running list.

Run after audit.py. Each P1-P3 finding is tracked by a stable id (rule + title). Status per run:
  new       first time seen
  open      seen before and still present (weeks_open counts from the first sighting)
  fixed     present in the previous run, gone now
  reopened  was fixed, came back
State lives in <data>/audit_backlog.json. With [report].sheet_id set, the sheet tab "Audit backlog"
("Бэклог аудита" when [report].language = "ru") is rewritten from the state; the human-edited columns
Owner and Comment are read back first and kept.

Usage: backlog.py [--site S] [--crawl DIR] [--no-sheet] [--date YYYY-MM-DD]
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import seoconf  # noqa: E402
import backlog_details  # noqa: E402

RU_TITLES = {
    "R01": "Внутренние ссылки ведут на страницы с ошибкой",
    "R02": "Цепочки редиректов (больше одного шага)",
    "R02b": "Внутренние ссылки ведут на редиректы",
    "R03": "В сайтмапе страницы, которые нельзя индексировать",
    "R04": "Индексируемые страницы не в сайтмапе",
    "R05": "Страницы с noindex: проверить, что так задумано",
    "R06": "Страницы без canonical",
    "R06c": "Canonical ведёт на ошибку или noindex",
    "R06d": "Google выбрал другой canonical, чем указан на странице",
    "R07": "Индексируемые страницы не в индексе Google",
    "R08": "Внутренние ссылки с трекинг-параметрами (_gl, utm)",
    "R09": "Хосты app, platform или old видны в поиске",
    "R10": "Варианты http:// или без www открываются без редиректа 301",
    "R11": "Нет title или title повторяется",
    "R11b": "Title длиннее 60 или короче 20 символов",
    "R12": "Meta description нет, повторяется или не 70–160 символов",
    "R13": "Нет H1 или несколько H1",
    "R14": "Тонкие страницы: меньше 250 слов",
    "R15": "Картинки без alt",
    "R16": "Ошибка в JSON-LD разметке",
    "R17": "hreflang",
    "R18": "Медленный ответ сервера: больше 1 секунды",
    "R18b": "Core Web Vitals у реальных пользователей хуже нормы",
    "R19": "JavaScript меняет title, canonical или robots",
    "R19b": "После JavaScript на странице сильно больше текста",
    "R20": "robots.txt закрывает поисковых или ИИ-ботов",
    "R20x": "robots.txt недоступен, хост не проверен",
    "R21": "Bing сообщает об ошибках обхода",
}
RU_STATES = {
    "URL is unknown to Google": "Google о них не знает",
    "Discovered - currently not indexed": "найдены, но ещё не просканированы",
    "Crawled - currently not indexed": "просканированы, но не проиндексированы",
    "Excluded by ‘noindex’ tag": "последний обход Google видел noindex",
}
RU_HREFLANG = {
    "no self-reference": "нет ссылки на саму себя",
    "invalid language code": "неверный код языка",
    "target not crawled (outside scope or blocked)": "цель вне обхода",
    "target is not an indexable 200": "цель не индексируемая страница 200",
    "missing return link": "нет обратной ссылки",
    "hreflang code differs from the target's <html lang>": "код не совпадает с <html lang> цели",
}
STATUS = {"en": {"new": "new", "open": "open", "fixed": "fixed", "reopened": "reopened"},
          "ru": {"new": "новая", "open": "открыта", "fixed": "исправлена", "reopened": "вернулась"}}
HEADERS = {
    "en": ["ID", "Priority", "Issue", "What is wrong", "Why it matters", "What to do", "How to check", "URLs",
           "Google clicks 28d", "Status", "Weeks open", "First seen", "Last seen", "Fixed on", "Owner", "Comment"],
    "ru": ["ID", "Приоритет", "Проблема", "Что не так", "Почему важно", "Что сделать", "Как проверить", "Адресов",
           "Клики Google за 28 дней", "Статус", "Недель открыта", "Впервые", "Последний раз", "Исправлена",
           "Ответственный", "Комментарий"],
}
HUMAN = {"en": ("Owner", "Comment"), "ru": ("Ответственный", "Комментарий")}  # edited by people, kept across runs
TAB = {"en": "Audit backlog", "ru": "Бэклог аудита"}
URL_TAB = {"en": "Audit URLs", "ru": "Адреса аудита"}
URL_HEADERS = {"en": ["Task ID", "Priority", "Issue", "URL", "What exactly is wrong", "Google clicks 28d"],
               "ru": ["ID задачи", "Приоритет", "Проблема", "Адрес", "Что именно не так", "Клики Google за 28 дней"]}


def title_for(f: dict, lang: str) -> str:
    if lang != "ru":
        return f["title"]
    base = RU_TITLES.get(f["rule"], f["title"])
    if f["rule"] == "R07" and ":" in f["title"]:
        state = f["title"].split(":", 1)[1].strip()
        return f"{base}: {RU_STATES.get(state, state)}"
    if f["rule"] == "R17" and ":" in f["title"]:
        kind = f["title"].split(":", 1)[1].strip()
        return f"{base}: {RU_HREFLANG.get(kind, kind)}"
    return base


def weeks_open(first: str, today: str) -> int:
    return (dt.date.fromisoformat(today) - dt.date.fromisoformat(first)).days // 7 + 1


def update(state: dict, findings: list[dict], today: str, lang: str) -> dict:
    """Merge one audit run into the state. Returns this run's summary."""
    items = state.setdefault("items", {})
    seen = set()
    summary = {"date": today, "new": [], "fixed": [], "reopened": []}
    for f in findings:
        if f.get("priority") not in ("P1", "P2", "P3"):
            continue
        key = f"{f['rule']}|{f['title']}"
        seen.add(key)
        it = items.get(key)
        if it is None:
            it = items[key] = {"id": key, "rule": f["rule"], "first_seen": today, "history": []}
            it["status"] = "new"
            summary["new"].append(key)
        elif it["status"] == "fixed":
            it["status"] = "reopened"
            it.pop("fixed_on", None)
            summary["reopened"].append(key)
        else:
            it["status"] = "open" if it.get("last_seen") != today or it["status"] != "new" else "new"
        it.update(title=title_for(f, lang), title_en=f["title"], priority=f["priority"], severity=f["severity"],
                  owner=f.get("owner"), count=f["count"], clicks=f.get("gsc_clicks_28d"),
                  exposure_complete=f.get("exposure_complete", True), last_seen=today, urls=f.get("urls", [])[:5])
        if not it["history"] or it["history"][-1][0] != today:
            it["history"].append([today, f["count"]])
        else:
            it["history"][-1] = [today, f["count"]]
    for key, it in items.items():
        if key not in seen and it["status"] != "fixed":
            it["status"] = "fixed"
            it["fixed_on"] = today
            summary["fixed"].append(key)
    runs = state.setdefault("runs", [])
    if today not in runs:
        runs.append(today)
    opened = [it for it in items.values() if it["status"] != "fixed"]
    summary["open"] = {p: sum(1 for it in opened if it["priority"] == p) for p in ("P1", "P2", "P3")}
    summary["open_total"] = len(opened)
    summary["top"] = sorted(
        ({"id": it["id"], "priority": it["priority"], "title": it["title"], "count": it["count"],
          "clicks": it.get("clicks"), "status": it["status"], "weeks_open": weeks_open(it["first_seen"], today)}
         for it in opened if it["priority"] in ("P1", "P2")),
        key=lambda x: (x["priority"], -x["weeks_open"]))
    state["last_summary"] = summary
    return summary


def sheet_rows(state: dict, lang: str, keep: dict[str, tuple[str, str]], today: str) -> list[list]:
    order = {"P1": 0, "P2": 1, "P3": 2}
    items = sorted(state["items"].values(),
                   key=lambda it: (it["status"] == "fixed", order.get(it["priority"], 9), it["first_seen"]))
    st = STATUS.get(lang, STATUS["en"])
    rows = [HEADERS.get(lang, HEADERS["en"])]
    for it in items:
        if it["status"] == "fixed" and it.get("fixed_on") and \
                (dt.date.fromisoformat(today) - dt.date.fromisoformat(it["fixed_on"])).days > 56:
            continue  # fixed more than 8 weeks ago: drop from the sheet, keep in state
        owner, comment = keep.get(it["id"], (it.get("owner") or "", ""))
        clicks = it.get("clicks")
        if clicks is not None and not it.get("exposure_complete", True):
            clicks = f"{clicks}*"
        what, why, fix, check = it.get("details") or ("", "", "", "")
        rows.append([it["id"], it["priority"], it["title"], what, why, fix, check, it["count"],
                     "" if clicks is None else clicks, st.get(it["status"], it["status"]),
                     "" if it["status"] == "fixed" else weeks_open(it["first_seen"], today),
                     it["first_seen"], it["last_seen"], it.get("fixed_on", ""), owner, comment])
    return rows


def url_rows(state: dict, lang: str) -> list[list]:
    """One row per affected URL of every open task, with the specific reason."""
    order = {"P1": 0, "P2": 1, "P3": 2}
    rows = [URL_HEADERS.get(lang, URL_HEADERS["en"])]
    for it in sorted((i for i in state["items"].values() if i["status"] != "fixed"),
                     key=lambda i: (order.get(i["priority"], 9), i["id"])):
        for u, reason, clicks in it.get("url_rows", []):
            rows.append([it["id"], it["priority"], it["title"], u, reason, clicks])
    return rows


def exposure_by_url(cfg) -> dict:
    """Google clicks per URL over the last 28 final days (trailing slash folded)."""
    import sqlite3
    p = os.path.join(seoconf.expand(cfg["data"]["dir"]), "gsc.sqlite")
    if not os.path.exists(p):
        return {}
    con = sqlite3.connect(p)
    last = con.execute("SELECT MAX(date) FROM pull_log WHERE final=1").fetchone()[0]
    if not last:
        return {}
    out = {}
    for page, c in con.execute("""SELECT page, SUM(clicks) FROM page_daily WHERE date > date(?, '-28 days') AND date <= ?
                                  AND date IN (SELECT date FROM pull_log WHERE final=1) GROUP BY page""", (last, last)):
        out[page.rstrip("/")] = out.get(page.rstrip("/"), 0) + c
    return out


def attach_details(state: dict, findings: list[dict], crawl: str, cfg: dict, lang: str) -> None:
    """Store the plain-language task texts and per-URL reasons on each current item."""
    import sqlite3
    pages = {}
    dbp = os.path.join(crawl, "crawl.sqlite")
    if os.path.exists(dbp):
        db = sqlite3.connect(dbp)
        db.row_factory = sqlite3.Row
        pages = {r["url"]: dict(r) for r in db.execute("SELECT * FROM pages")}
    ip = os.path.join(crawl, "inspection.json")
    insp = json.load(open(ip)) if os.path.exists(ip) else {}
    exp = exposure_by_url(cfg)
    for f in findings:
        it = state["items"].get(f"{f['rule']}|{f['title']}")
        if it is None:
            continue
        it["details"] = list(backlog_details.details(f, lang))
        it["url_rows"] = backlog_details.url_reasons(f, pages, insp, exp, lang)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--site")
    ap.add_argument("--crawl")
    ap.add_argument("--no-sheet", action="store_true")
    ap.add_argument("--date")
    a = ap.parse_args()
    cfg = seoconf.load(a.site)
    lang = cfg.get("report", {}).get("language", "en")
    crawl = os.path.realpath(a.crawl or os.path.join(seoconf.data_dir(cfg, "crawls"), "latest"))
    fpath = os.path.join(crawl, "findings.json")
    if not os.path.exists(fpath):
        sys.exit(f"No findings.json in {crawl}. Run audit.py first.")
    findings = json.load(open(fpath))["findings"]
    today = a.date or dt.date.today().isoformat()
    spath = os.path.join(seoconf.data_dir(cfg), "audit_backlog.json")
    state = json.load(open(spath)) if os.path.exists(spath) else {}
    summary = update(state, findings, today, lang)
    attach_details(state, findings, crawl, cfg, lang)
    for t in summary.get("top", []):  # the digest's action candidates get the "what to do" text too
        t["what_to_do"] = (state["items"][t["id"]].get("details") or ["", "", ""])[2]
    json.dump(state, open(spath, "w"), ensure_ascii=False, indent=1)
    sid = cfg.get("report", {}).get("sheet_id")
    if sid and not a.no_sheet:
        sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "gsc-insights", "scripts"))
        from sheets import Sheet  # noqa: PLC0415
        sh = Sheet(cfg, sid)
        tab = TAB.get(lang, TAB["en"])
        sh.ensure_tab(tab)
        keep = {}
        cur = sh.read(tab)
        if cur:  # find the human columns by name, so a layout change never loses what people typed
            hdr = cur[0]
            io, ic = (hdr.index(h) if h in hdr else None for h in HUMAN.get(lang, HUMAN["en"]))
            for r in cur[1:]:
                if r:
                    keep[r[0]] = (r[io] if io is not None and len(r) > io else "",
                                  r[ic] if ic is not None and len(r) > ic else "")
        sh.overwrite(tab, sheet_rows(state, lang, keep, today))
        utab = URL_TAB.get(lang, URL_TAB["en"])
        sh.overwrite(utab, url_rows(state, lang))
        print(f"Sheet tabs '{tab}' and '{utab}' updated")
    print(f"Backlog {today}: open {summary['open_total']} (P1 {summary['open']['P1']}, P2 {summary['open']['P2']}, "
          f"P3 {summary['open']['P3']}); new {len(summary['new'])}, fixed {len(summary['fixed'])}, "
          f"reopened {len(summary['reopened'])}\n{spath}")


if __name__ == "__main__":
    main()
