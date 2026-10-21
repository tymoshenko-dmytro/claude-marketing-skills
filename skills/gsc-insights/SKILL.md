---
name: gsc-insights
description: >-
  Analyses a site's Google Search Console data from a local SQLite archive of the Search Console API, so history
  survives Google's 16-month limit. Twelve recipes: striking-distance queries (positions 5-20), CTR below expected,
  cannibalization, content decay, new queries, brand vs non-brand, countries, devices, question queries, impact of a
  Google update or a site change. Builds the weekly report and a weekly digest (visits and conversions by search
  source and AI assistant, Bing, audit backlog, chart) for Slack and a Google Sheet. Use when someone asks how
  organic search is doing, why organic traffic dropped, which queries or pages to work on, or for the weekly SEO
  post. Triggers: "weekly SEO report", "GSC report", "Search Console this week", "why did organic drop",
  "striking distance keywords", "keyword cannibalization", "content decay", "pages losing traffic", "new queries",
  "low CTR pages". For technical audits use seo-tech-audit; for keyword research, ahrefs.
---

# GSC insights

Turn Search Console data into a short list of actions. Collect, calculate and interpret are separate steps:
scripts collect and calculate, you interpret. Never compute a metric in your head or fill a gap with a guess.

## Setup (once per site)

Full guide: `connections/search-console.md`. The short version:

1. **Install `uv`** (`curl -LsSf https://astral.sh/uv/install.sh | sh`, or `brew install uv`). Every script runs with
   `uv run --script` and installs its own dependencies (declared at the top of each script). Python 3.11+.
2. **Create a service account** in Google Cloud: enable the Google Search Console API (plus Sheets API for the report
   sheet, BigQuery API for conversions), create the service account, download its JSON key, `chmod 600` it, keep it
   outside every repository. Service accounts do not expire the way user logins do.
3. **Give it Restricted access** to the property: Search Console → Settings → Users and permissions → Add user →
   the service account's email → **Restricted** (read-only).
4. **Write the site config** `~/.config/marketing-agent-kit/seo/<site>.toml` from `references/config.md`: GSC
   property, hosts, locales, brand regexes, the key path, a data folder such as
   `~/.local/share/marketing-agent-kit/seo/<site>`. Optional: a report sheet (share it with the service account's
   email as Editor), a Slack channel, the two SQL files for the digest and the conversions join (start from
   `references/example.sources.sql` and `references/example.organic.sql`; the service account needs BigQuery Data
   Viewer on the GA4 export dataset and BigQuery Job User on the project).
5. **First pull:** `uv run --script ${CLAUDE_SKILL_DIR}/scripts/gsc_pull.py --site <site>` back-fills 16 months
   (~10 min). Then `uv run --script ${CLAUDE_SKILL_DIR}/scripts/gsc_recipes.py coverage --site <site>` shows what the
   archive holds.

Keys (`BING_WMT_API_KEY` for Bing numbers in the digest, `SLACK_WEBHOOK_URL` for webhook posts) are read from the
environment or the kit's keys file `~/.config/marketing-agent-kit/.env`; never from the site config.

## Commands

All scripts live in `${CLAUDE_SKILL_DIR}/scripts/`, run with `uv run --script`, and take `--site <name>` (optional
when only one config exists).

| Step | Command | Notes |
|---|---|---|
| Pull | `gsc_pull.py` | Incremental. First run back-fills 16 months (~10 min). Re-pulls days Google marks incomplete. `--start/--end` force a range. |
| Analyse | `gsc_recipes.py RECIPE [--days 28] [--end D] [--format table/json/csv]` | 12 recipes, see below and `references/recipes.md` |
| Weekly report | `gsc_report.py [--week 2026-W41]` | Detailed GSC lists: Markdown in `<data>/reports/`, detail tabs in the Google Sheet |
| Weekly digest | `weekly_digest.py [--week 2026-W42]` | The team summary: visits → sign-ups → trials by source (Google, AI assistants, Bing, other), GSC and Bing visibility, audit backlog, chart PNG, action candidates; Slack text in `[report].language` |

Always run `gsc_pull.py` before analysing, then `gsc_recipes.py coverage` to see what the archive holds.

## Recipes

