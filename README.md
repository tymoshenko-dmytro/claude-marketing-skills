# Marketing Agent Kit: Claude Code marketing skills for growth teams

[![Release](https://img.shields.io/github/v/release/tymoshenko-dmytro/claude-marketing-skills)](https://github.com/tymoshenko-dmytro/claude-marketing-skills/releases)
[![License: MIT](https://img.shields.io/badge/license-MIT-blue)](LICENSE)
[![Claude Code plugin](https://img.shields.io/badge/Claude_Code-plugin-D97757)](#install)

**Free Claude Code skills that let one marketer do the work of a growth team.**

![Marketing Agent Kit: 11 Claude Code marketing skills and a copy critic](docs/images/cover.png)

[Claude Code](https://code.claude.com) is Anthropic's AI agent. Each skill in this kit teaches it one job that a growth team usually gives to a specialist, from competitor research and SEO data to ad images and copy review. You give Claude the task and decide what to do with the result. Long jobs, like a full competitor dossier, run in the background while you work on something else.

Built from real work at a B2B SaaS growth team in 2026, with the company-specific parts taken out so you can adapt each skill to your own work.

## The jobs, and who usually does them

| Usually a job for | What you get | Skill | Needs |
|---|---|---|---|
| a competitive-intelligence analyst | A dossier on a competitor from just its website address: product, pricing, customers, community, ads, SEO, team and press, as a knowledge base and an HTML report. | [`competitor-research`](skills/competitor-research/SKILL.md) | Parallel, SearchApi, Ahrefs |
| a desk researcher | Web research on a question you set, with links to its sources: a quick search in minutes, or a deep report that can take up to an hour. | [`parallel-research`](skills/parallel-research/SKILL.md) | Parallel |
| a paid-media analyst | The ads a company has in the public LinkedIn, Google and Meta ad libraries, with each ad's text, run dates and link, and impressions where the library shows them. | [`ads-parser`](skills/ads-parser/SKILL.md) | SearchApi |
| an SEO specialist | Organic keywords, top pages, backlinks, Domain Rating and search volumes for any website, with a guide to what each request costs on your Ahrefs plan. | [`ahrefs-seo`](skills/ahrefs-seo/SKILL.md) | Ahrefs (paid) |
| a web analyst | Google Analytics 4 reports from a plain question, including period comparisons and where people drop out of your funnel, with notes on the reporting mistakes people usually make. | [`ga4-reports`](skills/ga4-reports/SKILL.md) | Google login |
| a UX researcher | A high-resolution iPhone screenshot of each screen in a competitor's quiz or onboarding funnel, including the paywall and discount pop-ups, up to the payment form, which it leaves empty. | [`funnel-screenshots`](skills/funnel-screenshots/SKILL.md) | Python (Playwright installs itself) |
| a designer | Ad images, blog covers and landing-page illustrations made with OpenAI GPT Image, as drafts or final versions, and a check that any text in the picture came out as written. | [`image-gen`](skills/image-gen/SKILL.md) | OpenAI key |
| a motion designer | Short animated video cards, such as an end card, a title card or an animated call to action, with voiceover. They are built from code, so every word appears exactly as written and you can edit and render them again. | [`motion-card`](skills/motion-card/SKILL.md) | Node 22+, FFmpeg, ElevenLabs |
| a creative-operations manager | Your finished ad videos named and filed by month, language and type, and listed in a CSV or Google Sheet, with a cover image and a review page for approving or rejecting each one. | [`ads-video-library`](skills/ads-video-library/SKILL.md) | FFmpeg |
| an editor | Edits that make your copy clear to a stranger in one read and stop it sounding AI-written, plus a critic agent that gives each line a verdict and a rewrite. | [`plain-copy`](skills/plain-copy/SKILL.md) + [`copy-critic`](agents/copy-critic.md) | — |

[`connect`](skills/connect/SKILL.md) sets all of this up: it walks you through each key, registers the MCP servers and tests every key with a free request.

**The critic.** [`copy-critic`](agents/copy-critic.md) reads ad copy like a stranger scrolling a feed and returns a verdict and a rewrite for every line. It started as a critic trained on one founder's comments; [here is how to train your own on your corrections](docs/train-your-critic.md).

**Connections.** One guide per service with access, cost, setup, a check and the gotchas: [connections/](connections/README.md). Google Ads, GA4, Ahrefs, Stripe, BigQuery, Playwright, Parallel, SearchApi, ElevenLabs, OpenAI Images, HyperFrames and Higgsfield.

## Things to ask

Once the kit is installed, plain requests are enough. Claude picks the skill from what you ask:

- "Research competitor example.com and build a knowledge base"
- "What ads is Example running on LinkedIn and Meta right now?"
- "Which pages bring example.com the most organic traffic?"
- "Compare last month's signups by channel with the month before"
- "Screenshot every step of the quiz at example.com/start, including the paywall"
- "Make two ad images for this headline, draft quality"
- "Make a 10-second end card that says 'Spring sale: 20% off', with a female voiceover"
- "Name these ad videos, add them to the catalogue and make me a review page"
- "Would a stranger understand this headline?"

## Read before you install

**Don't install skills blindly, this kit included.** Every installed skill adds its description to every conversation and competes for Claude's attention, and a skill written for someone else's workflow quietly does things their way. Treat these as templates:

1. Read the `SKILL.md` of the ones you want. They're short.
2. Install only what you'll use this month.
3. Each skill ends with **"Adapt it"**. Do that part: the skills get good when they hold *your* corrections, your report rules, your funnel events, your copy patterns and your brand.

## Install

**As a plugin** (Claude Code terminal or desktop app):

```
/plugin marketplace add tymoshenko-dmytro/claude-marketing-skills
/plugin install marketing-agent-kit@marketing-agent-kit
```

Skills are then available as `/marketing-agent-kit:<skill>`; Claude also picks them up automatically from what you ask.

**Or copy what you want:**

```bash
git clone https://github.com/tymoshenko-dmytro/claude-marketing-skills.git
cp -R claude-marketing-skills/skills/ads-parser ~/.claude/skills/        # one skill, all projects
cp claude-marketing-skills/agents/copy-critic.md ~/.claude/agents/       # the critic
```

Use `<project>/.claude/skills/` instead of `~/.claude/skills/` to scope a skill to one project.

## First run

Ask Claude: **"Set up the kit for competitor research"** (or whatever you want to do). The `connect` skill creates a private keys file, walks you through getting each key, registers MCP servers and runs a health check:

```bash
python3 skills/connect/scripts/kit.py init           # ~/.config/marketing-agent-kit/.env, chmod 600
python3 skills/connect/scripts/kit.py doctor --live  # what works, what's missing
```

## Keys and privacy

- All keys live in **one file outside any repository**: `~/.config/marketing-agent-kit/.env` (template: [.env.example](.env.example)). You type them in yourself.
- **Never paste keys into a chat**: chats are saved to disk. The scripts read the file and never print keys.
- A server registered for a shared project (`kit.py mcp add … --scope project`) gets a `${VAR}` reference in `.mcp.json`, never the key itself.
- Prefer OAuth where a service offers it, read-only permissions, and spending caps. Each connection guide says how.
- Research outputs (`raw/`, `dist/`, catalogues) are in `.gitignore`, and `funnel-screenshots` keeps its browser session and typed values out of git wherever you save them. Keep client data out of your forks.

## Requirements

- Python 3.9+ (scripts use the standard library only; Google Drive mode of `ads-video-library` needs `pip install google-auth requests`)
- FFmpeg for `ads-video-library` and `motion-card`; Node.js 18+ for Playwright MCP, 22+ for HyperFrames; `gcloud` + `pipx` for Google services; ~400 MB for `funnel-screenshots` (its setup installs Playwright and Chromium)

## What else I use (not included)

Good work by others. Read before installing, same rule as above.

| What | Why |
|---|---|
| [Marketing Skills](https://github.com/coreyhaines31/marketingskills) by Corey Haines (MIT) | `product-marketing` creates a product-context file the other skills (and `copy-critic`) read; also CRO, copywriting, SEO audit, emails, A/B tests |
| Anthropic document skills (`docx`, `pdf`, `pptx`, `xlsx`) | decks, reports and spreadsheets as files, available in Claude apps |
| [HyperFrames](https://github.com/heygen-com/hyperframes) (Apache-2.0) | videos rendered from HTML/CSS; pairs with `ads-video-library` |
| [Higgsfield skills](https://github.com/higgsfield-ai/skills) (MIT) | generative video and image ads |
| [/brag](https://github.com/latent-spaces/brag) (MIT) | launch videos of what you built; inspired the poster / frame-0 step here |
| [Impeccable](https://github.com/pbakaus/impeccable) | design review commands (audit, polish, critique) for landing pages |
| [Humanizer](https://github.com/blader/humanizer) (MIT) | removing AI-writing patterns from long texts |

## Credits

- Poster selection and the frame-0 technique in `ads-video-library` are adapted from [/brag](https://github.com/latent-spaces/brag) by Shunit Haviv Hakimi (MIT).
- Connection facts checked against vendor documentation on 2026-10-01.

## Questions and contributions

Questions and ideas: [Discussions](https://github.com/tymoshenko-dmytro/claude-marketing-skills/discussions). Bugs: [open an issue](https://github.com/tymoshenko-dmytro/claude-marketing-skills/issues/new/choose). How to contribute: [CONTRIBUTING.md](CONTRIBUTING.md).

## License

[MIT](LICENSE) © 2026 Dmytro Tymoshenko · [LinkedIn](https://www.linkedin.com/in/tymoshenko-dmytro)
