#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = ["google-auth>=2.30", "requests>=2.31"]
# ///
"""Pull Search Console data into a local SQLite archive, one day at a time.

Three grains are stored separately and never summed into each other:
  site_daily   property totals (aggregationType=byProperty)      -> the denominator
  page_daily   date x page (byPage)                              -> landing-page bridge
  query_daily  date x query x page x country x device (byPage)   -> opportunity detail
Positions are stored as position*impressions (pos_x_impr) so any aggregate is
SUM(pos_x_impr)/SUM(impressions). Days Google still marks incomplete are stored as provisional
and re-pulled on the next run.

Usage:
  gsc_pull.py [--site example] [--start YYYY-MM-DD] [--end YYYY-MM-DD] [--workers 4]
Defaults: on an empty archive, back-fill 16 months; afterwards, from the last final day minus 3.
"""
from __future__ import annotations

import argparse
import datetime as dt
import os
import sqlite3
import sys
import urllib.parse
from concurrent.futures import ThreadPoolExecutor

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import seoconf  # noqa: E402

SCOPE = ["https://www.googleapis.com/auth/webmasters.readonly"]
ROW_LIMIT = 25000
DAILY_ROW_CAP = 50000  # documented max detail rows per day per search type

SCHEMA = """
CREATE TABLE IF NOT EXISTS site_daily(date TEXT PRIMARY KEY, clicks INT, impressions INT, pos_x_impr REAL, final INT);
CREATE TABLE IF NOT EXISTS page_daily(date TEXT, page TEXT, clicks INT, impressions INT, pos_x_impr REAL,
  PRIMARY KEY(date, page));
CREATE TABLE IF NOT EXISTS query_daily(date TEXT, query TEXT, page TEXT, country TEXT, device TEXT,
  clicks INT, impressions INT, pos_x_impr REAL, PRIMARY KEY(date, query, page, country, device));
CREATE TABLE IF NOT EXISTS pull_log(date TEXT PRIMARY KEY, final INT, site_rows INT, page_rows INT,
  query_rows INT, query_truncated INT, pulled_at TEXT);
CREATE INDEX IF NOT EXISTS qd_query ON query_daily(query);
CREATE INDEX IF NOT EXISTS qd_page ON query_daily(page);
"""


def db_path(cfg: dict) -> str:
    return os.path.join(seoconf.data_dir(cfg), "gsc.sqlite")


def connect(cfg: dict) -> sqlite3.Connection:
    con = sqlite3.connect(db_path(cfg))
    con.executescript(SCHEMA)
    return con


class GSC:
    def __init__(self, cfg: dict):
        self.s = seoconf.service_account_session(cfg, SCOPE)
        prop = urllib.parse.quote(cfg["site"]["gsc_property"], safe="")
        self.url = f"https://searchconsole.googleapis.com/webmasters/v3/sites/{prop}/searchAnalytics/query"

    def query(self, body: dict) -> dict:
        for attempt in range(5):
            r = self.s.post(self.url, json=body, timeout=120)
            if r.status_code in (429, 500, 503):
                import time
                time.sleep(15 * (attempt + 1))
                continue
            if r.status_code != 200:
                sys.exit(f"GSC API {r.status_code}: {r.text[:500]}")
            return r.json()
        sys.exit("GSC API kept failing (rate limit or server errors). Try later with fewer --workers.")

    def rows(self, day: str, dims: list[str], aggregation: str) -> tuple[list[dict], dict]:
        out, start, meta = [], 0, {}
        while True:
            body = {"startDate": day, "endDate": day, "type": "web", "dimensions": dims,
                    "aggregationType": aggregation, "dataState": "all", "rowLimit": ROW_LIMIT, "startRow": start}
            r = self.query(body)
            meta = r.get("metadata", meta)
            batch = r.get("rows", [])
            out += batch
            if len(batch) < ROW_LIMIT:
                return out, meta
            start += ROW_LIMIT