`coverage`, `striking`, `ctr_gap`, `cannibal`, `decay`, `new_queries`, `page_map`, `brand`, `countries`,
`devices`, `questions`, `update_impact --date D`. Definitions, thresholds and decision rules are in
`references/recipes.md`. Read it before you recommend an action from a recipe.

## Weekly digest workflow (the Slack post)

1. `gsc_pull.py`, then `gsc_report.py` (refreshes the detail tabs), then `weekly_digest.py`. The digest covers the
   last full ISO week and stops if GA4 lacks any of its days; run it on Wednesday so GA4 and Search Console are
   both complete. If Search Console has not finalised the week yet, the text says so instead of showing numbers.
2. Replace the `{{ACTIONS}}` line in `<week>.digest.md` with at most three numbered actions chosen from
   `action_candidates` in `<week>.digest.json`. Each action is one plain sentence in the post's language, says what
   to do and why, and quotes only numbers that are in the JSON. Prefer: open P1 audit items, then pages with
   sign-ups but no trials (`conversion_gap`), then striking-distance queries on pages that convert.
3. Post the text with the Slack connector to `[report].slack_channel_id`, then upload `<week>.trend.png` to the same
   channel (two-step upload: get upload URL, POST the bytes, complete with the channel id). Ask before the first post
   to a new channel. Setup: `connections/slack.md`.

## Detailed report workflow

1. `gsc_pull.py`, then `gsc_report.py`. The report picks the last ISO week whose 7 days are final.
2. Read `<data>/reports/<week>.md`. Add at most 3 sentences of interpretation, each tied to a number
   in the report. Say what changed, not what might have caused it, unless a recipe shows the cause.
3. Post `<week>.slack.txt` to the channel in `[report].slack_channel`: through `SLACK_WEBHOOK_URL` if set,
   otherwise with the Slack connector (it takes standard Markdown: turn the leading `*title*` into `**title**`).
   Find the channel id with the connector's channel search (private channels included). Ask before the first post
   to a new channel.
4. The sheet gets one row per week in `Weekly` and fresh lists in the detail tabs.

## Rules

- **No data, no answer.** Recipes stop when any day of their window (or comparison window) is missing or
  provisional; the weekly report marks such sections "unavailable" and shows `n/a` for incomplete comparisons.
- **Name the grain.** Property totals, page rows and query rows are different datasets. Query rows miss
  anonymized queries (often 40-60% of clicks); every output states its coverage. Never sum query rows and call
  it the site total.
- **Dates are US Pacific** in GSC; GA4/BigQuery dates are the property's timezone. Edges differ by hours.
- **Thresholds are heuristics.** 5-20 positions, 20% shares, -20% decay are starting points. Say so when you cite them.
- **Brand is a classifier, not a fact.** A brand word that is also a dictionary word goes to `ambiguous`.
  Report brand, ambiguous, non-brand and hidden separately.
- **Different locales are not cannibalization.** `/es/` and `/ar/` versions answering the same query are
  legitimate; only same-locale pages are candidates, and a candidate is not proof of harm.
- **Read-only.** Never submit sitemaps, request indexing or change the site from this skill. Propose changes;
  a person applies them. Google's Indexing API is only for job postings and livestreams, not for pages like these.
- **Conversions are association, not attribution.** GSC never says which query produced a sign-up. The
  conversions SQL credits a person's last organic landing page; label it that way.
- The new Search Console AI report (AI Overviews / AI Mode impressions) is UI-only; it is not in this archive.

## Adapt it

- Write your brand regexes carefully (`[brand] patterns` and `ambiguous`): every brand / non-brand split depends on
  them. Put brand words that are also dictionary words into `ambiguous`.
- Map "registrations" and "trials" to your own two conversion events in the SQL files (sign-up and first purchase,
  lead and booked demo...). The column names stay; the events are yours.
- Tune the recipe thresholds to your traffic (`--min-impr`, `--days`); the defaults suit a site with thousands of
  impressions a day.
- Set `[report] language` (`en` or `ru`) and the Slack channel; add another language by extending the translation
  tables in `weekly_digest.py`.
- Change the AI-assistant source regex in `example.sources.sql` when new assistants start sending you traffic.
