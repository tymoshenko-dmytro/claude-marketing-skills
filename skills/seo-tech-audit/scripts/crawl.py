#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = ["httpx>=0.27", "selectolax>=1.0"]
# ///
"""Crawl the site's hosts (from the site config) and store what a technical audit needs.

Seeds: [site].start_urls plus every URL in [site].sitemaps (sitemap indexes are followed).
Scope: only hosts in [site].hosts. robots.txt is respected. Redirects are followed by hand so the
chain is recorded. Page content is treated as data only.

Output: <data dir>/crawls/<UTC timestamp>/crawl.sqlite (+ robots_<host>.txt), and a 'latest' symlink.
Tables: pages (one row per requested URL), links (internal + external edges), sitemap_urls.

Usage: crawl.py [--site S] [--max-pages 3000] [--concurrency 6] [--delay 0.2]
"""
from __future__ import annotations

import argparse
import asyncio
import datetime as dt
import json
import os
import re
import sqlite3
import sys
import time
import urllib.parse
import gzip
import xml.etree.ElementTree as ET

import httpx
from selectolax.lexbor import LexborHTMLParser as HTMLParser

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import seoconf  # noqa: E402
from robots import Robots  # noqa: E402

UA = "Mozilla/5.0 (compatible; seo-tech-audit/1.0; site-owner audit)"
SCHEMA = """
CREATE TABLE pages(url TEXT PRIMARY KEY, depth INT, status INT, final_url TEXT, redirect_chain TEXT,
  content_type TEXT, ttfb_ms INT, bytes INT, title TEXT, meta_description TEXT, h1 TEXT, canonical TEXT,
  meta_robots TEXT, x_robots TEXT, html_lang TEXT, hreflang TEXT, jsonld_types TEXT, word_count INT,
  internal_links INT, external_links INT, images INT, images_no_alt INT, images_empty_alt INT, in_sitemap INT,
  blocked_by_robots INT, total_ms INT, link_errors TEXT,
  error TEXT, fetched_at TEXT);
CREATE TABLE links(src TEXT, dst TEXT, anchor TEXT, nofollow INT, internal INT);
CREATE TABLE sitemap_urls(sitemap TEXT, url TEXT, lastmod TEXT);
CREATE TABLE meta(key TEXT PRIMARY KEY, value TEXT);
"""


def norm(url: str) -> str:
    """Drop fragments; keep query strings (they can be distinct pages)."""
    u = urllib.parse.urlsplit(url.strip())
    path = u.path or "/"
    return urllib.parse.urlunsplit((u.scheme.lower(), u.netloc.lower(), path, u.query, ""))


def text_words(tree: HTMLParser) -> int:
    body = tree.body
    if body is None:
        return 0
    for tag in body.css("script, style, noscript, svg, template"):
        tag.decompose()
    return len(re.findall(r"\w+", body.text(separator=" ")))


def safe_join(base: str, href: str | None) -> str | None:
    try:
        return norm(urllib.parse.urljoin(base, href)) if href else None
    except ValueError:  # malformed URL such as "http://[" (R69F-17)
        return None


