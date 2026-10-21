# HyperFrames (HeyGen)

**What it gives you:** short videos built from code — HTML, CSS and GSAP animations rendered frame by frame to a deterministic MP4. End cards, title cards, animated offers, product-UI panels, explainers. Exact text, re-renderable, nothing spent per attempt.
**Used by:** the video skills: `video-build` builds and renders with it; `video-studio`, `video-moves`, `video-3d` and `video-check` work on HyperFrames projects. **Pairs with:** `ads-video-library` (name, store and review the renders), ElevenLabs (voiceover and sound).
**Required:** the HyperFrames skills below. `video-build` is a layer over them (`hyperframes`, `hyperframes-core`, `hyperframes-animation`, `hyperframes-cli`) and `video-studio` routes some jobs to the upstream `general-video`, `motion-graphics`, `product-launch-video` and `media-use` skills.
**Access:** none for local rendering. A HeyGen login only for cloud rendering, HeyGen voices / music and the hosted MCP.
**Cost:** free and open source (Apache-2.0) locally. Cloud rendering costs HeyGen credits (4K at 1.5×).
**Needs:** Node.js 22+, FFmpeg, Chrome (the CLI finds or downloads it).
**Setup time:** ~10 minutes

## 1. Install the skills — pick ONE route

```bash
# A) Claude Code plugin (recommended)
claude plugin marketplace add heygen-com/hyperframes
claude plugin install hyperframes@hyperframes

# B) standalone skills
npx skills add heygen-com/hyperframes          # choose "Core Skills" in the picker
```

Installing both duplicates every skill. In the desktop app, use **+ → Plugins → Add plugin** for route A.

## 2. Check the toolchain

```bash
npx hyperframes doctor           # Node, FFmpeg, Chrome, disk space
npx hyperframes browser ensure   # finds or downloads Chrome
```

## 3. First render

```bash
npx hyperframes init my-card && cd my-card
npx hyperframes preview          # live preview in the browser
npx hyperframes check            # lint + contrast + layout — fix everything before rendering
npx hyperframes render
```

Or ask Claude: *"Make a 6-second end card with our logo and 'Try it free'."* `video-studio` picks the motion-card recipe and builds it with HyperFrames.

## Safety and privacy

- **Telemetry is on by default**, and after login it is linked to your account email. Turn it off: `export HYPERFRAMES_NO_TELEMETRY=1` (add to your shell profile).
- `npx hyperframes publish` uploads the project and prints a link with a claim token — anyone with the link can see it. Treat it as sharing.

## Gotchas

- `check` measures text, not images: a logo invisible on its background passes. Look at rendered frames (`video-check`'s `stills.py` contact sheets).
- Units in `vmin` are identical in 1920×1080 and 1080×1920 — scale the whole stack on a wrapper for different aspects instead of re-specifying every size.
- `init` refreshes the skills; set `HYPERFRAMES_SKIP_SKILLS=1` to stop that.
- A non-interactive `npx skills add` without `--skill` installs all ~21 skills.
- `doctor` fails with less than 2 GB free disk (frame cache).
- `validate`, `inspect` and `layout` are deprecated aliases of `check`.

## Links

- <https://github.com/heygen-com/hyperframes> · Docs: <https://hyperframes.heygen.com> · Index for agents: <https://hyperframes.heygen.com/llms.txt>

*Checked 2026-10-01; video skills updated 2026-10-21.*
