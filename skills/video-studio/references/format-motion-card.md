# Format: motion card

Short branded pieces assembled from code: HTML + CSS + one paused GSAP timeline,
rendered by HyperFrames, audio from ElevenLabs and the sound library. Deterministic and free
to re-render; nothing is spent per attempt except the audio, so iterate freely. End cards,
title cards, offer/CTA cards, product-UI panels with animated text, logo stings, lower
thirds - anything where the text must be exactly right. Not for generated footage of people,
rooms or objects: that is the **video-generated** skill.

**Coming from the `motion-card` skill (v1)?** This recipe replaces it. Its scripts moved to
video-sound (`gen_voice.py`, `gen_sfx.py`, `mix.py`) and its references to video-build
(`scaffold.md`, `hyperframes-gotchas.md`); `gen_voice.py --gate` still works, and `mix.py`
reads the same timeline format.

## Needs

- Node.js 22+, FFmpeg, HyperFrames (`npx hyperframes doctor`) - the kit's
  `connections/hyperframes-cli.md`.
- `ELEVENLABS_API_KEY` in `~/.config/marketing-agent-kit/.env` - `connections/elevenlabs-api.md`.
  A paid plan is needed for generated sound effects.
- The sound library: `python3 ../video-sound/scripts/library.py install`.
- For the speech check (`--gate`, `--must`): a Whisper CLI - `pipx install mlx-whisper` (Apple
  Silicon) or `pipx install openai-whisper`.

## Order of work

**Audio first, always.** Durations come from the audio that exists; the picture is then cut to
them. The other way round, the picture has time to fill, and whatever fills it was not in the
script. (The same seven words at the same speed came back 3.02 s, 3.30 s and 3.35 s on three
takes.)

1. `python3 ../video-sound/scripts/gen_voice.py lines-src.json audio/lines --must "YourBrand"` -
   one file per line, trimmed, static-levelled, transcript gate + names heard verbatim. It
   writes its results to `audio/lines.json` (next to the output folder), so never call the
   script file `lines.json` in that same folder - it gets overwritten. A flagged line: delete
   its .mp3/.wav/.txt and run again; a fresh take usually fixes a mispronounced name.
2. Sound effects: pick from the library catalogue; `../video-sound/scripts/gen_sfx.py` only for a
   sound the library lacks (generate it once, keep it, reuse it).
3. `python3 ../video-sound/scripts/mix.py timeline.json audio/track.wav --duck fg bg` - voice on
   `fg`, bed on `bg`.
4. `build.py` in the project emits the composition(s) from the measured timings.
5. `npx hyperframes check` - fix everything it reports.
6. `npx hyperframes render` (master at `--crf 10`, see video-check `references/qa.md`), then the
   gates and the independent review (video-check).

Read video-build's `references/hyperframes-gotchas.md` before writing composition HTML - every
item in it cost a wasted render to find. Its `references/scaffold.md` has the project skeleton
(`hyperframes.json`, the pinned CLI in `package.json`, the `build.py` pattern that emits several
aspect ratios from one source, the stylesheet head, a snippet that trims logo PNGs to their
visible pixels). Copy it rather than starting from nothing; once one card is finished, copy that.

Voice, effects and the bed in depth: the **video-sound** skill (ElevenLabs models, voices, keys).

## Brand assets

Keep them outside the skill and reference them from every project: logo lockups (white, dark,
colour), the icon, trust badges, brand tokens (colours, fonts) as one CSS file. Logo exports
often sit on large transparent canvases (512×512 with wide margins is common) - trim them to the
alpha box before layout, or the spacing is wrong (snippet in video-build `scaffold.md`). Keep one
trimmed, right-sized wordmark per ground (white on dark, dark on light) for the end card.

## Rules that decide the result

- **Text colour follows the ground, never the reverse.** A card that changes background
  mid-piece must change its ink with it. Dark ink centred on a blue-to-white gradient measured
  1.6:1 where the composition happened to sit.
- **`hyperframes check` measures text, not images.** It passes a logo that is invisible on its
  background. Look at a rendered frame - or the contact sheet video-check (`stills.py`) or the
  `ads-video-library` skill makes.
- **`vmin` is identical in 1920×1080 and 1080×1920** (both are 1080 on the short side), so type
  sized in vmin is physically the same in either aspect. A card sized to fill a portrait frame
  looks lost in a landscape one: scale the whole stack on a wrapper; never re-specify every size.
- **Grid**: percussive effects sit on the bed's own beats - read them from the track's `cues/`
  file in the library. A 120 BPM bed has a bar of exactly 2.0 s; a bed at another tempo moves the
  grid with it. An effect between the bed's hits reads as slop.
- **Nothing with a tail over a voice**; the only audio under speech is texture ≤ -24 dB. Events
  meant to be heard wait for a beat where nobody is talking.
- **Sound only where something visibly happens.** A click over a static frame reads as a mistake.
- **Duck per spoken passage, not per word.** The bed dips under each passage (`mix.py --duck`);
  a level offset alone leaves voice and bed competing, and a compressor keyed by the voice pumps
  between words.
- **Level every line before mixing.** Voices from different takes arrive at different loudness,
  so a dB offset between buses means nothing until each line is levelled (gen_voice.py does it).
- **Transcribe and compare.** Generated speech is checked against the script before it ships
  (`--gate`). Digits, currency symbols and sentence-break spacing are normalised first, or the
  gate cries wolf and gets switched off - which is worse than not having one.
- **Judge by watching, confirm with a metric** - never the other way round. Motion needs a cause
  on screen; decorative twitching to hit a "motion density" number reads as generated.

## After rendering

Name, store and review the batch with the `ads-video-library` skill: canonical names, posters
baked into frame 0, contact sheets, a review page.

## Make it yours

- Put your brand tokens (colours, fonts, logo paths) into one CSS file and reference it from
  every card.
- Generate the few sounds your library lacks once (`gen_sfx.py`) and reuse them; keep their
  grid consistent with the beds you use.
- Save one finished card as your reference project - the next card starts as a copy of it.