def parse(url: str, html: str, bad: list | None = None) -> tuple[dict, list[tuple[str, str, int]]]:
    t = HTMLParser(html)
    b = t.css_first("base[href]")
    base = safe_join(url, b.attributes.get("href")) if b else None
    base = base or url  # links resolve against the first valid <base href> (R69F-15)
    def attr(sel, a):
        n = t.css_first(sel)
        return n.attributes.get(a) if n else None
    title = t.css_first("title")
    hreflang = [{"lang": (n.attributes.get("hreflang") or "").strip(), "href": safe_join(base, n.attributes.get("href")) or ""}
                for n in t.css('link[rel="alternate"][hreflang]')]
    types = []
    for n in t.css('script[type="application/ld+json"]'):
        try:
            data = json.loads(n.text() or "null")
        except json.JSONDecodeError:
            types.append("INVALID_JSON")
            continue
        stack = data if isinstance(data, list) else [data]
        while stack:
            x = stack.pop()
            if isinstance(x, dict):
                ty = x.get("@type")
                types += ty if isinstance(ty, list) else ([ty] if ty else [])
                stack += x.get("@graph", []) if isinstance(x.get("@graph"), list) else []
    links = []
    for a in t.css("a[href]"):
        href = (a.attributes.get("href") or "").strip()
        if not href or href.startswith(("mailto:", "tel:", "javascript:", "#")):
            continue
        rel = (a.attributes.get("rel") or "").lower()
        dst = safe_join(base, href)
        if dst is None and bad is not None:
            bad.append(href[:100])  # RA35-09
        if dst and dst.startswith(("http://", "https://")):
            links.append((dst, (a.text(strip=True) or "")[:120], int("nofollow" in rel)))
    imgs = t.css("img")
    info = {
        "title": title.text(strip=True) if title else None,
        "meta_description": attr('meta[name="description"]', "content"),
        "h1": json.dumps([n.text(strip=True)[:200] for n in t.css("h1")], ensure_ascii=False),
        "canonical": safe_join(base, attr('link[rel="canonical"]', "href")),
        "meta_robots": attr('meta[name="robots"]', "content"),
        "html_lang": attr("html", "lang"),
        "hreflang": json.dumps(hreflang, ensure_ascii=False),
        "jsonld_types": json.dumps(sorted(set(map(str, types)))),
        "images": len(imgs),
        "images_no_alt": sum(1 for i in imgs if "alt" not in i.attributes),  # missing attribute only (R69F-20)
        "images_empty_alt": sum(1 for i in imgs if "alt" in i.attributes and not (i.attributes.get("alt") or "").strip()),
    }
    info["word_count"] = text_words(t)
    return info, links


