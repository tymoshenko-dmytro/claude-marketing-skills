# Audit rules

Severity describes the failure. Priority = severity, raised one step when the affected URLs had 50+ Google clicks in
28 days (P1 ≥ 4, P2 = 3, P3 = 1-2, info = 0 on the scale critical 4 / high 3 / medium 2 / low 1 / info 0).

| Rule | Severity | Detects | Source | Verify a fix |
|---|---|---|---|---|
| R01 | high | Internal links to 4xx/5xx pages (only targets with an observed internal link) (Cloudflare `/cdn-cgi/` excluded, reported as R01b info) | crawl | link target returns 200 or the link is gone |
| R02 / R02b | medium / low | Redirect chains with 2+ hops; internal links that point to redirects | crawl | one hop; links go to final URLs |
| R03 | high | Sitemap URLs that are not indexable 200s (redirects, errors, noindex, canonicalised, blocked); unreadable sitemaps | crawl + sitemaps | sitemap lists only indexable 200s |
| R04 | medium | Indexable 200 pages missing from the sitemap | crawl | page in sitemap, or noindexed on purpose |
| R05 | medium | All noindex pages, for review | crawl | each one intended |
| R06 / b / c / d | medium / info / high / high | No canonical; canonical to another URL; canonical to a non-200/noindex; Google canonical ≠ declared | crawl, inspection | self-canonical; Google agrees after recrawl |
| R07 / R07x | high/medium / info | Indexable pages Google has not indexed, grouped by coverage state; R07x = inspection returned no usable verdict (nothing claimed) | inspection | `inspect_urls.py` shows "Submitted and indexed" after recrawl |
| R08 | medium | Internal links with tracking parameters (`_gl`, `utm_*`, `gclid`…) | crawl links | links are clean URLs |
| R09 | high | Pages on `excluded_hosts` with Google impressions or in Bing | GSC archive, Bing | noindex/redirect in place; impressions fade over weeks |
| R10 | medium | http:// or non-www variants with impressions that do not 301 | GSC archive + live fetch | 301 to the canonical host |
| R11 / R11b | medium / low | Missing/duplicate titles; titles outside 20-60 characters | crawl | unique titles |
| R12 | low | Meta descriptions missing, duplicate, or outside 70-160 characters | crawl | — |
| R13 | low | No H1 or several H1s | crawl | one H1 |
| R14 | low | Indexable pages under 250 words | crawl | — |
| R15 | low | Pages with 3+ images missing the alt attribute (alt="" counts as decorative, not missing) | crawl | — |
| R16 / R16b | medium / info | Invalid JSON-LD; FAQPage markup (no longer a rich result) | crawl | JSON parses |
| R17 / R17b | medium-low / info | hreflang: no self-reference, invalid code, missing return link, non-indexable target, code ≠ target `<html lang>`; pages per locale | crawl | reciprocal, valid set |
| R18 / R18b | medium / low-medium | Crawler TTFB over 1 s; CrUX p75 metrics not "good" (LCP 2.5 s, INP 200 ms, CLS 0.1, TTFB 0.8 s) | crawl, CrUX | CrUX improves over the next 28-day window |
| R19 / R19b | high / low-high | JS changes title/canonical/robots; rendered DOM has much more text/links (low when the same block is added on every page and raw HTML already has content) | render | raw and rendered agree |
| R20 | info/medium | robots.txt access per search/AI bot | robots.txt | intended policy |
| R21 | medium | Bing crawl issues | Bing API | issue list empty |

Thresholds are conventions, not Google rules: title length is about pixel width, description length is about
truncation, and 250 words is a heuristic for "thin". Say so when you cite them.
