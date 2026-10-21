#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = ["requests>=2.31"]
# ///
"""Real-user Core Web Vitals from the Chrome UX Report (CrUX) API: p75 over the last 28 days.

Queries each host origin (all devices, PHONE, DESKTOP), the origin's 40-week history (PHONE), and the top
URLs by GSC clicks when they have enough traffic to be in CrUX. Needs CRUX_API_KEY (free; Google Cloud API key
restricted to the Chrome UX Report API). Lighthouse lab scores are not a substitute for this data.

Output: <crawl dir>/cwv.json. Usage: cwv.py [--site S] [--top-urls 20]
"""
from __future__ import annotations

import argparse
import json
import os
import sqlite3
import sys

import requests

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import seoconf  # noqa: E402

API = "https://chromeuxreport.googleapis.com/v1/records:"
METRICS = {"largest_contentful_paint": (2500, 4000), "interaction_to_next_paint": (200, 500),
           "cumulative_layout_shift": (0.1, 0.25), "experimental_time_to_first_byte": (800, 1800)}


def rate(metric, p75):
    good, poor = METRICS[metric]
    v = float(p75)
    return "good" if v <= good else ("poor" if v > poor else "needs improvement")


def query(key, method, body):
    r = requests.post(API + method, params={"key": key}, json=body, timeout=60)
    if r.status_code == 404:
        return None  # not enough real-user data
    if r.status_code != 200:
        sys.exit(seoconf.redact(f"CrUX {r.status_code}: {r.text}")[:300])  # redact, then cut (R958-01)
    return r.json()["record"]


def summarize(rec):
    if not rec:
        return {"status": "not enough real-user data in CrUX"}
    out = {"period_end": "{year}-{month:02d}-{day:02d}".format(**rec["collectionPeriod"]["lastDate"])}
    for m in METRICS:
        if m in rec["metrics"]:
            p = rec["metrics"][m]["percentiles"]["p75"]
            out[m] = {"p75": p, "rating": rate(m, p)}
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--site")
    ap.add_argument("--top-urls", type=int, default=20)
    ap.add_argument("--crawl")
    a = ap.parse_args()
    cfg = seoconf.load(a.site)
    key = seoconf.need_key("CRUX_API_KEY", "crux-api.md")
    crawl = a.crawl or os.path.join(seoconf.data_dir(cfg, "crawls"), "latest")
    res = {"origins": {}, "urls": {}}
    for h in cfg["site"]["hosts"]:
        o = f"https://{h}"
        res["origins"][o] = {ff or "ALL": summarize(query(key, "queryRecord", {"origin": o, **({"formFactor": ff} if ff else {})}))
                             for ff in (None, "PHONE", "DESKTOP")}
        hist = query(key, "queryHistoryRecord", {"origin": o, "formFactor": "PHONE"})
        if hist:
            res["origins"][o]["history_phone_p75"] = {
                m: hist["metrics"][m]["percentilesTimeseries"]["p75s"] for m in METRICS if m in hist["metrics"]}
    gsc = os.path.join(seoconf.expand(cfg["data"]["dir"]), "gsc.sqlite")
    if os.path.exists(gsc):
        con = sqlite3.connect(gsc)
        top = [r[0] for r in con.execute("""SELECT page FROM page_daily WHERE date >= date((SELECT MAX(date) FROM pull_log), '-28 days')
                                            GROUP BY page ORDER BY SUM(clicks) DESC LIMIT ?""", (a.top_urls,))]
        for u in top:
            if any(f"//{h}" in u for h in cfg["site"]["hosts"]):
                res["urls"][u] = summarize(query(key, "queryRecord", {"url": u, "formFactor": "PHONE"}))
    json.dump(res, open(os.path.join(crawl, "cwv.json"), "w"), indent=1)
    for o, d in res["origins"].items():
        for ff in ("ALL", "PHONE", "DESKTOP"):
            s = d.get(ff, {})
            print(o, ff, {m.split('_')[0] + "_" + m.split('_')[-1]: (v["p75"], v["rating"]) for m, v in s.items() if isinstance(v, dict)})
    print(f"URL-level records: {sum(1 for v in res['urls'].values() if 'period_end' in v)}/{len(res['urls'])}")


if __name__ == "__main__":
    main()
