# Captions: word-highlight captions in any language and direction

`scripts/captions.mjs` turns a film's voice lines and their word timings into caption cues and a
ready HyperFrames block. Ported from nanoclip-cutting-room `scripts/captions.mjs` (MIT) and fitted
to video-studio's laws. Proven on a test film (2026-10-14): six lines, English and Arabic
alternating, Latin names inside Arabic lines, rendered with hyperframes 0.8.157.

## Command

```bash
node ${CLAUDE_SKILL_DIR}/scripts/captions.mjs film.json --band 0.72 --size 62 \
  --font "Inter=assets/fonts/Inter-600-latin.woff2" \
  --font "Noto Sans Arabic=assets/fonts/NotoSansArabic-600-arabic.woff2"
# -> captions.cues.json (the timing truth) + captions.html (the block); exit 1 = some cue is unreadable
node --test ${CLAUDE_SKILL_DIR}/scripts/captions.test.mjs     # after editing the script
```

`film.json`, paths relative to it (`build.py` writes it from the same timing it uses for the picture):

```json
{ "duration": 18.81,
  "lines": [
    { "tag": "en1", "at": 0.50, "words": "audio/lines/en1.words.json", "voice": "cjVig..." },
    { "tag": "ar1", "at": 2.91, "words": "audio/lines/ar1.words.json" },
    { "tag": "talk", "at": 9.0, "whisper": "audio/talk.json", "in": 3.2, "out": 11.0 } ] }
```

- `words`: video-sound `gen_voice.py --align` (or `--words`) output, on the take's own clock; `at` is
  where the take starts in the film. An inline `[{w, s, e}]` array also works.
- `whisper`: `mlx_whisper --word-timestamps True` JSON for recorded speech; `in`/`out` pick the
  source window that lands at `at`. For TTS lines prefer `--align` (see Timing below).
- `speaker` (default: `voice`, then the tag), `dir` and `lang` override what is detected.
- Flags: `--max-words 4` (soft cap), `--band 0.70` (centre of the band, fraction of height),
  `--size 56` (px), `--ahead 0.55` (opacity of words not yet said; `0` = words appear as spoken,
  `1` = whole cue solid), `--no-highlight`, `--fps 30`, `--id captions`, `--font "Family=path"`.

