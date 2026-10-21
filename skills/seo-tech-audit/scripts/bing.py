#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = ["requests>=2.31"]
# ///
"""Bing Webmaster Tools data for the audit: pages Bing shows per host, crawl issues, top queries.

Needs BING_WMT_API_KEY (Bing Webmaster Tools > Settings > API access) and [site].bing_site.
Bing's AI Performance report has no public API; export it from the UI if needed.

Output: <crawl dir>/bing.json. Usage: bing.py [--site S]
"""
from __future__ import annotations

import argparse
import collections
import json
import os
import sys
import urllib.parse

import requests

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import seoconf  # noqa: E402

API = "https://ssl.bing.com/webmaster/api.svc/json/"


def call(method, key, site):
    try:
        r = requests.get(API + method, params={"siteUrl": site, "apikey": key}, timeout=60)
    except requests.RequestException as e:
        return {"error": seoconf.redact(f"{type(e).__name__}: {e}")[:200]}  # redact first, then cut (RA35-16)
    if r.status_code != 200:
        return {"error": seoconf.redact(f"{r.status_code} {r.text}")[:200]}  # redact the whole body, then cut (RA35-16)
    return r.json().get("d")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--site")
    ap.add_argument("--crawl")
    a = ap.parse_args()
    cfg = seoconf.load(a.site)
    key = seoconf.need_key("BING_WMT_API_KEY", "bing-webmaster.md")
    site = cfg["site"].get("bing_site") or sys.exit("[site].bing_site missing in config")
    crawl = a.crawl or os.path.join(seoconf.data_dir(cfg, "crawls"), "latest")
    pages = call("GetPageStats", key, site)
    issues = call("GetCrawlIssues", key, site)
    queries = call("GetQueryStats", key, site)
    by_host = collections.Counter()
    excluded = []
    if isinstance(pages, list):
        agg = collections.defaultdict(lambda: [0, 0])
        for p in pages:
            agg[p["Query"]][0] += p.get("Impressions", 0)
            agg[p["Query"]][1] += p.get("Clicks", 0)
        for url, (imp, clk) in agg.items():
            h = urllib.parse.urlsplit(url).netloc
            by_host[h] += 1
            if h in cfg["site"].get("excluded_hosts", []):
                excluded.append({"url": url, "impressions": imp, "clicks": clk})
    out = {"site": site, "page_stats_error": pages.get("error") if isinstance(pages, dict) else None,  # R69F-31
           "pages_by_host": dict(by_host) if isinstance(pages, list) else None, "excluded_host_pages": sorted(excluded, key=lambda r: -r["impressions"]),
           "crawl_issues": issues, "top_queries": sorted(queries, key=lambda q: -q.get("Impressions", 0))[:50] if isinstance(queries, list) else queries}
    json.dump(out, open(os.path.join(crawl, "bing.json"), "w"), indent=1, ensure_ascii=False)
    if isinstance(pages, dict):
        print("Bing page stats unavailable:", pages.get("error"))
    print("Bing pages by host:", dict(by_host))
    print("Pages on excluded hosts:", len(excluded))
    print("Crawl issues:", len(issues) if isinstance(issues, list) else issues)


if __name__ == "__main__":
    main()
