# Competitor research pipeline: phases, agents, templates

Placeholders: `{COMPANY}` — name, `{DOMAIN}` — domain, `{DIR}` — working folder `competitor-{name}/`.

## Folder structure

```
competitor-{name}/
  README.md            # map of the knowledge base (write it first)
  baseline/            # what was known before (from memory / past reports)
  raw/
    site/       (sitemap-urls.txt, dumps, docs-llms.txt, seo-farm-analysis, blog-digest, docs-api-map)
    ads/        (search JSON, li-detail-*.html, google-creatives/*.png)
    community/  (hackernews, reddit, github, social, review-sites, producthunt, forums, launches, tutorials)
    seo/        (raw Ahrefs responses)
    team/       (roster, posts-digest, SERP json)
    parallel/   (tN-brief.txt, tN-result.json, tN-report.md, runs.json)
  knowledge-base/      # 01-products-usp, 02-customers-cases, 03-pricing, 05-ads-offers, 06-seo, 07-team
  synthesis/           # 01-positioning-icp, 03-company-dossier, report.html, pages/*.html
```

## Phase 0 — foundation (inline, ~10 min)

1. Memory and past reports: if this competitor came up before, have one agent assemble a baseline file. Don't re-collect what is known.
2. `curl -sL https://{DOMAIN}/robots.txt` → sitemap URL (often `sitemap-index.xml` / `sitemap-0.xml`; frameworks have their own paths). Save the URL list and cluster it by the first path segment: `awk -F'/' '{print $4}' | sort | uniq -c | sort -rn`. The clusters tell you where the company invests (a big `/vs/` or `/alternatives/` cluster is a programmatic-SEO play).
3. Check keys with one cheap call each: SearchApi (`google`, `num=3`), Parallel search, Ahrefs `subscription-info-limits-and-usage` (free). Or run the `connect` skill's doctor.
4. On the docs subdomain try `/llms.txt` and `/llms-full.txt` — they often return the whole documentation as text.

## Phase 1 — Parallel deep research (submit BEFORE the collection phase)

Briefs t1–t9 from `parallel-briefs.md` with the full `{ANCHOR}`, processor `ultra`, run ids in `raw/parallel/runs.json`, one background poller over all of them (template in the parallel-research skill; for many runs loop over `runs.json` with `sleep 240`).

## Phase 2 — collection (~15–17 agents, 30–50 min)

All agents in parallel. Each returns `{file, key_findings, gaps}` (all three required). A shared preamble for every agent: company context, paths, which skill scripts to use, the rules (WebFetch for static pages; a source URL for every fact; never log in anywhere; two workaround attempts when blocked, then record a gap; quotes in the original language).

| Agent | What it does | Output |
|---|---|---|
| site-products | every product page + the homepage → product catalogue, USPs, verbatim claims with numbers, flagships | knowledge-base/01-products-usp.md |
| site-customers | every /customers or case-study page → table in the report-rules format + patterns (verticals, migrations) | knowledge-base/02-customers-cases.md |
| site-pricing | /pricing + docs + **an archive.org snapshot from a year ago** (what changed; watch for credit abstractions) | knowledge-base/03-pricing.md |
| site-vs-farm | /vs, /alternatives, programmatic clusters → who they position against, repeated proof points (= their sales arguments), whether they mention the user's company | raw/site/seo-farm-analysis.md |
| site-blog | every post: timeline, narratives, frequency | raw/site/blog-digest.md |
| site-docs | llms.txt → API map: models and versions, limits, changelog (deprecations!), self-hosting | raw/site/docs-api-map.md |
| community-hn | Algolia API (`hn.algolia.com/api/v1/search?query=X&tags=story` or `comment`) → threads, quotes, themes, founder engagement | raw/community/hackernews.md |
| community-reddit | `search.json` with a browser User-Agent + relevant subreddits; fallback: SERP `site:reddit.com` + old.reddit `.json` | raw/community/reddit.md |
| community-github | org repos, stars, issue themes (pain points!), community plugins, open source outside the org | raw/community/github.md |
| community-social | SearchApi `youtube` + Google `site:x.com` → who writes and films about them, reach | raw/community/social.md |
| community-reviews | G2 / Capterra / TrustRadius / Trustpilot through SERP snippets (direct fetches get blocked); empty listings are a finding too | raw/community/review-sites.md |
| community-producthunt | launches, upvotes, comments, directories | raw/community/producthunt.md |
| community-forums | dev.to / Medium / Hugging Face / Stack Overflow / framework forums | raw/community/forums.md |
| ads | per the **ads-parser** skill (three libraries + LinkedIn detail pages) | knowledge-base/05-ads-offers.md + raw/ads/* |
| seo | per the **ahrefs** skill (organic, top pages, referring domains, history; overlap with the user's domain if asked) | knowledge-base/06-seo.md + raw/seo/* |
| team-roster | NO login: SERP `site:linkedin.com/in "{COMPANY}"` (profile titles) + company page + theorg / crunchbase snippets + hiring press → full table | raw/team/roster.md |
| team-posts | SERP `site:linkedin.com/posts {COMPANY}` + founders' X accounts → the team's narratives | raw/team/posts-digest.md |

Drop or add rows for your market — a consumer app needs app-store reviews and TikTok more than GitHub and Hacker News.

## Phase 3 — verification (as needed)

After the first draft the user will point at doubtful numbers. Pattern: targeted verification agents (the origin of a LinkedIn impressions figure; "default in tutorials" → check the frameworks' quickstart code; the full team roster). Where a number doesn't hold up, remove it or re-attribute it honestly.

Known overcounts to check by default:
- LinkedIn headcounts overcount by roughly 25–40% and suffer name collisions (a "Head of Growth" at a same-named company). Cross-check with founder statements, careers pages and databases.
- Founder claims from podcasts and interviews are self-reported. Label them and keep them apart from independently verifiable facts.
- Identical engagement at 1000× the views (a post with a few dozen likes at 30M views) means bought impressions, not a normal promoted post — normal ads to relevant audiences produce proportional behaviour.

## Phase 4 — synthesis (three agents after collection)

1. **positioning-icp:** how positioning evolved, ICP profiles ranked by revenue, sales points with verification status (independently confirmed / self-reported / outdated), the GTM engine ranked by money.
2. **dossier:** timeline, finances, team, partnerships, media — a reference of dated facts.
3. **battlecard** — only on explicit request.

## Phase 5 — report and satellite pages

1. Main `report.html`: narrative summary → company (finances as a table, full team) → products and pricing → customers (table) → GTM ranked by money → weaknesses → what to monitor (/launch, changelog, pricing archive, ad library, careers) → appendix with the file map.
2. Satellite pages `pages/*.html`, each inheriting the main report's CSS: launches, ads, PR, tutorials, community — as material allows.
3. Navigation: a grid of card buttons after the table of contents, plus inline buttons at the end of relevant sections.
4. After cutting sections, validate tag balance (cuts often leave unclosed `div`s) and check the table-of-contents anchors.

## Phase 6 — memory

Save locations, main facts, what to monitor and links to published pages, so the next run starts from them.