class Crawler:
    def __init__(self, cfg, a, db):
        self.cfg, self.a, self.db = cfg, a, db
        self.hosts = set(cfg["site"]["hosts"])
        self.robots: dict[str, Robots | None] = {}  # None = policy unavailable, host not crawled
        self.seen: set[str] = set()
        self.queue: asyncio.Queue = asyncio.Queue()
        self.sitemap_set: set[str] = set()
        self.count = 0

    async def get_in_scope(self, client, url, hops=5):
        """GET following redirects by hand; every hop must stay on https/http and a configured host (RA35-06/07)."""
        trail = []
        for _ in range(hops + 1):
            r = await client.get(url, follow_redirects=False)
            trail.append([url, r.status_code])
            if r.status_code in (301, 302, 303, 307, 308) and "location" in r.headers:
                nxt = safe_join(url, r.headers["location"])
                sp = urllib.parse.urlsplit(nxt or "")
                if not nxt or sp.scheme not in ("http", "https") or sp.netloc not in self.hosts:
                    return None, trail + [[nxt, "not followed: out of scope"]]
                url = nxt
                continue
            return r, trail
        return None, trail + [[url, "not followed: redirect limit"]]

    async def load_robots(self, client, outdir):
        for h in self.hosts:
            note = None
            try:
                r, trail = await self.get_in_scope(client, f"https://{h}/robots.txt")
                if r is None:
                    txt, note = None, f"redirect not followed: {trail[-1]}"
                elif r.status_code == 200:
                    txt = r.text
                elif r.status_code == 429:  # rate limited: unknown policy, retry later (RA35-05)
                    txt, note = None, "HTTP 429"
                elif 400 <= r.status_code < 500:
                    txt = ""  # no robots.txt: everything allowed
                else:
                    txt, note = None, f"HTTP {r.status_code}"
            except httpx.HTTPError as e:
                txt, note = None, f"{type(e).__name__}"
            if txt is None:  # unavailable policy is not permission to crawl (R69F-14)
                self.robots[h] = None
                self.db.execute("INSERT OR REPLACE INTO meta VALUES(?,?)", (f"robots_unavailable:{h}", note))
                print(f"robots.txt for {h} unavailable ({note}); host skipped. Re-run later.", file=sys.stderr)
                continue
            open(os.path.join(outdir, f"robots_{h}.txt"), "w").write(txt)
            self.robots[h] = Robots(txt)

    def allowed(self, url: str) -> bool:
        u = urllib.parse.urlsplit(url)
        rb = self.robots.get(u.netloc)
        return u.scheme in ("http", "https") and u.netloc in self.hosts and rb is not None and rb.allowed("Googlebot", url)

    async def load_sitemaps(self, client):
        todo, done = list(self.cfg["site"].get("sitemaps", [])), set()
        while todo:
            sm = todo.pop()
            if sm in done:
                continue
            done.add(sm)
            try:
                if sm not in self.cfg["site"].get("sitemaps", []) and urllib.parse.urlsplit(sm).netloc not in self.hosts:
                    self.db.execute("INSERT INTO sitemap_urls VALUES(?,?,?)", (sm, None, "REJECTED child sitemap out of scope"))
                    continue
                r, trail = await self.get_in_scope(client, sm)
                if r is None:
                    self.db.execute("INSERT INTO sitemap_urls VALUES(?,?,?)", (sm, None, f"REJECTED {trail[-1]}"[:200]))
                    continue
                body = r.content
                if body[:2] == b"\x1f\x8b":  # gzipped sitemap file (R69F-16), capped at 50 MB
                    with gzip.GzipFile(fileobj=__import__("io").BytesIO(body)) as gz:
                        body = gz.read(50 * 1024 * 1024 + 1)
                    if len(body) > 50 * 1024 * 1024:
                        raise ValueError("sitemap larger than 50 MB uncompressed")
                root = ET.fromstring(body)
            except Exception as e:  # noqa: BLE001
                self.db.execute("INSERT INTO sitemap_urls VALUES(?,?,?)", (sm, None, f"ERROR {e}"[:200]))
                continue
            ns = {"s": "http://www.sitemaps.org/schemas/sitemap/0.9"}
            for loc in root.findall("s:sitemap/s:loc", ns):
                todo.append(loc.text.strip())
            for u in root.findall("s:url", ns):
                loc = u.find("s:loc", ns)
                lm = u.find("s:lastmod", ns)
                if loc is not None and loc.text:
                    url = norm(loc.text)
                    self.sitemap_set.add(url)
                    self.db.execute("INSERT INTO sitemap_urls VALUES(?,?,?)", (sm, url, lm.text if lm is not None else None))

    def enqueue(self, url, depth):
        host = urllib.parse.urlsplit(url).netloc
        if url in self.seen or host not in self.hosts or self.robots.get(host) is None or len(self.seen) >= self.a.max_pages:
            return
        self.seen.add(url)
        self.queue.put_nowait((url, depth))

    async def get(self, client, url):
        """Response, time to headers (ms) and total time (ms). Streams when the client supports it (R69F-18)."""
        t0 = time.monotonic()
        if hasattr(client, "stream"):
            async with client.stream("GET", url, follow_redirects=False) as r:
                ttfb = int((time.monotonic() - t0) * 1000)
                await r.aread()
        else:
            r = await client.get(url, follow_redirects=False)
            ttfb = int((time.monotonic() - t0) * 1000)
        return r, ttfb, int((time.monotonic() - t0) * 1000)

    async def fetch(self, client, url, depth):
        row = {"url": url, "depth": depth, "in_sitemap": int(url in self.sitemap_set),
               "fetched_at": dt.datetime.now(dt.UTC).isoformat(timespec="seconds")}
        if not self.allowed(url):
            row.update(blocked_by_robots=1)
            self.save(row, [])
            return
        chain, cur, links = [], url, []
        try:
            exhausted = True
            for _ in range(10):
                r, ttfb, total = await self.get(client, cur)
                if r.status_code in (301, 302, 303, 307, 308) and "location" in r.headers:
                    nxt = safe_join(cur, r.headers["location"])
                    chain.append({"url": cur, "status": r.status_code})
                    if not nxt or not self.allowed(nxt):  # every hop obeys scope and robots (R69F-12)
                        chain.append({"url": nxt, "status": None, "not_followed": "out of scope or blocked by robots.txt"})
                        cur = nxt
                        break
                    cur = nxt
                    continue
                exhausted = False
                break
            if exhausted and not (chain and chain[-1].get("not_followed")):  # never invent a status (RA35-08)
                chain.append({"url": cur, "status": None, "not_followed": "redirect limit (10 hops)"})
            row.update(status=chain[0]["status"] if chain else r.status_code, final_url=cur,
                       redirect_chain=json.dumps(chain), content_type=r.headers.get("content-type", ""),
                       ttfb_ms=ttfb, total_ms=total, bytes=len(r.content), x_robots=r.headers.get("x-robots-tag"))
            if chain and chain[-1].get("not_followed"):
                pass
            elif chain:
                row["final_status"] = r.status_code
                if cur:
                    self.enqueue(cur, depth)  # crawl the target too
            elif r.status_code == 200 and "html" in row["content_type"]:
                bad = []
                info, links = parse(cur, r.text, bad)
                row.update(info)
                if bad:
                    row["link_errors"] = json.dumps({"malformed_links": len(bad), "examples": bad[:5]})
                    print(f"malformed link(s) on {cur}: {bad[:3]}", file=sys.stderr)
                row["internal_links"] = sum(1 for l in links if urllib.parse.urlsplit(l[0]).netloc in self.hosts)
                row["external_links"] = len(links) - row["internal_links"]
                if depth < self.a.max_depth:
                    for l in links:
                        self.enqueue(l[0], depth + 1)
        except Exception as e:  # noqa: BLE001  one bad page must not stop the crawl (R69F-17)
            row["error"] = f"{type(e).__name__}: {e}"[:300]
        self.save(row, links)

    def save(self, row, links):
        cols = [c for c in row if c != "final_status"]
        if "final_status" in row:
            row["redirect_chain"] = json.dumps(json.loads(row["redirect_chain"]) + [{"url": row["final_url"], "status": row["final_status"]}])
        self.db.execute(f"INSERT OR REPLACE INTO pages({','.join(cols)}) VALUES({','.join('?' * len(cols))})",
                        [row[c] for c in cols])
        self.db.executemany("INSERT INTO links VALUES(?,?,?,?,?)",
                            [(row["url"], d, an, nf, int(urllib.parse.urlsplit(d).netloc in self.hosts)) for d, an, nf in links])
        self.count += 1
        if self.count % 50 == 0:
            self.db.commit()
            print(f"  {self.count} fetched, {self.queue.qsize()} queued", flush=True)

    async def worker(self, client):
        while True:
            url, depth = await self.queue.get()
            try:
                await self.fetch(client, url, depth)
                await asyncio.sleep(self.a.delay)
            except Exception as e:  # noqa: BLE001
                print(f"worker error on {url}: {e}", file=sys.stderr)
            finally:
                self.queue.task_done()

    async def run(self, outdir):
        limits = httpx.Limits(max_connections=self.a.concurrency)
        async with httpx.AsyncClient(headers={"User-Agent": UA, "Accept-Language": "en"}, timeout=30,
                                     limits=limits, http2=False) as client:
            await self.load_robots(client, outdir)
            await self.load_sitemaps(client)
            for u in self.cfg["site"].get("start_urls", []):
                self.enqueue(norm(u), 0)
            for u in sorted(self.sitemap_set):
                self.enqueue(u, 1)
            workers = [asyncio.create_task(self.worker(client)) for _ in range(self.a.concurrency)]
            await self.queue.join()
            for w in workers:
                w.cancel()
        self.db.commit()


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--site")
    ap.add_argument("--max-pages", type=int, default=3000)
    ap.add_argument("--max-depth", type=int, default=10)
    ap.add_argument("--concurrency", type=int, default=6)
    ap.add_argument("--delay", type=float, default=0.2)
    a = ap.parse_args()
    cfg = seoconf.load(a.site)
    stamp = dt.datetime.now(dt.UTC).strftime("%Y%m%dT%H%M%SZ")
    outdir = seoconf.data_dir(cfg, "crawls", stamp)
    db = sqlite3.connect(os.path.join(outdir, "crawl.sqlite"))
    db.executescript(SCHEMA)
    db.executemany("INSERT INTO meta VALUES(?,?)", [("started", stamp), ("hosts", json.dumps(cfg["site"]["hosts"])),
                                                    ("user_agent", UA)])
    c = Crawler(cfg, a, db)
    t0 = time.time()
    asyncio.run(c.run(outdir))
    db.execute("INSERT INTO meta VALUES('finished', ?)", (dt.datetime.now(dt.UTC).isoformat(timespec="seconds"),))
    db.execute("INSERT INTO meta VALUES('capped', ?)", (str(len(c.seen) >= a.max_pages),))
    db.commit()
    latest = os.path.join(seoconf.data_dir(cfg, "crawls"), "latest")
    if os.path.islink(latest):
        os.unlink(latest)
    os.symlink(outdir, latest)
    n = db.execute("SELECT COUNT(*), SUM(status=200), SUM(status BETWEEN 300 AND 399), SUM(status>=400), "
                   "SUM(error IS NOT NULL), SUM(blocked_by_robots) FROM pages").fetchone()
    print(f"Crawled {n[0]} URLs in {int(time.time() - t0)}s: 200={n[1]} 3xx={n[2]} 4xx/5xx={n[3]} errors={n[4]} "
          f"robots-blocked={n[5]}, sitemap URLs={len(c.sitemap_set)}\n{outdir}")


if __name__ == "__main__":
    main()
