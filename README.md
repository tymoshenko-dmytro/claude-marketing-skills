# Claude Marketing Skills: AI agents for marketing in Claude Code

[![Release](https://img.shields.io/github/v/release/tymoshenko-dmytro/claude-marketing-skills)](https://github.com/tymoshenko-dmytro/claude-marketing-skills/releases)
[![License: MIT](https://img.shields.io/badge/license-MIT-blue)](LICENSE)
[![Claude Code plugin](https://img.shields.io/badge/Claude_Code-plugin-D97757)](#installation)

https://github.com/user-attachments/assets/81a236a7-40fb-4f4c-8547-6c34cb9c514a

*The team at work in 66 seconds: one request goes round the whole loop, research, strategy, launch and analysis, and the weekly report starts the next one. The film was made with the kit's own video skills. Sound on.*

Claude Code skills that turn Claude into an AI growth team. Twenty agents research competitors, pull ads from the public libraries, run SEO from Search Console data to technical audits and keyword research, read GA4, screenshot funnels, make ad images, produce videos with voice, music and 3D, and check every line of copy. Each one works on your real data, not on general advice. Use them to strengthen a growth team, or to run growth without one. Install them as a Claude Code plugin or with `npx skills`.

Works with [Claude Code](https://code.claude.com) and any agent that supports the [Agent Skills](https://agentskills.io) format.

Built by [Dmytro Tymoshenko](https://www.linkedin.com/in/tymoshenko-dmytro), Head of Growth at Palabra.ai and ex-CEO of Eightify.

## Meet the team: 20 AI marketing agents

![Claude Marketing Skills: agents with job titles, each a Claude Code skill](docs/images/cover.png)

### Research

| Agent | Skill | What it does | Works with |
|---|---|---|---|
| **Head of Market Intelligence** | [`competitor-research`](skills/competitor-research/) | Builds a full dossier on a competitor from its domain: product, pricing, customers, ads, SEO, team and press. It runs the other research agents and gives you a knowledge base and an HTML report | Parallel, SearchApi, Ahrefs |
| **Research Analyst** | [`parallel-research`](skills/parallel-research/) | Does deep research on any question: a quick sourced search in seconds, or a cited report in 5 to 60 minutes | Parallel |
| **Paid Media Analyst** | [`ads-parser`](skills/ads-parser/) | Gets every ad a company runs in the LinkedIn, Google and Meta libraries: text, images, videos, run dates, and impressions where the library shows them | SearchApi |

### SEO

| Agent | Skill | What it does | Works with |
|---|---|---|---|
| **Head of SEO** | [`seo`](skills/seo/) | The entry point for any SEO question. Routes the work to the right specialist and holds the playbooks: structured data, site architecture, programmatic pages, comparison pages, AI search visibility, audit checklist | the three below |
| **Search Analyst** | [`gsc-insights`](skills/gsc-insights/) | Keeps a local archive of your Search Console data beyond Google's 16 months. Twelve recipes: striking distance, low CTR, cannibalization, decay, new queries, brand vs non-brand, update impact. A weekly report and a team digest for Slack and Google Sheets, joined to sign-ups from GA4 | Search Console, BigQuery (optional) |
| **Technical SEO Specialist** | [`seo-tech-audit`](skills/seo-tech-audit/) | Crawls your site, asks Google's index about every URL, reads real-user Core Web Vitals and Bing, compares raw and rendered HTML. Turns the evidence into developer tickets ranked by the traffic at stake, and tracks them week to week | Search Console, CrUX, Bing |
| **SEO Researcher** | [`ahrefs`](skills/ahrefs/) | Quick Ahrefs lookups for any domain, and staged keyword research: discover, price under a unit budget, read the top-10 SERPs, cluster keywords one page can rank for, join your Google positions, decide improve / new page / skip | Ahrefs |

### Measurement and UX

| Agent | Skill | What it does | Works with |
|---|---|---|---|
| **Growth Analyst** | [`ga4-reports`](skills/ga4-reports/) | Answers GA4 questions asked in plain words: traffic, channels, period comparisons and funnel drop-off | Google login |
| **UX Researcher** | [`funnel-screenshots`](skills/funnel-screenshots/) | Goes through a competitor's quiz or onboarding funnel and takes a retina iPhone screenshot of every screen, up to the paywall | Playwright (installs itself) |

### Creative

| Agent | Skill | What it does | Works with |
|---|---|---|---|
| **Designer** | [`image-gen`](skills/image-gen/) | Makes ad images, blog covers and illustrations, and checks that the text in each picture came out as written | OpenAI |
| **Video Producer** | [`video-studio`](skills/video-studio/) | Starts every video: picks the format (end card, launch film, UI walkthrough, a remake of a reference ad), writes the brief, holds the house laws and runs the six specialists below in order | the six below |
| **Sound Designer** | [`video-sound`](skills/video-sound/) | Voiceover with a transcript check that every brand name is said right, music cut to the film's beat grid, effects from a library of 1,277 analysed CC0 sounds, a mix that ducks music per spoken line | ElevenLabs, sound library |
| **Motion Designer** | [`video-build`](skills/video-build/) | Builds the film in code from measured audio timings, from your real product UI, with word-by-word captions in any language (Arabic and Hebrew too), and avoids the known render traps | HyperFrames |
| **Video Editor** | [`video-moves`](skills/video-moves/) | 24 camera and editing moves (dolly zoom, whip pan, match cut, speed ramp, J and L cuts...) with when to use each, working code and the sound of each move | HyperFrames |
| **3D Artist** | [`video-3d`](skills/video-3d/) | Real 3D in a film: logos as objects, data globes, particles, glTF models, post effects and rendered looks (ASCII, toon, halftone, pixel), every frame deterministic | three.js, HyperFrames |
| **AI Video Artist** | [`video-generated`](skills/video-generated/) | Generated people, rooms and objects, with a doctrine that settles everything on cheap stills before paying for video | Atlas Cloud |
| **Video QA Reviewer** | [`video-check`](skills/video-check/) | Checks every film before you see it: claims against the source, reading time per line, one-frame glitches at every cut, loudness, effects heard, a transcript, and an independent review by fresh agents | FFmpeg, Whisper |
| **Creative Ops Manager** | [`ads-video-library`](skills/ads-video-library/) | Names your ad videos, files them and lists them in a catalogue. It also makes a review page where each video gets approved or rejected | FFmpeg, Google Drive (optional) |

### Copy

| Agent | Skill | What it does | Works with |
|---|---|---|---|
| **Senior Marketing Copywriter** | [`plain-copy`](skills/plain-copy/) | Rewrites copy so a stranger understands it in one read | none |
| **Copy Critic** | [`copy-critic`](agents/copy-critic.md) | Reads every line the way a stranger would, gives it a verdict, and hands back the rewrite | none |
| *Onboarding* | [`connect`](skills/connect/) | Sets up keys, Google login, Search Console, MCP servers and the sound library, then runs a health check | none |

## How the team works together

```
                         ┌─────────────────────────────────────┐
                         │               connect               │
                         │ keys · MCP · site config · library  │
                         └──────────────────┬──────────────────┘
               ┌────────────────────────────┴────────────────────────────┐
               ▼                                                         ▼
 ┌───────────────────────────────┐                   ┌───────────────────────────────┐
 │ RESEARCH                      │                   │ SEO                           │
 │ competitor-research           │                   │ seo (routes, playbooks)       │
 │   ├ parallel-research         │                   │   ├ gsc-insights              │
 │   ├ ads-parser                │                   │   ├ seo-tech-audit            │
 │   └ ahrefs ───────────────────┼───── shared ──────┼── └ ahrefs                    │
 └───────────────┬───────────────┘                   └───────────────┬───────────────┘
 ┌───────────────┴───────────────┐                   ┌───────────────┴───────────────┐
 │ MEASUREMENT                   │                   │ CREATIVE                      │
 │ ga4-reports                   │                   │ image-gen                     │
 │ funnel-screenshots            │                   │ video-studio                  │
 │                               │                   │   ├ video-sound   video-moves │
 │                               │                   │   ├ video-build   video-3d    │
 │                               │                   │   ├ video-generated           │
 │                               │                   │   └ video-check (gate)        │
 │                               │                   │ ads-video-library             │
 └───────────────┬───────────────┘                   └───────────────┬───────────────┘
                 └────────── findings, tickets, screens, drafts ─────┘
                                        ▼
                         ┌─────────────────────────────────────┐
                         │      plain-copy  ↔  copy-critic     │
                         │     every line gets a verdict       │
                         └─────────────────────────────────────┘
```

## Read before you install

Install only the skills you will use this month. Every installed skill adds its description to every conversation, and v2 has twenty. Then do the **Adapt it** part of each one: the skills work best once they hold your corrections, report rules, site config, funnel events and brand laws.

## Installation

### Option 1: Claude Code plugin (recommended)

```bash
/plugin marketplace add tymoshenko-dmytro/claude-marketing-skills
/plugin install marketing-agent-kit@marketing-agent-kit
```

### Option 2: skills CLI (pick what you need)

```bash
npx skills add tymoshenko-dmytro/claude-marketing-skills --list                     # see all skills
npx skills add tymoshenko-dmytro/claude-marketing-skills --skill ads-parser         # one skill
npx skills add tymoshenko-dmytro/claude-marketing-skills --skill seo --skill gsc-insights --skill seo-tech-audit --skill ahrefs
```

Skills in a family call each other by folder name, so install a family together: the four SEO skills, or `video-studio` with the video skills it routes to.

### Option 3: clone and copy

```bash
git clone https://github.com/tymoshenko-dmytro/claude-marketing-skills.git
cp -R claude-marketing-skills/skills/ads-parser ~/.claude/skills/
cp claude-marketing-skills/agents/copy-critic.md ~/.claude/agents/
```

### Video: two extra steps

The video skills build on the [HyperFrames](https://github.com/heygen-com/hyperframes) skills (Apache-2.0), installed separately, and use a sound library that is too big for git:

```bash
npx skills add heygen-com/hyperframes                                 # or the plugin, see connections/hyperframes-cli.md
python3 skills/video-sound/scripts/library.py install                 # ~150 MB: 1,277 CC0 effects and 8 music beds, with a catalogue
python3 skills/video-sound/scripts/library.py venv                    # the analysis environment (librosa)
```

## First run

Ask Claude: **"Set up the kit for competitor research"** (or for SEO, or for video). The `connect` skill creates a private keys file, helps you get each key, and checks every connection with a free request.

## How to use Claude Code for marketing

Ask in plain words. Claude picks the right agent:

```
"Research competitor example.com and build a knowledge base"        → competitor-research
"What ads is Example running on LinkedIn and Meta right now?"        → ads-parser
"Why did our organic traffic drop last week?"                        → seo → gsc-insights, seo-tech-audit
"Run a technical SEO audit and write tickets for the developers"     → seo-tech-audit
"What should we write about for the German market?"                  → ahrefs (keyword research)
"Which pages bring example.com the most organic traffic?"            → ahrefs
"Compare last month's sign-ups by channel with the month before"     → ga4-reports
"Screenshot every step of the quiz at example.com/start"             → funnel-screenshots
"Make two ad images for this headline, draft quality"                → image-gen
"Make a 10-second end card: 'Spring sale: 20% off'"                  → video-studio (motion-card recipe)
"Make a 20-second launch video of our new feature"                   → video-studio → the video team
"Would a stranger understand this headline?"                         → plain-copy + copy-critic
```

You can also run a skill directly: `/competitor-research`, `/seo`, `/video-studio`.

## Why install these instead of writing your own?

You can write a skill in an evening. Making one that works on real data takes months of fixing what goes wrong. These skills already contain those fixes:

- **They do the work, not give advice.** Each skill connects to a real source (Search Console, Ahrefs, GA4, Meta, LinkedIn and Google ad libraries, Parallel, a real browser, OpenAI images, ElevenLabs, HyperFrames) and returns a file you can use: a dossier, a report, developer tickets, screenshots, images, a rendered video.
- **They know the traps.** Each skill already handles the cases where an ad library, Ahrefs, Search Console or GA4 gives misleading data, and the render traps that cost a video a wasted hour.
- **Every fact has a source.** Research skills link each claim to the page it came from. SEO numbers come from a script run in the same task, with their period, or the skill says the data is missing.
- **Setup takes minutes.** The `connect` skill walks you through each key, keeps the keys out of the chat, and tests each one with a free request.
- **They work as one team.** The research lead runs the researcher, the paid-media analyst and the SEO researcher together. The head of SEO routes every SEO question to the right specialist. The video producer runs six specialists in a fixed order, and nothing ships before the QA reviewer passes it.
- **They are templates.** Every skill ends with an **Adapt it** section, so it learns your rules, your site, your funnel and your brand.

## Claude Code skills by category

### Research and intelligence
- `competitor-research`: full competitor dossier (runs the next three)
- `parallel-research`: deep, sourced web research
- `ads-parser`: a Claude ads skill that pulls competitor ads from the public libraries
- `ahrefs`: Ahrefs data for any domain and staged keyword research

### SEO
- `seo`: a Claude SEO skill that routes every SEO task and carries the playbooks
- `gsc-insights`: Google Search Console archive, analysis recipes and a weekly report
- `seo-tech-audit`: technical SEO audit with a tracked developer backlog
- `ahrefs`: keyword research and SERP-based clustering

### Measurement and UX
- `ga4-reports`: GA4 reports from a plain question
- `funnel-screenshots`: every screen of a funnel, up to the paywall

### Creative
- `image-gen`: ad images, covers and illustrations
- `video-studio`: AI video production in Claude Code, from brief to QA
- `video-sound`, `video-build`, `video-moves`, `video-3d`, `video-generated`, `video-check`: the specialists it runs
- `ads-video-library`: naming, catalogue and review page for ad videos

### Copy
- `plain-copy` and `copy-critic`: clear copy, a verdict and a rewrite for every line

## Keys and privacy

All keys live in one file outside any repository: `~/.config/marketing-agent-kit/.env` (chmod 600). Never paste keys into a chat. SEO site configs live next to it in `~/.config/marketing-agent-kit/seo/`, the sound library in `~/.local/share/marketing-agent-kit/video-library`. Research output and catalogues are in `.gitignore`. [More on connections →](connections/README.md)

## Requirements

- Python 3.9+ (most scripts use the standard library only)
- [`uv`](https://docs.astral.sh/uv/) for the SEO scripts (they declare their own dependencies and need Python 3.11+, which `uv` fetches if missing) and the sound library's analysis environment
- FFmpeg for the video skills and `ads-video-library`; Node.js 22+ and the HyperFrames skills for video; a Whisper CLI for the voice and transcript checks (`mlx-whisper` on Apple Silicon, `openai-whisper` elsewhere)
- Node.js 18+ for Playwright MCP; `gcloud` + `pipx` for Google services; ~400 MB for `funnel-screenshots` (its setup installs Playwright and Chromium); ~150 MB for the sound library plus ~350 MB for its analysis environment

## What's new

- **v2.1:** a world-film recipe in the video studio: one drawn world, a cast of characters and one camera instead of a run of slides. The film at the top was made with it.
- **v2.0:** an SEO team of four (Search Console archive and weekly report, technical audit with a developer backlog, Ahrefs keyword research, SEO playbooks) and a video studio of seven (voice and sound, HyperFrames builds, 24 camera moves, three.js 3D, generated shots, QA).

[Full changelog →](CHANGELOG.md)

## Works well with

Good work by others. Read before installing, same rule as above.

| What | Why |
|---|---|
| Anthropic document skills (`docx`, `pdf`, `pptx`, `xlsx`) | decks, reports and spreadsheets as files, available in Claude apps |
| [Higgsfield skills](https://github.com/higgsfield-ai/skills) (MIT) | generative video and image ads |
| [/brag](https://github.com/latent-spaces/brag) (MIT) | launch videos of what you built; the launch-film format here started from it |
| [/watch](https://github.com/bradautomates/claude-video) (MIT) | a model that watches and listens to a film; `video-check` uses it for a "listen" pass |
| [Impeccable](https://github.com/pbakaus/impeccable) | design review commands (audit, polish, critique) for landing pages |
| [Humanizer](https://github.com/blader/humanizer) (MIT) | removing AI-writing patterns from long texts |

## Credits

- SEO playbooks in `skills/seo/references/` are from [marketingskills](https://github.com/coreyhaines31/marketingskills) by Corey Haines (MIT).
- The launch-film format, the claim-grounding check, poster selection and the frame-0 technique are adapted from [/brag](https://github.com/latent-spaces/brag) by Shunit Haviv Hakimi (MIT).
- Peak-aligned effects, the per-band gain solver and the sound-against-picture check are adapted from [opus-sound-layer](https://github.com/Bodila51/opus-sound-layer) (MIT). The cut-seam scanner and the caption engine are ported from [nanoclip-cutting-room](https://github.com/latent-spaces/nanoclip-cutting-room) (MIT).
- Sounds: [Kenney](https://kenney.nl), [Freesound](https://freesound.org) contributors and unicae_games on OpenGameArt (all CC0, credited in the library). Music: Sascha Ende, [ende.app](https://ende.app) (CC BY 4.0).
- Full notices: [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md). Connection facts checked against vendor documentation on 2026-10-01 and 2026-10-21.

## Contributing

Found a way to improve a skill? Have a new one? [Open a PR](CONTRIBUTING.md). Question or problem? [Open an issue](https://github.com/tymoshenko-dmytro/claude-marketing-skills/issues).

## License

[MIT](LICENSE) © 2026 Dmytro Tymoshenko · [LinkedIn](https://www.linkedin.com/in/tymoshenko-dmytro). Third-party code keeps its own licence: [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).
