#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = ["httpx>=0.27"]
# ///
"""Turn the collected evidence into findings, a report and developer tickets.

Reads the crawl folder (crawl.sqlite, robots_*.txt, and optional inspection.json, cwv.json, bing.json,
render.json) plus the gsc-insights archive (<data>/gsc.sqlite) for business exposure. Every finding carries
its rule, severity, affected URLs, evidence and the GSC clicks/impressions of those URLs (last 28 days).
Severity is about the failure; priority = severity adjusted by exposure. No traffic uplift is predicted.

Output in the crawl folder: findings.json, report.md, tickets.md.
Usage: audit.py [--site S] [--crawl DIR]
"""
from __future__ import annotations

import argparse
import collections
import json
import os
import re
import sqlite3
import sys
import urllib.parse

import httpx

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import seoconf  # noqa: E402
from robots import Robots  # noqa: E402

SEV = {"critical": 4, "high": 3, "medium": 2, "low": 1, "info": 0}
# language[-Script][-REGION], e.g. en, en-GB, zh-Hans, zh-Hans-CN, es-419 (R69F-24)
LANG_RX = re.compile(r"^[a-z]{2,3}(-[a-z]{4})?(-([a-z]{2}|\d{3}))?$|^x-default$", re.I)
IGNORE_PATH = re.compile(r"/cdn-cgi/")  # Cloudflare internals (email obfuscation etc.)


def load_json(crawl, name):
    p = os.path.join(crawl, name)
    return json.load(open(p)) if os.path.exists(p) else None


def key(u: str) -> str:
    """Comparable URL: lowercase host, no trailing slash, no fragment."""
    s = urllib.parse.urlsplit(u)
    return urllib.parse.urlunsplit((s.scheme, s.netloc.lower(), s.path.rstrip("/") or "/", s.query, ""))


