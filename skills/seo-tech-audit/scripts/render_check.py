#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = ["playwright>=1.48", "selectolax>=1.0", "httpx>=0.27"]
# ///
"""Compare raw HTML (from the crawl) with the browser-rendered DOM for one page per template.

A template is host + first path segment (locale prefixes are folded in). The check catches content, links,
titles, canonicals or robots directives that exist only after JavaScript runs, or that JavaScript changes.
Uses the installed Google Chrome (channel 'chrome'); set --channel '' to use Playwright's own Chromium.

Output: <crawl dir>/render.json. Usage: render_check.py [--site S] [--max 30]
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sqlite3
import sys
import urllib.parse

from playwright.sync_api import sync_playwright
from selectolax.lexbor import LexborHTMLParser

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import seoconf  # noqa: E402

UA = "Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0 Mobile Safari/537.36 seo-tech-audit"


def template(url, locales):
    u = urllib.parse.urlsplit(url)
    segs = [s for s in u.path.split("/") if s]
    if segs and segs[0] in locales:
        segs = segs[1:]
    return f"{u.netloc}/{segs[0] if segs else ''}"


def facts(html):
    t = LexborHTMLParser(html)
    def a(sel, at):
        n = t.css_first(sel)
        return n.attributes.get(at) if n else None
    body = t.body
    if body:
        for x in body.css("script, style, noscript, svg, template"):
            x.decompose()
    title = t.css_first("title")
    return {"title": title.text(strip=True) if title else None, "canonical": a('link[rel="canonical"]', "href"),
            "robots": a('meta[name="robots"]', "content"), "h1": len(t.css("h1")),
            "links": len(t.css("a[href]")), "words": len(re.findall(r"\w+", body.text(separator=" "))) if body else 0}


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--site")
    ap.add_argument("--crawl")
    ap.add_argument("--max", type=int, default=30)
    ap.add_argument("--channel", default="chrome")
    a = ap.parse_args()
    cfg = seoconf.load(a.site)
    crawl = a.crawl or os.path.join(seoconf.data_dir(cfg, "crawls"), "latest")
    db = sqlite3.connect(os.path.join(crawl, "crawl.sqlite"))
    rows = db.execute("SELECT url FROM pages WHERE status=200 AND content_type LIKE '%html%' ORDER BY depth, url").fetchall()
    locales = cfg["site"].get("locales", [])
    counts = {}
    for (u,) in rows:
        counts[template(u, locales)] = counts.get(template(u, locales), 0) + 1
    def group(u):  # one-off root slugs (e.g. blog posts at /slug/) share one "root page" template
        t = template(u, locales)
        return t if counts[t] > 1 else urllib.parse.urlsplit(u).netloc + "/<root page>"
    by_host = {}
    seen = set()
    for (u,) in rows:
        g = group(u)
        if g not in seen:
            seen.add(g)
            by_host.setdefault(urllib.parse.urlsplit(u).netloc, []).append(u)
    picked = []  # round-robin across hosts so every host gets samples
    while len(picked) < a.max and any(by_host.values()):
        for h in list(by_host):
            if by_host[h] and len(picked) < a.max:
                picked.append(by_host[h].pop(0))
    import httpx  # noqa: PLC0415
    out = []
    with sync_playwright() as p:
        b = p.chromium.launch(channel=a.channel or None, headless=True)
        ctx = b.new_context(user_agent=UA, viewport={"width": 412, "height": 915}, java_script_enabled=True)
        page = ctx.new_page()
        for u in picked:
            try:
                raw = httpx.get(u, headers={"User-Agent": UA}, timeout=30, follow_redirects=True).text
                page.goto(u, wait_until="load", timeout=45000)
                page.wait_for_timeout(2500)
                page.evaluate("document.querySelectorAll('video,audio').forEach(m=>{m.muted=true;m.pause()})")
                rendered = page.content()
            except Exception as e:  # noqa: BLE001
                out.append({"url": u, "error": str(e)[:200]})
                continue
            fr, fd = facts(raw), facts(rendered)
            diffs = [k for k in ("title", "canonical", "robots") if (fr[k] or "") != (fd[k] or "")]
            if fd["words"] > 1.5 * max(fr["words"], 50):
                diffs.append("words")
            if fd["links"] > 1.5 * max(fr["links"], 5):
                diffs.append("links")
            out.append({"url": u, "template": group(u), "raw": fr, "rendered": fd, "differs": diffs})
            print(f"  {'DIFF ' + ','.join(diffs) if diffs else 'same':24} {u}", flush=True)
        b.close()
    json.dump(out, open(os.path.join(crawl, "render.json"), "w"), indent=1, ensure_ascii=False)
    print(f"Rendered {len(out)} template samples; {sum(1 for r in out if r.get('differs'))} differ from raw HTML")


if __name__ == "__main__":
    main()
