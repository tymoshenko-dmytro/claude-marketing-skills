# Backlog: shorts cut from long footage

Not a format yet (a format is added when a second film of its kind is made). This note says
what to use the day a long recording arrives - a webinar, a customer call (with consent),
a talk, an interview recording, a podcast. Written 2026-10-14.

## The method

nanoclip-cutting-room's editorial playbook (github.com/latent-spaces/nanoclip-cutting-room,
MIT; ideas restated here):
- **Three tests a clip must pass**: it opens ON the hook (the first ~8 words work as an
  overlay); setup, turn and payoff are all inside the clip and every pronoun resolves inside it;
  a stranger understands it alone.
- **Disqualifiers**: ad reads, housekeeping ("can you hear me"), clips under 12 s or over 90 s.
- **Where a clip may cut**: only in a gap between words, at most 1.5 s from the chosen word,
  snapped to a picture cut.
- **Score**: hook 0.35, arc 0.25, standalone 0.15, energy 0.15, visual variety 0.10; propose at
  ≥ 0.60; pick a diverse batch, not five clips of one idea. (The weights are not calibrated -
  calibrate them on your first batch against the user's picks.)
- Long footage is scouted in shards in parallel (each short is its own film, so parallel
  workers are fine), frames taken from silences ≥ 5 s where the transcript cannot see.

## Tools, in the order to reach for them

| Job | Tool | Notes |
|---|---|---|
| Get the recording (a link) | `yt-dlp` (`--download-sections "*12:30-14:10"` for a piece) | `brew install yt-dlp` / `pipx install yt-dlp` |
| Watch it whole, with sound, and ask where the moments are | `/watch` plugin, Gemini engine (setup in video-check; the free key serves Flash only) | optional |
| Transcript with word timings | mlx-whisper turbo for text (no-condition + `--language`); parakeet-mlx for word times on single-language audio - it dropped a minority-language passage in a mixed-language film | video-sound and video-check use the same tools |
| Who speaks when (two or more people) | pyannote-audio (MIT; models gated on Hugging Face - needs an HF token and accepting the terms) or mlx-audio | install when needed |
| First pass: cut dead air | `auto-editor` (Unlicense; `--edit audio:threshold`, `--margin 0.2s`) | `pipx install auto-editor` when needed |
| Reframe talking footage to 9:16 or 1:1 | nanoclip's reframe law: a static crop per shot from the speaker's median face box, changing only at cuts; split screen for two speakers | rule known, no tool yet |
| Real footage inside HyperFrames | video-build `references/hyperframes-gotchas.md` "Real footage" + `scripts/footage_proxy.py` (measured on 0.8.157) | ready |
| Captions | video-build `scripts/captions.mjs` + `references/captions.md` (any language, RTL; timings from gen_voice `--words`/`--align`, or whisper for recorded speech) | ready |
| Glitches at cuts | video-check `scripts/seamscan.py` (gate 10) | ready |

## When it happens

1. Ask the user: which recording, who appears in it (consent), what channel and aspect
   (9:16 / 1:1 / 16:9), how many clips.
2. Transcribe, `/watch` the whole thing with the three tests as the question, score, propose a
   batch with timestamps and the hook line of each.
3. Build the picked clips as separate films (video-build), captions, sound (video-sound), gates
   (video-check). Private data: list it (laws.md) before showing.
4. After the second batch, turn this note into `format-shorts.md` and a row in `formats.md`.
