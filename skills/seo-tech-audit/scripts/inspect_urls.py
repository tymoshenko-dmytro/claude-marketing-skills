#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = ["google-auth>=2.30", "requests>=2.31"]
# ///
"""Inspect crawled URLs with the Search Console URL Inspection API (Google's indexed view, not a live test).

Takes 200-status HTML URLs from the latest crawl (or --urls file), most important first (GSC clicks, then
sitemap membership), and inspects up to --limit of them (quota: 2,000 per property per day). Results are
cached per URL per day in <data>/inspect.sqlite and copied into the crawl folder as inspection.json.

Usage: inspect_urls.py [--site S] [--limit 600] [--crawl DIR] [--urls file.txt]
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import sqlite3
import sys
from concurrent.futures import ThreadPoolExecutor


def valid(text: str) -> bool:
    """A usable inspection envelope: JSON object with a dict at inspectionResult.indexStatusResult (R958-03)."""
    try:
        j = json.loads(text)
    except (ValueError, TypeError):
        return False
    return isinstance(j, dict) and isinstance(j.get("inspectionResult"), dict) and \
        isinstance(j["inspectionResult"].get("indexStatusResult"), dict)

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import seoconf  # noqa: E402

SCOPE = ["https://www.googleapis.com/auth/webmasters.readonly"]
API = "https://searchconsole.googleapis.com/v1/urlInspection/index:inspect"


def gsc_clicks(cfg) -> dict[str, int]:
    p = os.path.join(seoconf.expand(cfg["data"]["dir"]), "gsc.sqlite")
    if not os.path.exists(p):
        return {}
    con = sqlite3.connect(p)
    return dict(con.execute("SELECT page, SUM(clicks)+SUM(impressions)/100 FROM page_daily "
                            "WHERE date >= date((SELECT MAX(date) FROM pull_log), '-90 days') GROUP BY page"))


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--site")
    ap.add_argument("--limit", type=int, default=600)
    ap.add_argument("--crawl")
    ap.add_argument("--urls")
    a = ap.parse_args()
    cfg = seoconf.load(a.site)
    crawl = a.crawl or os.path.join(seoconf.data_dir(cfg, "crawls"), "latest")
    if a.urls:
        urls = [l.strip() for l in open(a.urls) if l.strip()]
    else:
        db = sqlite3.connect(os.path.join(crawl, "crawl.sqlite"))
        rows = db.execute("SELECT url, in_sitemap FROM pages WHERE status=200 AND content_type LIKE '%html%'").fetchall()
        w = gsc_clicks(cfg)
        rows.sort(key=lambda r: (-(w.get(r[0], 0)), -r[1]))
        urls = [r[0] for r in rows]
    urls = urls[:a.limit]
    cache = sqlite3.connect(os.path.join(seoconf.data_dir(cfg), "inspect.sqlite"), check_same_thread=False)
    cache.execute("CREATE TABLE IF NOT EXISTS inspect(url TEXT, day TEXT, result TEXT, PRIMARY KEY(url, day))")
    today = dt.date.today().isoformat()
    have = {u for (u, t) in cache.execute("SELECT url, result FROM inspect WHERE day=?", (today,)) if valid(t)}
    todo = [u for u in urls if u not in have]
    print(f"{len(urls)} URLs, {len(todo)} to inspect today (cached: {len(urls) - len(todo)})", flush=True)
    s = seoconf.service_account_session(cfg, SCOPE)
    prop = cfg["site"]["gsc_property"]

    def one(u):
        try:
            r = s.post(API, json={"inspectionUrl": u, "siteUrl": prop}, timeout=60)
            return u, r.status_code, r.text
        except Exception as e:  # noqa: BLE001  transport failure stays a per-URL, retryable error (R69F-29)
            return u, None, seoconf.redact(f"{type(e).__name__}: {e}")

    errors, workers, sent = 0, 5, 0
    with ThreadPoolExecutor(max_workers=workers) as ex:
        for i in range(0, len(todo), workers):  # at most `workers` requests in flight (R69F-28)
            stop, batch = False, todo[i:i + workers]
            for u, code, text in ex.map(one, batch):
                sent += 1
                if code == 429:
                    stop = True
                    continue
                ok = code == 200 and valid(text)  # only a usable envelope is cached as success (RA35-14, R958-03)
                if ok:
                    cache.execute("INSERT OR REPLACE INTO inspect VALUES(?,?,?)", (u, today, text))
                else:
                    errors += 1
                    print(f"  {code or 'error'} {u}: {seoconf.redact(text)[:160]}", file=sys.stderr)
            cache.commit()
            if stop:
                done = {u for (u, t) in cache.execute("SELECT url, result FROM inspect WHERE day=?", (today,)) if valid(t)}
                left = sum(1 for u in todo if u not in done)  # same definition of "done" as dispatch (R212-03)
                print(f"Quota exhausted (429) after {sent} requests; {left} URLs left to inspect tomorrow.",  # RA35-15
                      file=sys.stderr)
                break
    out = {}
    for u in urls:
        row = next(((t, d) for t, d in cache.execute("SELECT result, day FROM inspect WHERE url=? ORDER BY day DESC", (u,))
                    if valid(t)), None)
        if not row:
            continue
        try:
            ir = json.loads(row[0]).get("inspectionResult", {}).get("indexStatusResult", {})
        except ValueError:
            continue
        out[u] = {k: ir.get(k) for k in ("verdict", "coverageState", "robotsTxtState", "indexingState",
                                         "pageFetchState", "lastCrawlTime", "googleCanonical", "userCanonical",
                                         "crawledAs", "sitemap", "referringUrls")} | {"inspected": row[1]}
    json.dump(out, open(os.path.join(crawl, "inspection.json"), "w"), indent=1)
    cov = {}
    for v in out.values():
        cov[v.get("coverageState")] = cov.get(v.get("coverageState"), 0) + 1
    print(f"Inspected {len(out)} URLs ({errors} errors). Coverage states:")
    for k, n in sorted(cov.items(), key=lambda x: -x[1]):
        print(f"  {n:4}  {k}")


if __name__ == "__main__":
    main()
