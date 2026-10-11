# Changelog

## v0.2.0 (2026-10-11)

The kit is now called **Claude Marketing Skills**: an AI growth team for Claude Code.

### New
- **Overview video** in the README: what the ten agents do, from competitor research to ads to analytics, in 70 seconds.
- **Install with `npx skills`.** Skill descriptions are now strict YAML, so `npx skills` finds all 11 skills (it found 1 before).
- **README** rewritten around the team: why install these instead of writing your own, the ten agents with job titles, how they work together, install options and categories. New cover.
- **Community files:** contributing guide, security policy, code of conduct, a bug form and a pull request template.

### Changed
- Repository renamed from `marketing-agent-kit` to `claude-marketing-skills`. Old links redirect.
- Plugin display name, description and version 0.2.0.

Video credits: music "The Inspiring Ads" by FASSounds (Pixabay); voice by ElevenLabs.

## v0.1.1 (2026-10-01)

Fixes from an external review, plus a rewritten README.

- Every script reads `~/.config/marketing-agent-kit/.env` with the same rule as `kit.py`; a key typed in front of the template's comment no longer swallows the comment. `ga4.py` reads `GA4_PROPERTY_ID` from the keys file too.
- `kit.py mcp add --scope project` writes `${VAR}` references into `.mcp.json` instead of the key.
- `funnel-screenshots` writes a `.gitignore` for files that can hold session cookies and the email you typed.
- `ads-video-library`: the `id` includes language and aspect; the catalogue is merged instead of overwritten.
- `motion-card` voice check keeps the letters of every script, so a Cyrillic line no longer matches anything.
- README rewritten around the job each skill takes on; Russian trigger phrases removed from skill descriptions.

## v0.1.0 (2026-10-01)

First public release.
