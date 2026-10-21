# Ahrefs MCP

**What it gives you:** Ahrefs data inside Claude — organic keywords, top pages, backlinks, Domain Rating, traffic history, keyword volumes, SERPs.
**Used by:** `ahrefs` (lookups and keyword research), `competitor-research`, `seo` (routes to `ahrefs`)
**Access:** OAuth (recommended) or an MCP key (`AHREFS_MCP_KEY`) for the MCP server; optionally an API v3 key (`AHREFS_API_KEY`) for scripts.
**Cost:** needs a paid Ahrefs plan, **Lite or higher**. No extra charge for MCP; calls spend API units from the plan.
**Setup time:** ~5 minutes

| Plan | Price | API units / month |
|---|---|---|
| Lite | $129/mo | 200k |
| Standard | $249/mo | 800k |
| Advanced | $449/mo | 2M |
| Enterprise | $1,499/mo (annual) | 4M+ |

Starter and Free plans have no MCP or API access. From Lite up, plans include "direct access to API v3, Ahrefs MCP, and Ahrefs Connect"; units are shared between the three.

## 1. Connect — OAuth (recommended)

```bash
python3 skills/connect/scripts/kit.py mcp add ahrefs --oauth
#   = claude mcp add --scope user --transport http ahrefs https://api.ahrefs.com/mcp/mcp
```

Then in Claude Code: `/mcp` → ahrefs → Authenticate → pick the workspace → Allow. Ahrefs creates a dedicated MCP key for this connection; no key is stored on your machine.

**Desktop app / claude.ai:** Settings → Connectors → search "Ahrefs" → Connect.

## 1b. Connect — with an MCP key

1. Ahrefs → Account settings → API keys → **Generate MCP key**.
2. Put it into the keys file: `AHREFS_MCP_KEY=...`
3. `python3 skills/connect/scripts/kit.py mcp add ahrefs` — sends it as `Authorization: Bearer`.

To load fewer tools, append `?tools=essentials` to the URL.

## 2. Check

In Claude: *"Domain Rating and top 10 organic pages of example.com in Ahrefs."* The first call should be the free `subscription-info-limits-and-usage`.

## 3. Optional: an API v3 key for scripts

The `ahrefs` skill's scripts (`ahrefs_api.py` for raw pulls, `kw.py` for staged keyword research) use API v3, never the MCP endpoint.

1. Ahrefs → Account settings → API keys → **create an API v3 key** (a different key from the MCP key).
2. Put it into the keys file: `AHREFS_API_KEY=...`, then `kit.py doctor --live`.

Without an API v3 key, keyword research still works: `kw.py --via mcp` writes a plan of MCP calls, Claude makes them with the MCP tools, and `kw.py import` loads each saved result. Details in `skills/ahrefs/SKILL.md`.

## Safety

- **Set a monthly unit cap on the key** (Account settings → API keys). An agent pulling raw backlinks can burn thousands of units in one call.
- The tools behave as lookups, but Ahrefs doesn't document the MCP as read-only. Keep an eye on tool calls the first time.

## Gotchas

- **Don't write your own scripts against the MCP endpoint.** Ahrefs' terms say custom scripts, bridges and standalone JSON-RPC clients calling the MCP endpoint are not permitted. For scripted pulls use API v3 with an API v3 key — the `ahrefs` skill's `scripts/ahrefs_api.py` and `kw.py` do that.
- API v3 paths are not always the MCP tool name with the first dash turned into a slash (`site-explorer-referring-domains` is `site-explorer/refdomains`, `serp-overview` is `serp-overview/serp-overview`). `ahrefs_api.py` maps the names for you.
- MCP keys and API v3 keys are not interchangeable — the wrong one returns 401.
- Each call costs at least 50 units: cost = max(50, per-row cost × rows). Some fields cost 5–10 units per row. Details: `skills/ahrefs/references/unit-costs.md`.
- Money values come back in USD cents.
- Paid-traffic and ad-cost estimates are unreliable — don't put them in reports.

## Links

- MCP docs: <https://docs.ahrefs.com/en/mcp/docs/introduction> (Claude Code page: `/claude-code`)
- Units: <https://docs.ahrefs.com/en/api/docs/limits-consumption>
- Pricing: <https://ahrefs.com/pricing> · Keys: <https://app.ahrefs.com/account/api-keys>

*Checked 2026-10-01; API v3 plans and the `ahrefs` skill updated 2026-10-21.*
