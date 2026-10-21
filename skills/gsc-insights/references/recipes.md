# Recipes: definitions and decision rules

All recipes read the local archive. The current window is the last `--days` final days (default 28) ending at
`--end` or the last final day; the previous window is the same length right before it. Positions are
impression-weighted: `SUM(position*impressions)/SUM(impressions)`. CTR is total clicks / total impressions, never an
average of row CTRs. Thresholds scale with `--days` unless set by flags.

| Recipe | What it computes | Default threshold | What to do with it |
|---|---|---|---|
| `coverage` | Archive span, final days, truncated days (50k-row cap), share of clicks/impressions on query rows | — | Quote the coverage next to every query-level number. |
| `striking` | Non-brand query+page pairs at position 5-20 | >= 100 impressions per 28 days | Improve the existing page first (title, intro answer, section for the query, internal links from strong pages). `potential_clicks` = impressions x our CTR at position 3 - clicks; it is an upper bound, not a forecast. Rank by business value, not by potential alone: a huge generic query with no conversions is worth less than a small product query. |
| `ctr_gap` | Top-10 pairs getting < 80% of the clicks our own CTR curve expects for that position | >= 100 impressions per 28 days | Check the SERP first (AI Overview, ads, video, map pack can eat clicks). Then title/description/intent match. The curve is built from our own non-brand data over 90 days; with too little data it falls back to a generic curve and says so. |
| `cannibal` | Queries where 2+ pages of the same locale each take >= 20% of impressions; `top_page_switches` counts distinct daily top pages | >= 50 impressions per 28 days | Open both pages and the SERP. Merge or differentiate only when the intent is the same. Different locales are excluded on purpose. |
| `decay` | Pages whose clicks fell >= 20% vs the previous window, with the reason split into fewer impressions / lower position / lower CTR | prev clicks >= 20 per 28 days | Fewer impressions → demand or indexing; lower position → competitors or content; lower CTR → SERP features or snippet. Rule out technical changes (status, canonical, noindex) before rewriting. |
| `new_queries` | Non-brand queries in the window not seen in the 84 days before it | >= 20 impressions | "Newly observed" is not "new demand". Map relevant ones to an existing page; queue the rest for ahrefs keyword research. |
| `page_map` | Per page: clicks, query count, top 5 queries, share of clicks without a visible query | — | Find pages without a coherent query cluster and clusters landing on the wrong page. |
| `brand` | Weekly clicks/impressions split brand / ambiguous / non-brand, plus hidden (site total minus query rows) | — | Growth in brand can hide non-brand decline; always read the non-brand line. |
| `countries` | Country totals vs previous window with the top writing systems of their queries | — | A country is not a language. Use the script mix to see which language actually brings traffic. |
| `devices` | Device totals vs previous window | — | A device-specific drop points at page experience or snippet truncation. |
| `questions` | Question queries (EN/ES/PT/FR/DE/ID/AR patterns) by landing page | — | Answer them on the page that already ranks; do not make one thin page per phrasing. |
| `update_impact --date D` | Page clicks in the `--days` before D vs the `--days` starting 7 days after D | pages with >= 5 clicks | For Google core updates use the rollout end date. Compare with unchanged pages before claiming cause. |

## Interpreting with conversions

`gsc_report.py` adds organic sessions, registrations and trials per landing page when the site config has a
conversions SQL. Use it to weigh opportunities: a page with organic sessions but no trials needs conversion work
before more traffic; a striking-distance query landing on a converting page is worth more than a bigger one landing
on a page that never converts.
