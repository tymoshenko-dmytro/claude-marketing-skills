# Chrome UX Report (CrUX) API

**What it gives you:** real-user Core Web Vitals (LCP, INP, CLS) at the 75th percentile for your origin and URLs, the field data Google uses.
**Used by:** `seo-tech-audit` (`cwv.py`).
**Access:** a Google Cloud API key enabled for the Chrome UX Report API.
**Cost:** free. 150 queries per minute per Google Cloud project; the quota cannot be raised by paying.
**Setup time:** ~5 minutes

## 1. Get the key

1. Google Cloud console → **APIs & Services → Library** → enable **Chrome UX Report API**.
2. **APIs & Services → Credentials → Create credentials → API key.**
3. Edit the key → **API restrictions → Restrict key** → only *Chrome UX Report API*. A restricted key is useless for anything else if it leaks.
4. Put it into the keys file: `CRUX_API_KEY=...` (`kit.py open`).

## 2. Check

```bash
python3 skills/connect/scripts/kit.py doctor --live      # CRUX_API_KEY · accepted
```

## Gotchas

- Small sites and new pages often have no CrUX data: not enough Chrome traffic. `cwv.py` reports "no field data" for them; that is not an error.
- Field data is a rolling 28-day window. A fix shows up fully about four weeks later.
- Lighthouse (lab data) helps find the cause, but the pass/fail verdict comes from CrUX.

## Links

- <https://developer.chrome.com/docs/crux/api>

*Checked 2026-10-21.*
