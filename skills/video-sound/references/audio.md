# Audio

Library: `$VIDEO_LIBRARY` (default `~/.local/share/marketing-agent-kit/video-library`; installed by
`scripts/library.py install`, checked by `library.py doctor`).
- `catalog/CATALOG.md` - what there is; `catalog/music.json`, `catalog/sfx.json` - fields. Every
  `path` is relative to the library root; in a mix timeline write `"$VIDEO_LIBRARY/<path>"`.
- `LICENSES.md` - where every file came from and whether it may go in an ad.
- `README.md` - how to add a track or a sound (licence row first, then analyse, then rebuild the catalogue).
- Entries with `"external": true` are not in the package (their licence forbids redistribution):
  use one only when its file exists at its `path`.

The library venv for the analysis scripts: `$VIDEO_LIBRARY/tools/.venv/bin/python` (below: `$PY`).

## Voice

`scripts/gen_voice.py lines.json out_dir --must Acme[,Zoom,...]`
- one file per line; durations become the picture's grid (audio first);
- each line trimmed and given ONE static gain to -18 LUFS (no gain riding inside a line);
- `--gate` transcribes (Whisper large-v3-turbo: `mlx_whisper` on Apple Silicon, else
  `openai-whisper`) and diffs against the script; `--must` additionally requires each listed name
  to be heard - the whole-line gate passed a take that swapped one consonant of the brand name.
  Spelling variants count ("Acme II" = Acme2: no recogniser writes "Acme2"); a different
  sound does not. A flagged name that opens the take: regenerate once before anyone listens.
  Never add `--initial-prompt` with the names - it writes the name over a bad take and deletes
  prompted words (a speech-recognition bench on our takes, 2026-10-14);
- the gate reads every script (until 2026-10-14 it kept Latin letters only, so an Arabic line was
  compared as "" with "" and always passed). Arabic vowel marks, tatweel and the hamza / ta marbuta /
  alef maqsura spellings are folded. Whisper writes a Latin name inside an Arabic or Hebrew line in
  that line's letters ("Google Maps" → "جوجل مابس", "Wi-Fi" → "واي فاي"): such a run counts as
  heard and is printed `check by ear` - no recogniser can confirm it, so listen to those names. On
  the bench's 106 European takes the gate's verdicts did not change;
- every line gets 8 ms / 30 ms fades at its edges: a take that ends mid-waveform clicks where
  the next line starts (a product promo, 2026-10-08: heard at 33 s);
