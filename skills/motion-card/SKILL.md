---
name: motion-card
description: >-
  Build a short branded video from code instead of filming or generating it — an end card, a title card, an animated offer or CTA card, a product-UI panel with animated text, a logo sting, a lower third — rendered from HTML/CSS/GSAP to MP4 with HyperFrames, with voiceover and sound effects from ElevenLabs. Exact text, deterministic, re-renderable for free. Use when a piece must be pixel-exact and repeatable, or a set of cards must share one template. Triggers: "make an end card", "title card", "animated CTA", "logo sting", "simple video with voiceover". Not for generative footage of people or scenes.
---

# Motion card

Short branded videos assembled from code: HTML + CSS + one paused GSAP timeline, rendered to MP4 by [HyperFrames](https://hyperframes.heygen.com), with audio from ElevenLabs. Deterministic and re-renderable; nothing is spent per attempt except the audio, so iterate freely.

**Use this** for end cards, title cards, offer / CTA cards, product-UI panels with animated text, logo stings, lower thirds — anything where the text must be exactly right. **Don't** use it for generated footage of people, rooms or objects; that's a generative video model.

## Needs

- Node.js 22+, FFmpeg, HyperFrames (`npx hyperframes doctor`) — `connections/hyperframes-cli.md`. The HyperFrames skills help a lot; install them as that guide says.
- `ELEVENLABS_API_KEY` in `~/.config/marketing-agent-kit/.env` — `connections/elevenlabs-api.md`. A paid plan is needed for sound effects.
- For the speech check (`--gate`): a Whisper CLI — `pipx install mlx-whisper` (Apple Silicon) or `pipx install openai-whisper`.

ElevenLabs endpoints used:

| | |
|---|---|
| `POST /v1/text-to-speech/{voice_id}` | speech. `eleven_multilingual_v2` (default here) for anything non-English; `eleven_v3` / `eleven_v4` for expressive English — test before switching |
| `POST /v1/sound-generation` | sound effects, `duration_seconds` 0.5–30 |

`GET /v1/voices` lists the account's voices; `GET /v1/shared-voices?language=es` finds native voices in other languages — the account's own list is often English-only, and shared-library voice ids work directly in TTS.

## Order of work

**Audio first, always.** Durations come from the audio that exists; the picture is then cut to them. The other way round, the picture has time to fill, and whatever fills it wasn't in the script. (The same seven words at the same speed came back 3.02 s, 3.30 s and 3.35 s on three takes — you can't plan the grid before the audio exists.)

1. `scripts/gen_voice.py lines.json audio/lines --gate` — one file per line, trimmed, levelled, transcribed and compared with the script
2. `scripts/gen_sfx.py sounds.json sfx/lib` — a sound library, built once, reused across projects (starter prompts inside the script)
3. `scripts/mix.py timeline.json audio/track.wav [--duck fg bg]` — lay lines and effects on a timeline, mix, duck
4. `build.py` in the project — emit the composition(s) from the measured timings
5. `npx hyperframes check` — fix everything it reports before rendering
6. `npx hyperframes render`

```bash
S=${CLAUDE_SKILL_DIR}/scripts
python3 $S/gen_voice.py lines.json audio/lines --gate
python3 $S/mix.py timeline.json audio/track.wav
```

Read `references/hyperframes-gotchas.md` **before** writing composition HTML. Every item in it cost a wasted render to find.

## Scaffold

`references/scaffold.md` has the project skeleton: `hyperframes.json`, `package.json` (pinned CLI), the `build.py` pattern that emits several aspect ratios from one source, the stylesheet head, and a snippet that trims logo PNGs to their visible pixels. Copy it rather than starting from nothing.

Keep brand assets outside the skill and reference them: logo lockups (white / dark / colour), icon, brand tokens (colours, fonts) as a CSS file, your sound library. Logo exports often sit on large transparent canvases — trim them to the alpha box before layout, or the spacing is wrong.

## Rules that decide the result

**Text colour follows the ground, never the reverse.** A card that changes background mid-piece must change its ink with it. Dark ink centred on a blue-to-white gradient measures 1.6:1 where the composition happens to sit.

**`hyperframes check` measures text, not images.** It will pass a logo that is invisible on its background. Look at a rendered frame — or the contact sheet `ads-video-library` makes.

**`vmin` is identical in 1920×1080 and 1080×1920** — both are 1080 on the short side — so type sized in vmin is physically the same in either aspect. That's the point, but a card sized to fill a portrait frame looks lost in a landscape one. Scale the whole stack on a wrapper; never re-specify every size.

**Sound only where something visibly happens.** A click over a static frame reads as a mistake. Interface sounds need "dry, no reverb" in the prompt — a tail smears across a short beat. Nothing with a tail goes over a voice; events that are meant to be heard wait for a beat where nobody is talking.

**Ducking, not level.** When one voice must sit under another (or music under a voice), sidechain-compress the background keyed by the foreground: `mix.py --duck fg bg`. Setting it quieter leaves them competing; the duck is what makes one the voice and the other the room.

**Level every line before mixing.** Voices from different sources arrive at different loudness, so a dB offset between buses doesn't mean what it says. `gen_voice.py` normalises each line, which makes the offsets literal.

**Transcribe and compare.** Generated speech gets checked against the ordered text before it ships: `gen_voice.py --gate`. Digits, currency symbols and sentence-break spacing are normalised first, or the gate cries wolf and gets switched off — which is worse than not having one.

**Judge by watching, confirm with a metric** — never the other way round. Motion needs a cause on screen (a click, a response, a camera following); decorative twitching to hit a "motion density" number reads as generated.

## After rendering

Name, store and review the batch with the `ads-video-library` skill: canonical names, posters baked into frame 0, contact sheets, and a review page.

## Adapt it

- Put your brand tokens (colours, fonts, logo paths) into one CSS file and reference it from every project.
- Build your sound library once (`gen_sfx.py`) and reuse it; keep its BPM grid consistent with the music beds you buy.
- Save one finished card as your reference project — the next card starts as a copy of it.
