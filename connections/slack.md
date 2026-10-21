# Slack (weekly SEO post)

**What it gives you:** the weekly SEO digest posted to a channel: visits → sign-ups → trials by source, visibility, open audit items, a trend chart.
**Used by:** `gsc-insights` (`weekly_digest.py`, `gsc_report.py`).
**Access:** either the Slack connector in Claude (no key) or an incoming webhook URL.
**Cost:** free.
**Setup time:** ~5 minutes

## Option A: the Slack connector (recommended)

claude.ai → **Settings → Connectors → Slack → Connect**, or in the desktop app **+ → Connectors**. Claude then posts the text and uploads the chart itself. Put the channel name and id into the site config (`[report] slack_channel`, `slack_channel_id`); Claude can find the id with the connector's channel search. Claude asks before the first post to a new channel.

## Option B: an incoming webhook

1. <https://api.slack.com/apps> → **Create New App** → From scratch → pick the workspace.
2. **Incoming Webhooks** → on → **Add New Webhook to Workspace** → pick the channel.
3. Put the URL into the keys file: `SLACK_WEBHOOK_URL=https://hooks.slack.com/services/...`.

A webhook posts text only. `gsc-insights` uses it for the detailed weekly report when it is set; the team digest and its chart go through the connector (without it, the text and the chart PNG stay in the report folder for you to post).

## Safety

- The webhook URL is a secret: anyone with it can post to the channel. Keep it in the keys file only.
- `kit.py doctor` never tests it, because a test would post a message.

*Checked 2026-10-21.*