Paste `captions.html` inside the composition root and call `mountCaptions(tl)` in the timeline
script before `window.__timelines[...] = tl`. Colours come from the film being edited, never a brand
default: override `--cap-ink`, `--cap-scrim`, `--cap-hi`, `--cap-hi-ink`, `--cap-font`, `--cap-y`,
`--cap-pill`, `--cap-pill-rtl` in a rule AFTER the block or as `#root #captions {...}` (an earlier
rule of the same weight loses - the first test film's size override did).

## What it does

**Cue breaks.** Always at a speaker change, at >= 0.8 s of dead air and at a seam (a new voice
line, a new footage window). Inside a run the split points are chosen, not cut every 4 words: each
possible cue is scored, a cue that readcheck would fail costs 100, words over `--max-words` cost 3
each, a split away from punctuation 1, a one-word cue 2. So slow speech with pauses gets 3-4 word
cues ending on punctuation, and fast TTS speech gets longer cues. Why: our TTS runs at 3.5-4.5
words/s (en1: 8 words in 1.8 s); a fixed 4-word cut leaves the first half on screen ~0.9 s and
fails "Readable" (tail >= 0.6 s after the last word, >= 1.8 s in all). With 0.5 s pauses even a
3-word cue at 0.45 s/word reaches only 1.78 s and is merged.

**Readability is computed the way video-check `readcheck.mjs` measures it.** Words ahead are
ghosted (`--ahead 0.55`), so readcheck sees the cue revealed with the voice and applies the
subtitle rule; the builder predicts each cue's tail and prints it (`ok`/`SHORT` with got/need). On
the test film the predictions matched readcheck within one 0.05 s step in all three modes. A whole
cue solid from its first frame (`--ahead 1`) is judged as a static line (0.3 s per word) and failed
3 of 9 cues at TTS speed - that is why ghosting is the default. A `SHORT` that remains means the
next voice starts too soon: widen the gap in the edit or cut words.

**Timing of a cue.** It holds >= 0.5 s after its last word and until it is readable, never ends
before its last word, never runs into the next cue or past the film. Two cues closer than 0.5 s are
chained with exactly 2 empty frames between them (subtitle practice: the blink tells the eye the
text changed; nanoclip's 0.05 s yield is the same idea), and the chained cue pops in. A cue after
silence fades in during the 0.12 s BEFORE its first word, so that word lights up at full strength
(fading from the first word made the first pill 2 frames late).

**Highlight.** The said word goes solid and gets the pill on the frame nearest its start (every
time is rounded to a frame in `mountCaptions`); the pill runs on to the next word across gaps
< 0.25 s (no flicker between words) and lasts >= 0.08 s. Words already said stay solid.

**Band.** Centre at `--band` (default 70% of the height; laws: never in the face zone - check the
footage), cues stacked in one grid cell, each `data-read` (readcheck folds a grid item of <= 3 words
into the whole band otherwise) and `data-layout-allow-overlap`.

## Right-to-left and mixed scripts

- **Direction per line, by the script most of its letters are in.** An Arabic line with "Google
  Maps" is `rtl`; an English line with one Arabic name stays `ltr` (nanoclip's "any RTL run makes
  the cue RTL" would flip it). Every cue of the line gets `dir`.
- **Word spans stay `display: inline`.** Inline spans share the cue's bidi paragraph, so a Latin
  name sits where it belongs. With `inline-block` each word becomes a neutral box and a run of them
  reverses: the test cue rendered "Maps Google". So
  no transforms on words (they need inline-block) - colour, background and opacity only.
- **The pill covers the word without its punctuation.** In an RTL line the final "." of "Maps."
  belongs at the far left; a pill over the whole span split into a stray second pill there. The
  punctuation gets its own span (and no pill padding on that side, or "nine ," detaches).
- **Fonts.** Ship a face that covers the script as a local `@font-face` (`--font`; lint wants a
  local file for every named family). Latin face FIRST in the stack: the pill is as tall as the
  first face's box. With Inter first the dots under Arabic letters (ي, ب) reach ~0.42 em below the
  baseline, past Inter's 0.24 em, and were painted dark on dark outside the pill - RTL pills
  therefore pad the bottom (`--cap-pill-rtl: 0 0.1em 0.24em`). Noto Sans Arabic first is no fix: its
  line metrics made every pill 2.15 em tall, sticking out of the scrim. New fonts: look at a still -
  dots inside the pill, pill inside the scrim.
- No `letter-spacing` on RTL cues (breaks the joins); line height 1.6 for Arabic.
- Hebrew: `eleven_multilingual_v2` has no Hebrew; `eleven_v3` with `--align` works (probed on the test film).

## Timing source

One input whatever the language: `<tag>.words.json` from video-sound `gen_voice.py`.
- **`--align` for every new take** (any language; required for Arabic, Hebrew, CJK): ElevenLabs'
  own character alignment, script words exactly. On 7 Arabic takes (53 words) its word starts
  landed 43 ms before the end of each of the 6 comma pauses (worst 54 ms); whisper turbo started
  the next word 250 ms early (worst 360 ms, all 6 off by > 100 ms) and matched only 45 of 53 words to
  the script (it writes "Google Maps" as "جوجل مابس"); parakeet wrote Arabic as Latin gibberish (4/53).
- `--words` without `--align`: parakeet, for old European takes only (gen_voice refuses other scripts).
- Recorded speech: whisper JSON. Expect words after a pause to light up ~0.25 s early.

## Checks for a captioned film

1. `npx hyperframes check` (contrast is measured per word span; the ghosted words passed at 0.55).
2. `node ../video-check/scripts/readcheck.mjs <project>` - every cue OK. (It counts a word's
   punctuation as a word because the punctuation has its own span; the builder counts the same way.)
3. Stills at every word start and every cue change, cropped to the band: order of words (RTL from
   the right, Latin names in place, final punctuation at the left end), joined Arabic letters, dots
   inside the pill, nothing outside the scrim. Sample a frame AFTER a time, not before: the frame
   at `end - 0.04` can already be past a rounded end.
4. Highlight against the sound on the render: find the pill in every frame (its colour in the
   caption band) and the speech onsets in the film's own audio, and compare the two. Test film: 42 of 43 switches
   on the expected frame (the other a 0.5-frame rounding tie), the word lit 3-30 ms before its onset
   at all 7 onsets, chained cues exactly 2 frames apart.