- word timings for captions and word reveals, `<tag>.words.json` = the script's words (its
  spelling) on measured times - the input of video-build `../video-build/scripts/captions.mjs`:
  - **`--align` for every new take, any language** (implies `--words`): the take comes from
    `/with-timestamps` as pcm (kept as `<tag>.src.wav` + `<tag>.align.json`, so the alignment's
    clock is the file's clock) and the words take ElevenLabs' own times, shifted by the head trim.
    Same price as a plain take. On 7 Arabic takes it put the word after each of 6 comma pauses
    43 ms before the pause ended (worst 54 ms); whisper turbo started that word 250 ms early
    (worst 360) and matched 45 of 53 words to the script; parakeet wrote Arabic as Latin
    gibberish, 4 of 53 words matched (a captions test, 2026-10-14). Old takes (an mp3 without
    alignment) are never re-requested: delete or move the take to re-cut it with alignment. A
    tempo change after the take (Rubber Band) invalidates the times - rebuild the words.
  - `--words` alone: parakeet-mlx (Apple Silicon only; elsewhere use `--align`), for takes without
    alignment in its 25 European languages (Latin, Greek, Cyrillic script; gen_voice skips other
    scripts and says so). Parakeet put 88% of word starts within 100 ms of ElevenLabs' alignment
    (Whisper turbo 69%) and splits words at pauses; Whisper turbo stretches a word ~320 ms into the
    pause. On the same bench turbo had the lowest word error (EN 1.0%, ES 0.0%) and caught both
    known-bad takes - that is why the gate is turbo and the timings are parakeet. Parakeet's times
    sit on an 80 ms grid (2-2.4 frames). It is for single-language takes only - in a mixed film it
    silently dropped a 7 s Spanish passage.
  - Hebrew: `eleven_multilingual_v2` has no Hebrew; `--model eleven_v3 --align` works.
- `mlx_whisper` always with `--model mlx-community/whisper-large-v3-turbo` (without it the CLI
  runs whisper-tiny: 13.5% Spanish error, 37/59 names) and one file per call (0.4.3 writes every
  result of a multi-file call under the first file's name). `openai-whisper`: `--model turbo`.

Model choice (2026-10-08, a product promo): `eleven_v3` at `--stability 0.0` with
emotion tags ([excited], [playfully], ...) was rejected as overacted and breathy - the tags
shift the timbre. `eleven_v3 --stability 0.5` with no tags kept the energy and the voice. v3 ignores
`speed` and runs ~20% slower than v2: speed it up after the take with Rubber Band
(`rubberband -3 -F -T 1.12`, formants kept), then level and gate again.

### ElevenLabs

Key `ELEVENLABS_API_KEY` (environment, else `~/.config/marketing-agent-kit/.env`; setup in
`connections/elevenlabs-api.md`). A line costs cents: regenerate a bad one, don't patch it.
Sound generation (`gen_sfx.py`) is blocked on the free tier.
`eleven_multilingual_v2` for anything non-English; `eleven_v3` for expressive English
short lines. `GET /v1/voices` lists the account's voices (English); non-English lines
need a shared-library voice (`GET /v1/shared-voices?language=es`), usable directly.
**Eleven Music is gated** (403 until the account accepts separate terms) - use a library
bed or ask.

## Music

Pick by role and tempo from the catalogue. `ads: false` tracks (the scratch synth beds in
`music/own/`) never ship in a finished film; `"external": true` tracks only once their file is in place.
The Ende tracks are CC BY 4.0: put "Music by Sascha Ende (ende.app)" in the film's credits or
description - the author says it is no longer required, and it costs nothing.
- Every track has `cues/<stem>.music-cues.md`: beat grid and strongest cues in the first
  25 s, plus full-track JSON. Use policy: a major reveal may move to a strong cue within
  ~0.15 s, a small entrance to a beat within ~0.10 s; story, voice sync and reading time win.
- A track not in the library: `$PY $VIDEO_LIBRARY/tools/analyze_music_cues.py <file> --output-json ... --output-md ...`
  (reproduces the shipped latent-spaces/brag presets exactly), then `music_key.py <file> --write`.
  Inside a HyperFrames project `npx hyperframes beats` is the quick fallback (grid only).
- Fitting a track to a grid: `python3 $VIDEO_LIBRARY/tools/prep_bed.py src out.wav --from <s> --secs 18
  --from-bpm <its tempo> [--bpm 120]` - atempo stretch (under ~10% is inaudible), cut a window,
  0.35 s fade in, 0.9 s fade out, -24 LUFS. A bed on the film's grid keeps effects placed on the
  grid on the bed's own hits.
- No music yet: `$PY $VIDEO_LIBRARY/tools/synth_bed.py out.wav --bpm 110 --mood calm` makes a scratch
  bed from sine and noise at the exact tempo, to time a card before the real track is in.

Cut the film to the music, not the music under the film (a product promo, 2026-10-08: two
beat-heavy beds laid under a voice-timed cut were heard as "out of step, like a rap clip"; the
softer Ende bed sounded best but "boring"). What worked: the bed spliced from the track's own bars,
never stretched - a quiet stretch under the hook, the section that drops on the product's name (on a
bar), a breakdown under the calm middle, and the track's real ending, so its last hit lands on the
end card's name and rings out. Every splice sits on a bar of the same tempo, so the film keeps one
uniform grid (beat k at drop + k x period) and every scene cut snaps to it (line starts moved by
<=0.25 s).

Section maps of the Ende tracks (by ear and cue file, for that splice):
- vol. 1 (120 BPM): intro to 16 s, full 16-32, breakdown 32-48, full from 48; its last hit at
  158 s rings out to the end of the file.
- vol. 9 (114.84 BPM): build to 20 s, full 20-50, breakdown 50-66, full 68-100, then the outro;
  its last full bar lands at 100 s.
- vol. 12 (110 BPM): a quiet intro, a build that comes in at 9 s, full from 17 s; at 105 s the
  full band drops to the outro. Avoid syncopated / glitch beats for a narrated film: check the
cue file - if many detected beats sit off a straight grid, the cut cannot land on them.

**The catalogue's BPM is estimated on the first 25 s - measure the grid on the whole track before
anything beat-locked runs longer than that.** ende vol. 1: catalogue 120.19, a linear fit of
`librosa.beat.beat_track` beats over 5-155 s gives 120.005 (period 0.49998 s, first beat 0.040 s);
"correcting" to 120 from the catalogue figure drifted a picture's 0.5 s grid by 0.24 s over 160 s,
the fitted grid stays within 6 ms (a looping demo slide, 2026-10-14).

**A seamless music loop** (the same demo slide): rank N-bar windows that start on a downbeat by
energy and by how much the music right after the window resembles its start (chroma + mel
features, 1 s on each side, compared); cut the window on the measured
grid (16 beats = the loop, no stretch); crossfade its first 0.12 s (equal power) with the music that
FOLLOWS the window, so the last sample runs into the first; master three copies in a row through
`mix.py` and keep the middle one - the limiter is warm and identical at both seams. Measured: the
sample step at the seam 0.024 vs a median 0.015. For a slide that loops for minutes, also ship a long
version (the loop picture repeated under the whole track) so the music does not repeat every 8 s.

## Sound effects

- First choice: `catalog/sfx.json`. Filter by `family`, `tags`, `suggestedUses`,
  `highFrequencyRisk`. Kenney pick-by-use lists: `catalog/kenney-sfx-analysis.md`.
- **Repeated sounds must be `highFrequencyRisk: medium`.** Seven of the eleven ElevenLabs
  sounds (`el-*`) measure high (every `ui_*`, `typing`, `translate`, `shimmer`) - fine once, tiring
  in a run. For repeated clicks use the soft Kenney clicks (`k-click_002/003/005`, `k-click2`).
- Typing is the one exception: the 32 keypresses in `sfx/keyboard/` all measure high, but
  each lasts milliseconds. Random file per character at about -21 dB, thinned on dense copy
  (a product demo: 25 characters, every other space skipped).
- Find by type and look before choosing: `$PY scripts/sfxlib.py browse --type riser --sheet s.png`;
  `--ads` drops the three speech-suspect Freesound items.
- Nothing in the bank fits: `scripts/gen_sfx.py` (ElevenLabs; generate dry - the mix adds the shared room),
  then put the files in a source folder of their own, run `$PY $VIDEO_LIBRARY/tools/analyze_sfx.py` on
  them and rebuild the catalogue (the library's README.md).
- Placement: at the START of the visible action (entry pop 0-0.1 s before first frame);
  success sound when the thing is fully visible; in a stagger, score the first, last or
  strongest item only. Never on a first syllable; nothing with a tail under speech.

Check after mixing: `$PY scripts/sfxcheck.py timeline.json` says for every effect whether it is
heard (in a pause over the bed, or cutting through speech) or masked, and flags a sound on a
first syllable or a tail under speech. Mark wanted texture `"role": "texture"` in its event.

## To try (borrowed, not yet proven here)

From lemo-opuscar's directing notes (MIT). Try them on the next film; whatever survives
the user's review moves to video-studio laws.md, whatever is rejected goes there as a rule against it.
- **One real silence before the peak.** Drop the bed (and effects) to near-silence for
  0.5-1 s right before the key claim or the reveal; the first sound after it should be one
  of the most important in the film (the product's name, the output voice).
- **Sound as a transition** (J-cut / L-cut): tested in video-moves (moves 23, 24 - lead 0.3-0.5 s
  from the first audible word, tail 0.3-1.5 s with a fade); still to be proven in a real film.
- **Three layers**: ambience (room tone, a call's line noise), foley tied to actions, music.
  Our films mostly have only the last two.

## Levelling and pitching effects (sfxauto.py)

Effects that matter get `"gain": "auto"` instead of a guessed dB, and the timeline goes through
`$PY scripts/sfxauto.py` before mix.py. It renders the bed (music ducked per passage + any
`stop_before`, plus the voice) and lifts each effect over it in the band where it is easiest to
hear (3.5 dB; `"hero": true` 5 dB in its main band), with caps on the 2-8 kHz lift and on the
peak; a group of the same sound stays within ±2 dB of its median; clicks closer than 0.15 s are
taken down. An effect that lands inside a voice passage is set to texture (-24 dB under the bed)
and reported - move it to a gap if it must be heard (laws.md, Sound). Tonal effects (chime,
shimmer, pop, ui...) can take `"pitch": "auto"`: moved at most ±3 semitones onto the tonic or
fifth of the music's key (or another scale tone); the key comes from `catalog/music.json`
(`tools/music_key.py`; confidence under 0.05 = ambiguous, pitch left alone).

Before the hero hit: `"stop_before": true` gives the hit one real silence (music -24 dB for 0.4 s);
`"build": true` thins the music into it (2 s crossfade into a 300 Hz high-pass). Use one of them
per film, on the one moment that carries it.

## Mix

`scripts/mix.py timeline.json out.wav --duck fg bg [--depth 7] [--merge 1.0] [--tp-ceiling -2]`
- an effect that belongs to a picture event is placed by `"cue"` + `"align": "peak"` (its
  loudest 2 ms on the frame), not by guessing an `"at"` - a hit whose file starts with 11 ms
  of attack lands 11 ms late otherwise (measured 2026-10-14);
- stereo by default (`--mono` exists for old cards only);
- the `bg` bus (music) dips `--depth` dB per spoken PASSAGE: voice events closer than
  `--merge` s form one passage; the dip starts 0.3 s before the first word and recovers
  0.5 s after the last. A compressor keyed on the voice pumped ~11 dB between words and
  was heard as "louder, quieter, louder" - that is why it is gone;
- master = one static gain to `loudness`, then a 4x-oversampled peak-only limiter at the
  true-peak ceiling (-2 dBTP), the gain re-solved until the file is within 0.3 LU of the
  target (2026-10-14; the old sample-peak limiter left -0.3 dBTP and AAC pushed a -2.1 WAV
  to -0.5 - the new one measured -1.9 dBTP after AAC);
- a shared room on the effects bus (`--room on`, default; `--room-db -16`), switched off under
  every voice passage - picked in a blind A/B (laws.md, Sound). Effects are laid in
  dry; the room comes from the mix, so every effect sits in the same space;

Targets: **-14 LUFS, true peak ≤ -1 dBTP** for anything going to YouTube / LinkedIn /
ads (platforms normalise there). The ElevenLabs reference film sat near -11 LUFS
hard-limited - louder only when a piece must compete without normalisation.
`hyperframes render` does no mastering; the track it embeds is the one mix.py made.
