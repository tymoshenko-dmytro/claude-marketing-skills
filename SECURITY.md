# Security

## Report a vulnerability

Please do not open a public issue about a security problem.
Use [private vulnerability reporting](https://github.com/tymoshenko-dmytro/claude-marketing-skills/security/advisories/new) instead.
I aim to reply within 7 days.

## What counts

- A script that prints, logs or sends an API key.
- A skill that writes keys or client data into a place that git tracks.
- A dependency or command in the setup that runs untrusted code.

## Supported versions

Only the latest release gets fixes.

## Your keys

All keys live in `~/.config/marketing-agent-kit/.env` (chmod 600), outside any repository. Never paste keys into a chat. If you think a key leaked, revoke it at the vendor first, then report.
