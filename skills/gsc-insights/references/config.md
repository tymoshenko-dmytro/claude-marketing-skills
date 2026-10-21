# Site config

One TOML file per site in `~/.config/marketing-agent-kit/seo/<site>.toml` (override the folder with
`SEO_SKILLS_CONFIG_DIR`). The same file is read by gsc-insights, seo-tech-audit and ahrefs (keyword research).
Scripts take `--site <name>` (or a path to the file, or `SEO_SITE`); with a single file in the folder they use it.
Secrets never go in it.

```toml
[site]
name = "example"
gsc_property = "sc-domain:example.com"        # or "https://www.example.com/"
hosts = ["www.example.com", "blog.example.com"]  # hosts we want in search; the crawler stays inside them
start_urls = ["https://www.example.com/"]
sitemaps = ["https://www.example.com/sitemap.xml"]
excluded_hosts = ["app.example.com"]           # should never appear in search
other_hosts = ["docs.example.com"]             # may be indexed, out of crawl scope
locales = ["en", "es", "de"]                   # first path segment of localized URLs
bing_site = "https://example.com/"             # Bing Webmaster Tools site URL

[brand]
patterns = ['example\s*app', 'examplehq']      # case-insensitive regexes -> brand
ambiguous = ['\bexample\b']                     # brand words that are also normal words

[credentials]
gsc_service_account = "~/.config/gcloud/seo-reader.json"   # JSON key of the read-only service account
# env_file = "~/.config/marketing-agent-kit/.env"         # default; KEY=value lines: CRUX_API_KEY,
#                                                          # BING_WMT_API_KEY, AHREFS_API_KEY, SLACK_WEBHOOK_URL

[data]
dir = "~/.local/share/marketing-agent-kit/seo/example"   # archive, crawls, reports, keyword projects

[report]
sheet_id = ""                                   # Google Sheet shared with the service account as editor
slack_channel = "#seo-weekly"
slack_channel_id = "C0123456789"               # the Slack connector posts by id
language = "en"                                 # digest and audit backlog language: en or ru
trend_weeks = 8

[digest]                                        # weekly_digest.py
sources_sql = "~/.config/marketing-agent-kit/seo/example.sources.sql"
# {{start}} {{end}}; columns: week (YYYY-Www), channel (Google / AI assistants / Bing / Other search), sessions,
# registrations, trials; plus one row per week with channel='_days' and sessions = number of GA4 days present.
# Start from references/example.sources.sql.

[conversions]                                   # BigQuery; bq_project and bq_location are also used by [digest]
sql = "~/.config/marketing-agent-kit/seo/example.organic.sql"   # optional; {{start}} {{end}};
# columns: landing_page, organic_sessions, registrations, trials. Start from references/example.organic.sql.
bq_project = "my-project"                       # the project that runs (and pays for) the queries
bq_location = "EU"                              # the location of the GA4 export dataset

[keywords]
default_country = "us"
markets = ["us", "de"]
monthly_unit_cap = 0                            # Ahrefs units; 0 = log only
```

Secrets: a variable already set in the environment wins; otherwise the scripts read the keys file
(`[credentials].env_file`, by default `~/.config/marketing-agent-kit/.env`, or the file named by `MARKETING_KIT_ENV`).
Lines are `KEY=value`; quotes and a trailing ` # comment` are allowed.

## The two SQL files

Both run in BigQuery as the service account, with `{{start}}` and `{{end}}` replaced by inclusive dates
(`YYYY-MM-DD`). Give the service account **BigQuery Data Viewer** on the GA4 export dataset (and on any other
dataset the SQL reads) and **BigQuery Job User** on `bq_project`.

| File | Used by | Must return |
|---|---|---|
| `[digest] sources_sql` | `weekly_digest.py` | `week` (`YYYY-Www`, ISO), `channel` (`Google`, `AI assistants`, `Bing`, `Other search`), `sessions`, `registrations`, `trials`; plus per week one row `channel = '_days'` whose `sessions` is the number of GA4 days present (7 = complete week) |
| `[conversions] sql` | `gsc_report.py`, `weekly_digest.py` (`conversion_gap` candidates) | `landing_page`, `organic_sessions`, `registrations`, `trials` |

`references/example.sources.sql` and `references/example.organic.sql` implement these contracts on the standard
GA4 BigQuery export (`events_*` tables) with the GA4 recommended event `sign_up` as the registration and a
placeholder for your trial (second conversion) event. Copy them next to the site config and change the lines marked
`CHANGE`. "Registrations" and "trials" are just the column names: map them to your own two conversion events (for
example sign-up and first purchase, or lead and booked demo). If your conversions live in a backend table instead of
GA4, replace the `conv` CTE with a query on that table that returns the same columns.
