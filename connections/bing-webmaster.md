# Bing Webmaster Tools API

**What it gives you:** Bing's view of your site: crawl errors, indexed pages, query stats. Bing's index also feeds ChatGPT search and other AI assistants, so it matters more than Bing's own traffic suggests.
**Used by:** `seo-tech-audit` (`bing.py`), `gsc-insights` (the weekly digest's Bing visibility line).
**Access:** an API key from Bing Webmaster Tools. One key per user, valid for all your verified sites.
**Cost:** free.
**Setup time:** ~5 minutes (plus site verification if you have not done it; importing from Search Console takes a minute)

## 1. Get the key

1. Sign in to <https://www.bing.com/webmasters> and add your site. **Import from Google Search Console** verifies it in one step.
2. **Settings** (top right) → **API Access** → accept the terms → **API Key** → **Generate API Key**.
3. Put it into the keys file: `BING_WMT_API_KEY=...` (`kit.py open`).
4. In the site config set `[site] bing_site` to the site URL exactly as Bing lists it (e.g. `https://example.com/`).

## 2. Check

```bash
python3 skills/connect/scripts/kit.py doctor --live      # BING_WMT_API_KEY · accepted, N site(s)
```

## Safety

- The key can also submit URLs and change settings through the API. The skills only read; still, treat the key as a password. If it leaks: **API Access → Delete**, then generate a new one.
- Bing's API takes the key as a URL parameter. Do not paste such URLs into chats or logs.

## Links

- <https://learn.microsoft.com/en-us/bingwebmaster/getting-access>

*Checked 2026-10-21.*