class Audit:
    def __init__(self, cfg, crawl):
        self.cfg, self.crawl = cfg, crawl
        self.db = sqlite3.connect(os.path.join(crawl, "crawl.sqlite"))
        self.db.row_factory = sqlite3.Row
        self.pages = {r["url"]: dict(r) for r in self.db.execute("SELECT * FROM pages")}
        self.by_key = {key(u): p for u, p in self.pages.items()}
        self.hosts = set(cfg["site"]["hosts"])
        self.findings = []
        self.exposure_days = 0
        self.exposure = self._exposure()
        self.exposure_complete = self.exposure_days == 28

    def _exposure(self):
        p = os.path.join(seoconf.expand(self.cfg["data"]["dir"]), "gsc.sqlite")
        if not os.path.exists(p):
            return {}
        con = sqlite3.connect(p)
        out = collections.defaultdict(lambda: [0, 0])
        last = con.execute("SELECT MAX(date) FROM pull_log WHERE final=1").fetchone()[0]
        if not last:
            return {}
        n = con.execute("SELECT COUNT(*) FROM pull_log WHERE final=1 AND date > date(?, '-28 days') AND date <= ?",
                        (last, last)).fetchone()[0]
        self.exposure_days = n  # fewer than 28 final days = partial exposure (RA35-12)
        # exactly the 28 final days ending at the last final day; provisional days never count (R69F-22)
        for page, c, i in con.execute("""SELECT page, SUM(clicks), SUM(impressions) FROM page_daily
                                         WHERE date > date(?, '-28 days') AND date <= ?
                                           AND date IN (SELECT date FROM pull_log WHERE final=1)
                                         GROUP BY page""", (last, last)):
            out[key(page)][0] += c
            out[key(page)][1] += i
        return out

    def exp(self, urls):
        keys = {key(u) for u in urls}  # /a and /a/ are one page (R69F-23)
        c = sum(self.exposure.get(k, [0, 0])[0] for k in keys)
        i = sum(self.exposure.get(k, [0, 0])[1] for k in keys)
        return c, i

    def add(self, rule, sev, title, urls, why, fix, evidence=None, owner="Frontend"):
        urls = sorted(set(urls))
        if not urls and sev != "info":
            return
        c, i = self.exp(urls)
        # a partial exposure total never raises priority and is labelled (RA35-12)
        score = SEV[sev] + (1 if self.exposure_complete and c >= 50 else 0)
        prio = "P1" if score >= 4 else "P2" if score == 3 else "P3" if score >= 1 else "info"
        self.findings.append({"rule": rule, "severity": sev, "priority": prio, "title": title, "count": len(urls),
                              "gsc_clicks_28d": c, "gsc_impressions_28d": i, "exposure_complete": self.exposure_complete, "why": why, "fix": fix, "owner": owner,
                              "urls": urls[:200], "evidence": evidence or {}})

    # ---------- helpers ----------
    def html200(self):
        return [p for p in self.pages.values() if p["status"] == 200 and "html" in (p["content_type"] or "")]

    @staticmethod
    def noindex(p) -> bool:
        """meta robots / X-Robots-Tag tokens; 'none' means noindex, nofollow (R69F-26)."""
        toks = set(re.split(r"[\s,]+", ((p.get("meta_robots") or "") + "," + (p.get("x_robots") or "")).lower()))
        return bool(toks & {"noindex", "none"})

    def indexable(self, p):
        if self.noindex(p):
            return False
        can = p.get("canonical")
        return not can or key(can) == key(p["url"])

    # ---------- rules ----------
    def r_status_links(self):
        bad = {u: p for u, p in self.pages.items() if (p["status"] or 0) >= 400 and not IGNORE_PATH.search(u)}
        src = collections.defaultdict(set)
        for s, d in self.db.execute("SELECT src, dst FROM links WHERE internal=1"):
            if d in bad:
                src[d].add(s)
        self.add("R01", "high", "Internal links point to error pages", [u for u in bad if src[u]],
                 "Links to 4xx/5xx pages waste crawl and send users to dead ends.",
                 "Fix or remove each link; restore the page or redirect it to the closest live page.",
                 {u: {"status": bad[u]["status"], "linked_from": sorted(src[u])[:5]} for u in list(bad)[:50] if src[u]})
        cf = [u for u, p in self.pages.items() if IGNORE_PATH.search(u) and (p["status"] or 0) >= 400]
        if cf:
            self.add("R01b", "info", "Cloudflare email-protection links return 404 to crawlers", cf,
                     "Cloudflare rewrites e-mail addresses into /cdn-cgi/l/email-protection links; bots see 404s.",
                     "Optional: turn off Email Address Obfuscation in Cloudflare for these hosts, or ignore.", owner="Platform")

    def r_redirects(self):
        chains, linked = [], collections.defaultdict(set)
        for u, p in self.pages.items():
            ch = json.loads(p["redirect_chain"] or "[]")
            if len(ch) > 2:  # chain stores every hop incl. final
                chains.append(u)
        redirecting = {u for u, p in self.pages.items() if json.loads(p["redirect_chain"] or "[]")}
        for s, d in self.db.execute("SELECT src, dst FROM links WHERE internal=1"):
            if d in redirecting:
                linked[d].add(s)
        self.add("R02", "medium", "Redirect chains (more than one hop)", chains,
                 "Each hop adds latency and can drop signals; Google follows up to 10 hops but chains decay.",
                 "Point the first URL straight to the final destination.",
                 {u: json.loads(self.pages[u]["redirect_chain"]) for u in chains[:30]})
        self.add("R02b", "low", "Internal links point to redirecting URLs", list(linked),
                 "Internal links should go straight to the final URL.",
                 "Update the links to the final URLs.", {u: sorted(s)[:5] for u, s in list(linked.items())[:30]})

    def r_sitemap(self):
        sm = {r[0] for r in self.db.execute("SELECT url FROM sitemap_urls WHERE url IS NOT NULL")}
        errs = [r[0] for r in self.db.execute("SELECT sitemap FROM sitemap_urls WHERE url IS NULL")]
        bad = []
        for u in sm:
            p = self.pages.get(u)
            if not p:
                continue
            if p["status"] != 200 or not self.indexable(p) or p["blocked_by_robots"]:
                bad.append(u)
        self.add("R03", "high", "Sitemap lists URLs that are not indexable 200 pages", bad + errs,
                 "Sitemaps should list only canonical, indexable 200 URLs; others dilute the signal.",
                 "Remove redirects, errors, noindex and canonicalised URLs from the sitemap.",
                 {u: {"status": self.pages[u]["status"], "robots": self.pages[u]["meta_robots"],
                      "canonical": self.pages[u]["canonical"]} for u in bad[:30] if u in self.pages}, owner="Backend")
        missing = [p["url"] for p in self.html200() if self.indexable(p) and not p["in_sitemap"]]
        self.add("R04", "medium", "Indexable pages missing from the sitemap", missing,
                 "Pages outside the sitemap are discovered later and get less crawl attention.",
                 "Add them to the sitemap, or noindex/remove them if they should not be in search.", owner="Backend")

    def r_noindex(self):
        ni = [p["url"] for p in self.html200() if self.noindex(p)]
        self.add("R05", "medium", "Pages with noindex (review that each one is intended)", ni,
                 "A noindex on an acquisition page removes it from search; on utility pages it is correct.",
                 "Confirm each URL; remove noindex from pages meant to rank.",
                 {u: {"robots": self.pages[u]["meta_robots"], "in_sitemap": self.pages[u]["in_sitemap"]} for u in ni[:40]})

    def r_canonical(self, insp):
        missing, other, bad_target = [], [], []
        for p in self.html200():
            c = p["canonical"]
            if not c:
                missing.append(p["url"])
            elif key(c) != key(p["url"]):
                t = self.by_key.get(key(c))
                (bad_target if t and (t["status"] != 200 or not self.indexable(t)) else other).append(p["url"])
        self.add("R06", "medium", "Pages without a canonical tag", missing,
                 "Without a self-canonical, Google picks one itself, and parameter or case variants can compete.",
                 "Add <link rel=canonical> pointing to the page's own clean URL on every indexable template.")
        self.add("R06b", "info", "Pages canonicalised to another URL", other,
                 "Expected for duplicates and alternates; a mistake on unique pages.", "Review the list.",
                 {u: self.pages[u]["canonical"] for u in other[:40]})
        self.add("R06c", "high", "Canonical points to a non-200 or noindex URL", bad_target,
                 "A broken canonical target sends contradictory signals.", "Point the canonical to a live, indexable URL.",
                 {u: self.pages[u]["canonical"] for u in bad_target[:40]})
        if insp:
            diff = [u for u, r in insp.items() if r.get("googleCanonical") and r.get("userCanonical")
                    and key(r["googleCanonical"]) != key(r["userCanonical"])]
            self.add("R06d", "high", "Google chose a different canonical than the page declares", diff,
                     "Google ignores the declared canonical, usually because of duplicate content or conflicting signals.",
                     "Compare both URLs; align internal links, sitemap and redirects with the intended canonical.",
                     {u: {"google": insp[u]["googleCanonical"], "declared": insp[u]["userCanonical"]} for u in diff[:40]})

    def r_index_status(self, insp):
        if not insp:
            self.add("R07", "info", "URL Inspection not run", [], "Run inspect_urls.py to add Google's index view.", "")
            return
        want = {p["url"] for p in self.html200() if self.indexable(p)}
        groups = collections.defaultdict(list)
        missing = []
        for u, r in insp.items():
            if u not in want:
                continue
            if r.get("verdict") not in ("PASS", "FAIL", "NEUTRAL", "PARTIAL") or (r.get("coverageState") or "Unknown") == "Unknown":
                missing.append(u)  # no usable result is not evidence of non-indexing (R69F-21)
            elif r.get("verdict") != "PASS":
                groups[r["coverageState"]].append(u)
        if missing:
            self.add("R07x", "info", "URL Inspection returned no usable result", missing,
                     "The API answered without an index verdict; nothing is claimed about these URLs.",
                     "Re-run inspect_urls.py later.")
        for state, urls in groups.items():
            sev = "high" if state in ("URL is unknown to Google", "Discovered - currently not indexed",
                                       "Crawled - currently not indexed") else "medium"
            self.add("R07", sev, f"Indexable pages not in Google's index: {state}", urls,
                     {"URL is unknown to Google": "Google has not found these pages; they lack internal links or sitemap entries Google trusts.",
                      "Discovered - currently not indexed": "Google knows the URLs but has not crawled them yet.",
                      "Crawled - currently not indexed": "Google crawled and chose not to index; usually weak or duplicate content.",
                      "Excluded by ‘noindex’ tag": "Google's last crawl (see evidence dates) saw a noindex the page no longer has; it clears on the next crawl."
                      }.get(state, "Google does not index these pages."),
                     "Strengthen internal links from indexed pages, keep them in the sitemap, and improve unique value. "
                     "Re-submitting alone does not help.", {u: insp[u].get("lastCrawlTime") for u in urls[:40]}, owner="Content")

    def r_tracking_links(self):
        rx = re.compile(r"[?&](_gl|utm_[a-z]+|_ga|gclid|fbclid)=")
        links = collections.defaultdict(set)
        for s, d in self.db.execute("SELECT src, dst FROM links WHERE internal=1"):
            if rx.search(d):
                links[d].add(s)
        self.add("R08", "medium", "Internal links carry tracking parameters (_gl, utm_…)", list(links),
                 "Hard-coded tracking parameters create duplicate URLs, are blocked by robots.txt and pollute analytics sessions.",
                 "Replace these hrefs with clean URLs (the GA cross-domain linker adds _gl at click time by itself).",
                 {u: sorted(s)[:5] for u, s in list(links.items())[:30]})

    def r_excluded_hosts(self, bing):
        ex = set(self.cfg["site"].get("excluded_hosts", []))
        gsc = [u for u in self.exposure if urllib.parse.urlsplit(u).netloc in ex and self.exposure[u][1] > 0]
        bing_urls = [r["url"] for r in (bing or {}).get("excluded_host_pages", [])]
        self.add("R09", "high", "App/old hosts appear in search results", gsc + bing_urls,
                 "Logins, app screens and the old site compete with the marketing site and send searchers to the wrong place.",
                 "Add noindex (meta or X-Robots-Tag) to app/platform pages that should not rank, redirect old.* to the "
                 "matching www pages, and keep robots.txt open so Google can see the noindex.",
                 {"google": {u: self.exposure[u] for u in gsc[:200]}, "bing": (bing or {}).get("excluded_host_pages", [])[:200]},
                 owner="Platform")

    def r_variants(self):
        canon_hosts = {h for h in self.hosts}
        vs = [u for u in self.exposure if u.startswith("http://") or
              (urllib.parse.urlsplit(u).netloc not in self.hosts and
               urllib.parse.urlsplit(u).netloc.replace("www.", "") in {h.replace("www.", "") for h in self.hosts})]
        bad = {}
        for u in vs[:40]:
            cur, hops, ok, trail = u, 0, False, []
            try:
                while hops < 5:  # follow the chain; it must end on https + a configured host with a 200 (R69F-27)
                    r = httpx.get(cur, follow_redirects=False, timeout=20)
                    trail.append([cur, r.status_code])
                    if r.status_code in (301, 308) and "location" in r.headers:
                        nxt = urllib.parse.urljoin(cur, r.headers["location"])
                        sp = urllib.parse.urlsplit(nxt)
                        own = {urllib.parse.urlsplit(u).netloc} | canon_hosts  # never request other hosts (RA35-13)
                        if nxt == cur or sp.scheme not in ("http", "https") or sp.netloc not in own:
                            trail.append([nxt, "not followed"])
                            break
                        cur, hops = nxt, hops + 1
                        continue
                    sp = urllib.parse.urlsplit(cur)
                    ok = hops > 0 and r.status_code == 200 and sp.scheme == "https" and sp.netloc in canon_hosts
                    break
            except httpx.HTTPError as e:
                trail.append([cur, type(e).__name__])
            if not ok:
                bad[u] = trail
        self.add("R10", "medium", "Protocol or host variants get impressions without a permanent redirect to the canonical host",
                 list(bad), "http:// or non-www URLs should 301 to the https canonical host so signals consolidate.",
                 "Add 301 redirects from every variant straight to the https URL on the canonical host.", bad, owner="Platform")

    def r_onpage(self):
        pages = [p for p in self.html200() if self.indexable(p)]
        titles = collections.defaultdict(list)
        descs = collections.defaultdict(list)
        for p in pages:
            titles[(p["title"] or "").strip()].append(p["url"])
            descs[(p["meta_description"] or "").strip()].append(p["url"])
        self.add("R11", "medium", "Missing or duplicate titles",
                 [u for t, us in titles.items() if not t or len(us) > 1 for u in us],
                 "Titles are the main snippet text and a relevance signal.", "Write a unique title per page.",
                 {t or "(missing)": us[:5] for t, us in titles.items() if not t or len(us) > 1})
        self.add("R11b", "low", "Titles longer than 60 or shorter than 20 characters",
                 [p["url"] for p in pages if p["title"] and not 20 <= len(p["title"]) <= 60],
                 "Long titles are truncated or rewritten by Google; very short ones waste the slot.",
                 "Keep the key phrase in the first 50-60 characters.",
                 {p["url"]: len(p["title"]) for p in pages if p["title"] and not 20 <= len(p["title"]) <= 60})
        self.add("R12", "low", "Meta descriptions missing, duplicate, or outside 70-160 characters",
                 [p["url"] for p in pages if not p["meta_description"] or not 70 <= len(p["meta_description"]) <= 160
                  or len(descs[(p["meta_description"] or "").strip()]) > 1],
                 "Google often writes its own snippet, but a good description lifts CTR where it is used.",
                 "Write a unique 120-160 character description that answers the page's main query.",
                 {p["url"]: len(p["meta_description"] or "") for p in pages if not p["meta_description"]
                  or not 70 <= len(p["meta_description"]) <= 160}, owner="Content")
        h1 = {p["url"]: len(json.loads(p["h1"] or "[]")) for p in pages}
        self.add("R13", "low", "Pages with no H1 or several H1s", [u for u, n in h1.items() if n != 1],
                 "One clear H1 states the page topic.", "Use exactly one H1 per page.",
                 {u: n for u, n in h1.items() if n != 1}, owner="Frontend")
        self.add("R14", "low", "Thin pages (under 250 words of visible text)",
                 [p["url"] for p in pages if (p["word_count"] or 0) < 250],
                 "Very short pages rarely rank unless the intent is navigational.",
                 "Expand with useful content or noindex utility pages.",
                 {p["url"]: p["word_count"] for p in pages if (p["word_count"] or 0) < 250}, owner="Content")
        self.add("R15", "low", "Images without alt text (pages with 3+)",
                 [p["url"] for p in pages if (p["images_no_alt"] or 0) >= 3],
                 "Alt text helps image search and accessibility.", "Add descriptive alt text; empty alt only for decoration.",
                 {p["url"]: f'{p["images_no_alt"]}/{p["images"]}' for p in pages if (p["images_no_alt"] or 0) >= 3}, owner="Content")
        badjs = [p["url"] for p in pages if "INVALID_JSON" in (p["jsonld_types"] or "")]
        self.add("R16", "medium", "Invalid JSON-LD structured data", badjs,
                 "Unparseable JSON-LD is ignored.", "Fix the JSON syntax.")
        faq = [p["url"] for p in pages if "FAQPage" in (p["jsonld_types"] or "")]
        self.add("R16b", "info", "FAQPage markup present", faq,
                 "Google stopped showing FAQ rich results on 7 May 2026; the markup no longer earns extra space.",
                 "Keep it if harmless; do not add more for SERP reasons.")

    def r_hreflang(self):
        locales = set(self.cfg["site"].get("locales", []))
        issues = collections.defaultdict(dict)
        decl = {}
        for p in self.html200():
            hl = json.loads(p["hreflang"] or "[]")
            if hl:
                decl[key(p["url"])] = {h["lang"].lower(): key(h["href"]) for h in hl}
        for src, m in decl.items():
            if src not in m.values():
                issues["no self-reference"][src] = sorted(m)
            for lang, tgt in m.items():
                if not LANG_RX.match(lang):
                    issues["invalid language code"][src] = lang
                t = self.by_key.get(tgt)
                if not t:
                    issues["target not crawled (outside scope or blocked)"][tgt] = lang
                    continue
                if t["status"] != 200 or not self.indexable(t):
                    issues["target is not an indexable 200"][tgt] = {"status": t["status"], "canonical": t["canonical"],
                                                                     "robots": t["meta_robots"]}
                if lang != "x-default" and tgt != src and src not in decl.get(tgt, {}).values():
                    issues["missing return link"].setdefault(src, []).append({"to": tgt, "lang": lang})  # real URL keys (R69F-25)
                hl_lang = (t.get("html_lang") or "").lower().split("-")[0]
                if lang not in ("x-default",) and hl_lang and hl_lang != lang.split("-")[0]:
                    issues["hreflang code differs from the target's <html lang>"][tgt] = {"hreflang": lang, "html_lang": t["html_lang"]}
        loc_counts = collections.Counter()
        for p in self.html200():
            seg = urllib.parse.urlsplit(p["url"]).path.strip("/").split("/")[0]
            loc_counts[seg if seg in locales else "(default)"] += 1
        for kind, ev in issues.items():
            self.add("R17", "medium" if kind != "target not crawled (outside scope or blocked)" else "low",
                     f"hreflang: {kind}", list(ev), "hreflang only works when every version links to every other "
                     "version (return links) and each target is a live, self-canonical page.",
                     "Fix the annotation set so it is complete and reciprocal.", dict(list(ev.items())[:30]))
        self.add("R17b", "info", "Localized pages per locale (crawled)", [],
                 "Shows how much of the site exists in each language.", "", dict(loc_counts))

    def r_performance(self, cwv):
        slow = [p["url"] for p in self.html200() if (p["ttfb_ms"] or 0) > 1000]
        by_host = collections.defaultdict(list)
        for p in self.html200():
            by_host[urllib.parse.urlsplit(p["url"]).netloc].append(p["ttfb_ms"] or 0)
        med = {h: sorted(v)[len(v) // 2] for h, v in by_host.items()}
        self.add("R18", "medium", "Slow server response (over 1 s from the crawler)", slow,
                 "Slow HTML responses delay every other metric (LCP) and reduce crawl rate.",
                 "Enable full-page caching for anonymous visitors (CDN/page cache) and check origin performance.",
                 {"median_ttfb_ms_by_host": med}, owner="Platform")
        if cwv:
            weak = {}
            for o, d in cwv.get("origins", {}).items():
                for ff in ("PHONE", "DESKTOP", "ALL"):
                    for m, v in (d.get(ff) or {}).items():
                        if isinstance(v, dict) and v.get("rating") in ("needs improvement", "poor"):
                            weak[f"{o} {ff} {m}"] = v
            self.add("R18b", "medium" if any(v["rating"] == "poor" for v in weak.values()) else "low",
                     "Core Web Vitals not 'good' for real users (CrUX p75, 28 days)", list(weak),
                     "Field data is what Google uses for page experience; INP > 200 ms and LCP > 2.5 s are below 'good'.",
                     "Diagnose with Lighthouse/DevTools on the slow template; fix server time first, then scripts.",
                     weak, owner="Frontend")

    def r_render(self, render):
        if not render:
            return
        crit = [r["url"] for r in render if set(r.get("differs", [])) & {"title", "canonical", "robots"}]
        self.add("R19", "high", "JavaScript changes title, canonical or robots", crit,
                 "Google indexes the rendered version; a different raw value sends mixed signals and other bots see the raw one.",
                 "Serve the final values in the HTML response.", {r["url"]: {"raw": r["raw"], "rendered": r["rendered"]} for r in render if r["url"] in crit})
        add = [r for r in render if set(r.get("differs", [])) & {"words", "links"} and r["url"] not in crit]
        if add:
            deltas = [r["rendered"]["words"] - r["raw"]["words"] for r in add]
            raw_ok = all(r["raw"]["words"] >= 200 for r in add)
            self.add("R19b", "low" if raw_ok else "high",
                     "Rendered page has much more text/links than raw HTML" + (" (same block on every page: injected widget)" if raw_ok else ""),
                     [r["url"] for r in add],
                     "Content that appears only after JavaScript may be missed by bots that do not render (most AI crawlers)."
                     if not raw_ok else "The main content is in the raw HTML; the extra block is likely a consent banner or chat widget.",
                     "Check what the extra block is; make sure real content is server-rendered.",
                     {"median_extra_words": sorted(deltas)[len(deltas) // 2]})

    def r_robots(self):
        bots = ["Googlebot", "Bingbot", "GPTBot", "OAI-SearchBot", "ChatGPT-User", "ClaudeBot", "Claude-SearchBot",
                "Claude-User", "PerplexityBot", "Perplexity-User", "Google-Extended", "CCBot"]
        out = {}
        for h in self.hosts:
            p = os.path.join(self.crawl, f"robots_{h}.txt")
            if not os.path.exists(p):
                continue
            rp = Robots(open(p).read())  # same wildcard/precedence semantics as the crawler (R69F-13)
            out[h] = {b: rp.allowed(b, f"https://{h}/") for b in bots}
        blocked = [f"{h}: {b}" for h, d in out.items() for b, ok in d.items() if not ok]
        self.add("R20", "info" if not blocked else "medium", "robots.txt access for search and AI bots", blocked,
                 "Search bots (Googlebot, Bingbot, OAI-SearchBot, Claude-SearchBot, PerplexityBot) decide AI-search visibility; "
                 "training bots (GPTBot, ClaudeBot, Google-Extended, CCBot) are a separate policy choice. "
                 "Cloudflare's AI-bot blocking can override robots.txt; check it in the dashboard.",
                 "Allow the search bots you want to appear in; decide training bots on purpose.", out, owner="Platform")

    def r_unassessed(self, bing):
        meta = dict(self.db.execute("SELECT key, value FROM meta").fetchall())
        un = {k.split(":", 1)[1]: v for k, v in meta.items() if k.startswith("robots_unavailable:")}
        if un:  # RA35-10
            self.add("R20x", "medium", "Hosts not crawled: robots.txt unavailable", [f"https://{h}/robots.txt" for h in un],
                     "The crawler does not treat an unreachable robots.txt as permission, so these hosts were not audited.",
                     "Re-run the crawl later; if it persists, check the server or Cloudflare rules for /robots.txt.",
                     {"robots_unavailable": un}, owner="Platform")
        if bing and bing.get("page_stats_error"):  # RA35-17
            self.add("R21x", "info", "Bing page statistics unavailable (excluded-host check incomplete)",
                     [cfg_site for cfg_site in [bing.get("site", "")] if cfg_site],
                     "Bing returned an error for GetPageStats, so Bing's view of app/old hosts is unknown.",
                     "Check the Bing API key and site access, then re-run bing.py.",
                     {"page_stats_error": bing["page_stats_error"]}, owner="Platform")

    def r_bing(self, bing):
        if bing and isinstance(bing.get("crawl_issues"), list) and bing["crawl_issues"]:
            self.add("R21", "medium", "Bing crawl issues", [i.get("Url", "") for i in bing["crawl_issues"]],
                     "Issues Bing reports while crawling.", "Fix per issue type.", {"issues": bing["crawl_issues"][:30]})

    def run(self):
        insp, cwv, bing, render = (load_json(self.crawl, n) for n in ("inspection.json", "cwv.json", "bing.json", "render.json"))
        self.r_status_links(); self.r_redirects(); self.r_sitemap(); self.r_noindex(); self.r_canonical(insp)
        self.r_index_status(insp); self.r_tracking_links(); self.r_excluded_hosts(bing); self.r_variants()
        self.r_onpage(); self.r_hreflang(); self.r_performance(cwv); self.r_render(render); self.r_robots(); self.r_bing(bing)
        self.r_unassessed(bing)
        order = {"P1": 0, "P2": 1, "P3": 2, "info": 3}
        self.findings.sort(key=lambda f: (order[f["priority"]], -SEV[f["severity"]], -f["gsc_clicks_28d"], -f["count"]))
        return {"inputs": {"crawl": self.crawl, "pages": len(self.pages), "inspection": bool(insp), "cwv": bool(cwv),
                           "bing": bool(bing), "render": bool(render), "gsc_exposure": bool(self.exposure)},
                "exposure_days": self.exposure_days, "exposure_complete": self.exposure_complete,
                "findings": self.findings}


def write_reports(res, crawl, cfg):
    F = res["findings"]
    meta = dict(sqlite3.connect(os.path.join(crawl, "crawl.sqlite")).execute("SELECT key, value FROM meta").fetchall())
    L = [f"# Technical SEO audit · {cfg['site']['name']} · crawl {meta.get('started')}", "",
         f"Hosts: {', '.join(cfg['site']['hosts'])}. Pages crawled: {res['inputs']['pages']}. Inputs: "
         + ", ".join(k for k, v in res["inputs"].items() if v is True) + ". Exposure = GSC clicks/impressions of the "
         "affected URLs over the last 28 days"
         + ("" if res.get("exposure_complete") else f" (PARTIAL: only {res.get('exposure_days')} final days available; "
            "exposure did not raise any priority)") + ". Priorities rank root causes; they do not predict traffic gains.", "",
         "| # | Priority | Severity | Finding | URLs | GSC clicks | GSC impr. | Owner |", "|---|---|---|---|---|---|---|---|"]
    for n, f in enumerate(F, 1):
        L.append(f"| {n} | {f['priority']} | {f['severity']} | {f['title']} | {f['count']} | {f['gsc_clicks_28d']} | "
                 f"{f['gsc_impressions_28d']} | {f['owner']} |")
    L.append("")
    for n, f in enumerate(F, 1):
        L += [f"## {n}. {f['title']} ({f['rule']}, {f['priority']})", "", f"**Why:** {f['why']}", "",
              f"**Fix:** {f['fix']}" if f["fix"] else "", ""]
        if f["urls"]:
            L += ["Examples:", ""] + [f"- {u}" for u in f["urls"][:10]] + ([f"- … {f['count'] - 10} more"] if f["count"] > 10 else []) + [""]
        if f["evidence"]:
            L += ["<details><summary>Evidence</summary>", "", "```json", json.dumps(f["evidence"], ensure_ascii=False, indent=1)[:3000], "```", "</details>", ""]
    open(os.path.join(crawl, "report.md"), "w").write("\n".join(L))
    T = [f"# Developer tickets · {cfg['site']['name']} · crawl {meta.get('started')}", ""]
    for f in [f for f in F if f["priority"] in ("P1", "P2")]:
        T += [f"## [{f['priority']}] {f['title']} — {f['count']} URL(s)", "",
              f"**Owner:** {f['owner']} · **Status:** confirmed by crawl/API evidence", "",
              f"**Observed:** {f['why']}", "", "**Affected URLs (sample):**", ""] + [f"- {u}" for u in f["urls"][:15]] + [
              "", (f"**Business exposure:** {f['gsc_clicks_28d']} clicks / {f['gsc_impressions_28d']} impressions in Google over 28 days on these URLs."
                   if f.get("exposure_complete") else
                   f"**Business exposure:** partial: {f['gsc_clicks_28d']} clicks / {f['gsc_impressions_28d']} impressions over only "
                   f"{res.get('exposure_days')}/28 final days; a full 28-day total is unavailable."),  # R958-06
              "", f"**Proposed change:** {f['fix']}", "",
              "**Acceptance:** re-run `crawl.py` + `audit.py`; this rule returns no URLs. For index issues, re-check with "
              "`inspect_urls.py` after Google recrawls.", "", "---", ""]
    open(os.path.join(crawl, "tickets.md"), "w").write("\n".join(T))


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--site")
    ap.add_argument("--crawl")
    a = ap.parse_args()
    cfg = seoconf.load(a.site)
    crawl = os.path.realpath(a.crawl or os.path.join(seoconf.data_dir(cfg, "crawls"), "latest"))
    res = Audit(cfg, crawl).run()
    json.dump(res, open(os.path.join(crawl, "findings.json"), "w"), indent=1, ensure_ascii=False)
    write_reports(res, crawl, cfg)
    cnt = collections.Counter(f["priority"] for f in res["findings"])
    print(f"{len(res['findings'])} findings: " + ", ".join(f"{k}={v}" for k, v in sorted(cnt.items())))
    for f in res["findings"]:
        if f["priority"] != "info":
            print(f"  {f['priority']} {f['severity']:6} {f['count']:4}  {f['title']}  (clicks {f['gsc_clicks_28d']})")
    print(f"\n{crawl}/report.md\n{crawl}/tickets.md")


if __name__ == "__main__":
    main()
