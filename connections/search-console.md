# Google Search Console (service account)

**What it gives you:** your site's Google search data: clicks, impressions, CTR and position by page, query, country and device; Google's index view of each URL (URL Inspection); sitemaps.
**Used by:** `gsc-insights`, `seo-tech-audit` (URL Inspection, Google clicks per URL), `ahrefs` (`kw.py prioritize` joins your positions), `seo` (routes to them).
**Access:** a Google Cloud service account with **Restricted** (read-only) access to your Search Console property, and its JSON key file.
**Cost:** free.
**Needs:** `uv` (the SEO scripts run with `uv run --script` and install their own dependencies), a site config file.
**Setup time:** ~15 minutes

Why a service account and not your Google login: it does not expire like a user login, it can be limited to read-only, and the weekly report keeps working when nobody is signed in.

## 1. Create the service account

1. Google Cloud console → pick or create a project → **APIs & Services → Library** → enable **Google Search Console API**. For the weekly report sheet also enable **Google Sheets API**; for the conversions join, **BigQuery API**.
2. **IAM & Admin → Service accounts → Create service account.** Any name (`seo-reader`). No project roles are needed for Search Console.
3. Open it → **Keys → Add key → Create new key → JSON**. Save the file outside every repository, e.g. `~/.config/gcloud/seo-reader.json`, and `chmod 600` it.

If key creation is blocked, your organisation has the policy `iam.disableServiceAccountKeyCreation`; ask an admin or use a project outside the organisation.

## 2. Give it read-only access to the property

Search Console → your property → **Settings → Users and permissions → Add user** → the service account's email (`seo-reader@<project>.iam.gserviceaccount.com`) → permission **Restricted**.

A domain property (`sc-domain:example.com`) covers every host and protocol; use it if you have one.

## 3. Write the site config

`~/.config/marketing-agent-kit/seo/<site>.toml`. The format, with every field explained, is in `skills/gsc-insights/references/config.md`. The minimum: `[site]` (property, hosts, start URLs, sitemaps), `[brand]` (regexes for brand queries), `[credentials] gsc_service_account = "~/.config/gcloud/seo-reader.json"`, `[data] dir`.

Optional parts:
- **Weekly report sheet**: create a Google Sheet, share it with the service account's email as **Editor**, put its id in `[report] sheet_id`.
- **Conversions join (BigQuery)**: give the service account **BigQuery Data Viewer** on the GA4 export dataset and **BigQuery Job User** on the project; start from `skills/gsc-insights/references/example.*.sql`.

## 4. Check

```bash
uv run --script skills/gsc-insights/scripts/gsc_pull.py --site <site>      # first run back-fills 16 months (~10 min)
uv run --script skills/gsc-insights/scripts/gsc_recipes.py coverage --site <site>
```

Or ask Claude: *"Pull Search Console data for my site and show what the archive covers."*

## Limits

| What | Limit |
|---|---|
| URL Inspection API | 2,000 queries per day and 600 per minute, per site |
| Search Analytics queries | 1,200 per minute per site and per user |
| History in the API | 16 months; `gsc_pull.py` keeps a local archive so older data survives |

## Safety

- **Restricted** permission can read everything but change nothing. The skills never submit sitemaps or request indexing.
- The JSON key is a password for that account. Keep it out of repositories and chats; delete the key in Cloud console if it leaks.

## Gotchas

- Search Console dates are US Pacific time; GA4 uses the property's time zone. Day edges differ by hours.
- The last 2-3 days are provisional. The scripts re-pull days Google marks incomplete and refuse to report on them.
- Query rows hide anonymised queries (often 40-60% of clicks). Page and site totals are the real totals.
- The Search Console "AI" report (AI Overviews / AI Mode impressions) is not in the API.

## Links

- API limits: <https://developers.google.com/webmaster-tools/limits> · Adding users: <https://support.google.com/webmasters/answer/7687615>

*Checked 2026-10-21.*
