# Connections

Every service the kit uses, one guide each: what it gives you, what it costs, how to get access, how to connect it to Claude Code, how to check it works, and what to watch out for. Facts checked against vendor docs on **2026-10-01**, new guides on **2026-10-21** — services change, so each guide links to its sources.

Commands in these guides run from the kit's folder (`python3 skills/connect/scripts/kit.py …`). Installed as a plugin? Just ask Claude — the `connect` skill knows where its scripts are.

The fastest path is the **`connect` skill**: ask Claude "set up the kit" and it walks you through only the services you need, runs a health check and registers MCP servers for you.

## Overview

| Service | What for | Access | Cost to start | Guide |
|---|---|---|---|---|
| Parallel.ai | deep web research with citations | API key (Search MCP works without one) | free credits on signup | [parallel-api.md](parallel-api.md) |
| SearchApi.io | ad libraries: LinkedIn, Google, Meta | API key or OAuth MCP | 100 free requests | [searchapi.md](searchapi.md) |
| Ahrefs | SEO data, keyword research | OAuth or MCP key; optional API v3 key for scripts | paid plan, Lite+ ($129/mo) | [ahrefs-mcp.md](ahrefs-mcp.md) |
| Google Search Console | your site's search data, index status per URL | service account (read-only) | free | [search-console.md](search-console.md) |
| Chrome UX Report | real-user Core Web Vitals | API key | free | [crux-api.md](crux-api.md) |
| Bing Webmaster Tools | Bing's view of your site (it also feeds AI search) | API key | free | [bing-webmaster.md](bing-webmaster.md) |
| Slack | the weekly SEO post | connector or webhook | free | [slack.md](slack.md) |
| Google Analytics 4 | traffic, conversions, funnels | gcloud login | free | [ga4-mcp.md](ga4-mcp.md) |
| Google Ads | campaigns, spend, conversions (read-only) | gcloud login | free | [google-ads-mcp.md](google-ads-mcp.md) |
| BigQuery | SQL over GA4 export and your own data | OAuth client or gcloud login | 1 TiB of queries free per month | [bigquery.md](bigquery.md) |
| Stripe | revenue, subscriptions, payments | OAuth or Agent key | free | [stripe-mcp.md](stripe-mcp.md) |
| Playwright | a browser the agent drives (`funnel-screenshots` ships its own) | none | free | [playwright-mcp.md](playwright-mcp.md) |
| OpenAI Images | image generation and editing | API key | pay per image | [openai-images-api.md](openai-images-api.md) |
| ElevenLabs | voiceover, sound effects | API key or OAuth MCP | free tier (no SFX) | [elevenlabs-api.md](elevenlabs-api.md) |
| HyperFrames | videos rendered from HTML/CSS | none for local renders | free locally | [hyperframes-cli.md](hyperframes-cli.md) |
| Higgsfield | generative image and video | browser login | credits | [higgsfield.md](higgsfield.md) |
| Atlas Cloud | generated people, rooms and objects for video (Seedance, OmniHuman, Nano Banana) | API key | pay per generation | [atlas-cloud.md](atlas-cloud.md) |

## Three kinds of connection

- **MCP server** — a plug-in that gives Claude new tools (`mcp__ahrefs__…`). Remote servers are a URL; local ones are a program Claude starts.
- **API key + script** — a skill runs a small script that calls the service. The key lives in the kit's keys file.
- **CLI** — a command-line program the agent runs (`gcloud`, `npx hyperframes`, `higgsfield`).

## Where things are stored

| What | Where |
|---|---|
| The kit's API keys | `~/.config/marketing-agent-kit/.env` — chmod 600, outside every repository |
| Google login | `~/.config/gcloud/application_default_credentials.json` (written by `gcloud`) |
| MCP servers, all projects | `~/.claude.json` (`claude mcp add --scope user`) — the desktop app reads this |
| MCP servers, one project, shared with the team | `.mcp.json` in the project (`--scope project`) — use `${VAR}` instead of real keys |

**Never paste a key into a chat.** Chats are saved to disk. Put keys into the keys file (`connect` skill → `kit.py open`).

## Adding an MCP server

**Terminal (Claude Code CLI):**

```bash
claude mcp add --scope user --transport http <name> <url>                         # remote, OAuth
claude mcp add --scope user --transport http <name> <url> --header "Authorization: Bearer <KEY>"
claude mcp add --scope user <name> -e KEY=value -- <command> <args>               # local program (name BEFORE -e)
```

Then, for OAuth servers, run `/mcp` inside Claude Code → pick the server → Authenticate. Or let the kit do it: `kit.py mcp add <name>` reads the key from the keys file and never prints it.

**Desktop app (Code tab):** it reads the same `~/.claude.json`, so anything added with `--scope user` shows up. Without a terminal: open the app's built-in terminal (Ctrl+`) and run the same command, or add a listed service with **+ → Connectors** next to the prompt.

**claude.ai connectors:** services in Claude's connector directory (Stripe, Ahrefs, ElevenLabs and others) can be connected in Settings → Connectors. They also appear in Claude Code when you sign in with a claude.ai subscription.

## Keep agents read-only

Add deny rules for write tools to `~/.claude/settings.json` (all projects) or `.claude/settings.json` (one project):

```json
{
  "permissions": {
    "deny": [
      "mcp__stripe__stripe_api_write",
      "mcp__bigquery__execute_sql",
      "mcp__bigquery__cancel_job"
    ]
  }
}
```

Tool names follow `mcp__<server name>__<tool>`; check the exact names with `/mcp` after connecting. Plugin-installed servers have longer names (`mcp__plugin_<plugin>_<server>__<tool>`).
