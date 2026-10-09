---
name: ahrefs-seo
description: >-
  Pull raw SEO data from Ahrefs for any domain — organic keywords, top pages, backlinks, referring domains, Domain Rating, traffic history, anchors, organic competitors, keyword volumes — through the Ahrefs MCP server or a script fallback, while keeping API-unit spend under control. Use when someone asks for a domain's organic traffic, backlinks, SEO metrics of a competitor, or keyword volumes. Triggers: "check in Ahrefs", "organic traffic of X", "backlinks of X", "keyword volumes".
---

# Ahrefs SEO data

Ahrefs data through the official Ahrefs MCP server, with an optional script for API v3 keys. Every call spends API units from your Ahrefs plan (MCP needs a paid plan, Lite or higher). Setup: `connections/ahrefs-mcp.md`, or run the `connect` skill.

## Path 1 — the Ahrefs MCP server (default)

Tools are named `mcp__ahrefs__*`. If they aren't loaded, search for them (for example "ahrefs organic keywords"); if the server isn't connected, send the user to `connections/ahrefs-mcp.md`. Server rules:

- Call the `doc` tool before the first use of any tool.
- Every money value is in **USD cents** — divide by 100.
- If a response carries `render_with` metadata, call that render tool with the data.
- Save what matters: write each response you will quote to `raw/seo/<name>.json`.

## Path 2 — API v3 script (Enterprise API keys only)

For repeatable pulls with an **API v3 key** (`AHREFS_API_KEY`):

```bash
python3 ${CLAUDE_SKILL_DIR}/scripts/ahrefs_api.py site-explorer/organic-keywords target=example.com date=2026-09-30 \
    select=keyword,sum_traffic,best_position limit=100 order_by=sum_traffic:desc --out raw/seo/kw.json
```

The endpoint path is the MCP tool name with the first dash turned into a slash. MCP keys and API v3 keys are not interchangeable — the wrong one returns 401. Don't write your own client for the MCP endpoint: Ahrefs' terms don't permit scripts that call it directly; scripted access goes through API v3.

## Recipes (tool names as of 2026 — verify with `tools`)

| Task | Tool |
|---|---|
| DR and summary metrics | `site-explorer-domain-rating`, `site-explorer-metrics` |
| Organic keywords (top by traffic) | `site-explorer-organic-keywords` (order by traffic, `limit<=150`) |
| Top pages by organic traffic | `site-explorer-top-pages` |
| Referring domains, backlink summary | `site-explorer-referring-domains`, `site-explorer-backlinks-stats` |
| Anchors | `site-explorer-anchors` |
| Traffic and keyword history | `site-explorer-metrics-history`, `site-explorer-keywords-history` |
| Organic competitors | `site-explorer-organic-competitors` |
| Organic traffic by country | `site-explorer-metrics-by-country` |
| SERP for a keyword | `serp-overview` |
| Keyword ideas | `keywords-explorer-matching-terms`, `keywords-explorer-related-terms` |
| Keyword volume and difficulty | `keywords-explorer-overview` |
| Units left this month | `subscription-info-limits-and-usage` (free) |

## Hard rules

- Every call costs **at least 50 units**, and fields are billed per row. `limit<=150` per call by default. Never pull raw backlinks by the thousand — `site-explorer-all-backlinks` is the most expensive tool; start with stats and referring domains.
- Check remaining units (`subscription-info-limits-and-usage`) before a long series of calls.
- **Don't trust Ahrefs paid-traffic and ad-budget estimates, and don't put them in reports.** They are systematically off. Mentioning that a domain has paid keywords is fine; dollar figures are not.
- Save raw responses with `--out` next to the analysis. Numbers in a report must be checkable against raw files.

## Keyword research costs

Large keyword pulls are where units disappear. Read `references/unit-costs.md` before pricing more than a few dozen keywords. The short version:

- Volume-type fields (`volume`, `global_volume`, `difficulty`, `traffic_potential`, `parent_volume`) cost about 10 units **per row each**; `keyword` alone costs about 1. Select only the field you need.
- Discover with `select=keyword` first, then price only the shortlist.
- Put the volume floor into `where` — only kept rows are billed.
- Send pricing calls sequentially, in batches of 2–5 keywords.

## Adapt it

- Keep a `domains.json` with your own domain and your competitors, so "compare us with the usual three" needs no lookups.
- If you run the same SEO snapshot monthly, turn the calls into a fixed script and keep the agent for interpreting changes — a stable report doesn't need an agent every time.