def pull_day(gsc: GSC, day: str) -> dict:
    site, meta = gsc.rows(day, ["date"], "byProperty")
    pages, _ = gsc.rows(day, ["page"], "byPage")
    queries, _ = gsc.rows(day, ["query", "page", "country", "device"], "byPage")
    first_incomplete = meta.get("firstIncompleteDate") or meta.get("first_incomplete_date")
    final = int(first_incomplete is None or day < first_incomplete)
    return {"day": day, "site": site, "pages": pages, "queries": queries, "final": final}


def store(con: sqlite3.Connection, res: dict) -> None:
    d = res["day"]
    with con:
        for t in ("site_daily", "page_daily", "query_daily"):
            con.execute(f"DELETE FROM {t} WHERE date=?", (d,))
        for r in res["site"]:
            con.execute("INSERT INTO site_daily VALUES(?,?,?,?,?)",
                        (d, r["clicks"], r["impressions"], r["position"] * r["impressions"], res["final"]))
        con.executemany("INSERT INTO page_daily VALUES(?,?,?,?,?)",
                        [(d, r["keys"][0], r["clicks"], r["impressions"], r["position"] * r["impressions"])
                         for r in res["pages"]])
        con.executemany("INSERT OR REPLACE INTO query_daily VALUES(?,?,?,?,?,?,?,?)",
                        [(d, *r["keys"], r["clicks"], r["impressions"], r["position"] * r["impressions"])
                         for r in res["queries"]])
        con.execute("INSERT OR REPLACE INTO pull_log VALUES(?,?,?,?,?,?,?)",
                    (d, res["final"], len(res["site"]), len(res["pages"]), len(res["queries"]),
                     int(len(res["queries"]) >= DAILY_ROW_CAP), dt.datetime.now(dt.UTC).isoformat(timespec="seconds")))


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--site")
    ap.add_argument("--start")
    ap.add_argument("--end")
    ap.add_argument("--workers", type=int, default=4)
    a = ap.parse_args()
    cfg = seoconf.load(a.site)
    con = connect(cfg)
    today = dt.date.today()
    end = dt.date.fromisoformat(a.end) if a.end else today - dt.timedelta(days=1)
    if a.start:
        start = dt.date.fromisoformat(a.start)
    else:
        last_final = con.execute("SELECT MAX(date) FROM pull_log WHERE final=1").fetchone()[0]
        start = (dt.date.fromisoformat(last_final) - dt.timedelta(days=3)) if last_final \
            else today - dt.timedelta(days=486)  # 16 months
    done = {r[0] for r in con.execute("SELECT date FROM pull_log WHERE final=1")}
    days = [(start + dt.timedelta(n)).isoformat() for n in range((end - start).days + 1)]
    todo = [d for d in days if d not in done or a.start]
    # provisional days older than the incremental start must not be stranded (R69F-01)
    stranded = [] if a.start else [d for (d,) in con.execute(  # explicit ranges stay exact (RA35-01)
        "SELECT date FROM pull_log WHERE final=0 AND date < ? AND date <= ?", (start.isoformat(), end.isoformat()))]
    todo = sorted(set(todo) | set(stranded))
    print(f"{cfg['site']['gsc_property']}: {len(todo)} day(s) to pull, {start} .. {end}", flush=True)
    gsc = GSC(cfg)
    n = 0
    with ThreadPoolExecutor(max_workers=a.workers) as ex:
        for res in ex.map(lambda d: pull_day(gsc, d), todo):
            store(con, res)
            n += 1
            if n % 20 == 0 or n == len(todo):
                print(f"  {n}/{len(todo)} last={res['day']} final={res['final']} "
                      f"pages={len(res['pages'])} query_rows={len(res['queries'])}", flush=True)
    s = con.execute("SELECT MIN(date), MAX(date), SUM(final), COUNT(*), SUM(query_truncated) FROM pull_log").fetchone()
    print(f"Archive {db_path(cfg)}: {s[0]} .. {s[1]}, {s[3]} days ({s[2]} final), truncated days: {s[4]}")


if __name__ == "__main__":
    main()
