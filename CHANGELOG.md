# Changelog

## v2.0.0 (2026-10-21)

Two new teams: SEO (four skills) and video (seven skills). Nineteen agents in all, twenty skills.

### New: the SEO team
- **`seo`**: the entry point for any SEO task. Routes work to the three skills below and carries six playbooks: structured data, site architecture, programmatic pages, competitor and comparison pages, AI search visibility, and an audit checklist (from coreyhaines31/marketingskills, MIT; `sync_upstream.py` refreshes them).
- **`gsc-insights`**: a local SQLite archive of the Search Console API (history survives Google's 16-month limit), twelve analysis recipes, a weekly report for Google Sheets and Slack, and a team digest that joins organic visits to sign-ups and trials from your GA4 BigQuery export.
- **`seo-tech-audit`**: crawler, URL Inspection, CrUX field data, Bing Webmaster, raw-vs-rendered check, findings ranked by the Google traffic at stake, developer tickets, and a backlog that tracks every finding week to week.
- **`ahrefs`** replaces `ahrefs-seo`: the same quick lookups, plus staged keyword research (discover → price under a unit budget → SERPs → cluster by shared top-10 URLs → prioritise against your Search Console positions), with a unit ledger and a monthly cap. Scripts use the Ahrefs API v3; with only an MCP plan, Claude makes the calls through the Ahrefs MCP tools and imports the results.
- One site config for all three: `~/.config/marketing-agent-kit/seo/<site>.toml`. A test suite for the SEO scripts in `tests/seo/`.

### New: the video team
- **`video-studio`** replaces `motion-card`: it decides the format (motion card, launch film, reference remake, generated scenes), writes the brief every specialist reads, holds the house laws learned on real films, and runs the specialists in order. End cards and title cards are its motion-card recipe.
- **`video-sound`**: ElevenLabs voiceover with a transcript gate and a check that brand names are said right; music cut to the beat grid; effects placed on picture events by their peak; a stereo mix that ducks music per spoken passage, with a true-peak limiter; checks that every effect is heard. A downloadable library (`library.py install`, ~150 MB) of 1,277 analysed CC0 sound effects and eight music beds (Sascha Ende, CC BY 4.0, and our own), with a catalogue and beat cues.
- **`video-build`**: the HyperFrames project scaffold, building from a real product UI, word-highlight captions in any language including Arabic and Hebrew, real-footage handling, and a catalogue of render traps.
- **`video-moves`**: 24 camera and editing moves with when to use each, staging, numbers, traps, working code (`camera-kit.js`) and the sound of each move.
- **`video-3d`**: deterministic three.js for film: objects and materials, data globes and maps, particles and GPU compute, post-processing, rendered looks (ASCII, toon, halftone, dither, CRT, pixel), glTF models, compositing, WebGPU; every capability marked proven or not.
- **`video-generated`**: generated people, rooms and objects through Atlas Cloud (Seedance, OmniHuman, Nano Banana), with measured prices and a doctrine that settles everything on stills first.
- **`video-check`**: the gates every film passes before you see it (claims, voice, reading time, stills, cut seams, loudness, sound against picture, transcript) and an independent review by fresh agents.

### Changed
- `connect`: new keys (`CRUX_API_KEY`, `BING_WMT_API_KEY`, `ATLAS_API_KEY`, `SLACK_WEBHOOK_URL`) with free live checks; `doctor` now reports `uv`, SEO site configs and the sound library.
- New connection guides: Search Console, CrUX, Bing Webmaster, Slack, Atlas Cloud. HyperFrames and ElevenLabs guides point at the video skills.
- `competitor-research` uses `ahrefs` for its SEO layer.
- `THIRD_PARTY_NOTICES.md` lists every borrowed piece and its licence.

### Upgrading from v0.2
- `motion-card` is gone: ask for the same card and `video-studio` builds it. Old `timeline.json` files work with `video-sound/scripts/mix.py` unchanged.
- `ahrefs-seo` is now `ahrefs`. `scripts/ahrefs_api.py` keeps its name and arguments.
- The video skills need the HyperFrames skills (`npx skills add heygen-com/hyperframes`) and the sound library (`python3 skills/video-sound/scripts/library.py install`).

## v0.2.0 (2026-10-12)

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
