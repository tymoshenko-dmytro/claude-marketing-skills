# Gates

Run in this order before anyone sees the video. Each line exists because a cut shipped
without it once - or, for lines marked (borrowed), because another studio's did.

0. **Private data listed** (laws.md "Say what private data is on screen"): grep the composition,
   its assets' text and the transcript for emails, phone numbers, `sk-`/`AIza`/token-like strings,
   internal hostnames and personal names; look at every UI screenshot for the same. Report what is
   there and the decision recorded in the plan - a finding is a question for the user, not an
   automatic swap.
1. **Grounding read.** Read every on-screen line and every spoken line once with one
   question: does the product (its files, UI, output, the product brief) say this? Names, numbers,
   features, quotes must be found; tone and jokes may be invented. `check` has no opinion
   on copy - "Ships 10x faster" passes it clean. Repeat per language version.
   The same for material shown as somebody's (a rival's ads, a customer's page): it comes from the
   sources behind the numbers next to it.
2. **Voice gate.** `gen_voice.py --must <names>` passed: every line transcribed, every
   name heard verbatim.
3. **`npx hyperframes check`** - lint, runtime, layout, contrast. Fix errors; contrast
   warnings on the product's own pale UI text are expected (show the UI as it is), but
   the product's NAME must read (≥4.5:1).
4. **Reading time** - `node scripts/readcheck.mjs <project>` (borrowed: lemo-opuscar). Steps
   through the composition and measures how long every line stays fully on screen against
   the "Readable" law (0.3 s per word, from when the whole line is in). Captions revealed
   word by word with the voice are judged as subtitles instead: ≥ 0.6 s after the last word,
   ≥ 1.8 s in all. When to switch to `--norm strict` (about twice as long): see video-studio/references/laws.md,
   "Readable". It also lists text that is never fully in frame (cut by an edge). Skips
   text under 24 px (UI chrome); live UI text it flags (a transcript streaming in a panel)
   is read by judgement - mark it `data-noread` if it is not meant to be read. Takes seconds;
   on a 32 s launch film: 3 short lines found, all three confirmed on rendered frames.
   **Typed text** (a line typed character by character) shows one SHORT row per frame of typing.
   Judge only the final string: drop every row whose text is a prefix of a longer row (on a 66 s
   world film, 141 of 198 rows were typing frames).
5. **Stills, including mid-transitions** - `scripts/stills.py <project> t1 t2 ...`. Look
   for: an element visible before its entrance (a `fromTo` with `immediateRender:false`
   shows its natural state until it starts - hide it in CSS), two motions at once, a
   double exposure, a frozen tail, text cut by an edge.
   **Phone width** (borrowed: video-talkcraft): `scripts/stills.py <project> --every 1.5
   --width 390 --cols 2 --out phone.jpg` and read every line at that size - a 16:9 film in a
   phone feed is about 390 px wide. A line that does not read there: cut words first, then
   enlarge; never leave a single word on its own line.
6. **1:1 zoom on every image and small detail** - `npx hyperframes snapshot --zoom
   "<selector>"`. A thumbnail sheet does not show a squashed image (an `<img>` with
   width/height attributes under `width:100%` needs `height:auto`).
7. **Render** the master near-lossless: `hyperframes render -q high --crf 10`; encode
   the deliverable ONCE from it (`libx264 -crf 14 -preset slow`, `-tune stillimage` for UI).
   `-q high` alone is ~3.8 Mbit/s and smears small UI text, and a second encode on top
   doubles the loss.
8. **Sound check on the file**: integrated loudness and true peak
   (`ffmpeg -i out.mp4 -af ebur128=peak=true -f null -`), and the short-term curve every
   0.5 s - under speech it should sit within ~2 LU; a sawtooth means something is riding gain.
   **Effects heard?** `$PY ../video-sound/scripts/sfxcheck.py timeline.json` (borrowed: video-talkcraft) -
   every effect is GAP (in a pause, over the bed), OVER (cuts through speech), LOW or MASKED,
   plus ONSET (on a first syllable) and TAIL (tail under speech) flags. An effect that should
   be heard and comes out MASKED is either moved into a pause or cut - it does nothing.
   On a launch film two 10 ms clicks at -26 dB under the narrator came out 30-40 dB under the masker.
   Contact sheets cut from the rendered file: pick frames by number (`select='not(mod(n,15))'`),
   not with `fps=2` - the fps filter took the nearest frame and every tile was labelled 0.233 s
   early, so a reviewer saw scenes start before their cut (a camera-moves test film, 2026-10-14).
   **Sound on its picture** (borrowed: opus-sound-layer qa.py, MIT): `$PY scripts/soundqa.py` with
   mix.py's `placed.json` - every effect marked with `"visual"` must have that change in the
   frame (region with `"roi"` on UI films), every `"align": "peak"` effect peaks on its cue,
   the encoded audio sits within 1 ms of the mix. Lab test 2026-10-14: smash, match and whip
   cues passed, a fake cut in a still scene failed. (`$PY` = the sound library's venv, SKILL.md Setup.)
9. **Black and frozen frames**: `signalstats` YHIGH < 30 sampled at 12 fps (`blackdetect`
   misses black under a caption). Long clips rendered with `-w 1`. Frozen:
   `ffmpeg -i out.mp4 -vf freezedetect=n=0.001:d=1.0 -an -f null - 2>&1 | grep freeze_` lists
   every stretch of ≥ 1 s where nothing moves. Each one must be a choice (UI waiting between
   moves, a freeze on a promise, the end card) - not a dead frame. (talkcraft's `n=0.003`
   calls a panel with words streaming in "frozen": too coarse for UI films.)
10. **Cut seams** (borrowed: nanoclip-cutting-room `switch-scan.mjs` + `switch-lab.mjs`, MIT) - the
   one-frame glitches at a cut that gate 9 misses: a ghost frame (a mix of the two shots), a black
   or flat frame between them, the frame before the cut held while the shot moves, a cut that lands
   a frame early or late, a declared cut where nothing happens. Run on the encoded deliverable:
   `$PY scripts/seamscan.py renders/film.mp4 --scenes scenes.json --scene-in dip:3`
   The scene list is what build.py writes (video-moves scaffold): every scene start is a seam;
   a scene's `"in": "dip:3"` (or `--scene-in` for all), `"cut": u` and
   `"seams": [{"at": u, "kind": "dissolve", "dur": 1.0}]` declare the intended transitions, which
   are then checked against their own shape (a dip falls to one flat frame and back; a dissolve or
   wipe moves one way and never jumps; a whip and a fade never pop), not flagged as glitches.
   No scene list: `--cuts 12.9,f387,62.0:dissolve:1.0,1.5:dip:3`; nothing at all: it detects the cuts
   on the file. Declare whenever the build knows the times - at a known cut any mix of the two
   sides is a ghost and a late cut is caught; detection alone finds only ghosts that cover a tenth
   of the frame, and it cannot know a cut is late.
   **Read** `report.txt` (next to the film in `<film>.seams/`): every line that is not `ok` is a defect
   and the script exits 1; `HELD-AFTER` and `SOFT` are warnings to look at. Then the sheet,
   `seams-NN.jpg`: one row of 7 frames per flagged seam, the declared frame outlined yellow, the bad
   frame red, each tile labelled frame / time / `d` (change from the frame before). Confirm each
   flag on its tiles: a ghost shows both shots in one tile; a held frame is the `d0.0` tile right
   before the cut while the tiles around it move; a late cut shows the old shot inside the yellow
   tile. A `FLASH` at frame 0 is the spliced poster of gate 11. Fix the build (the scene time, the
   tween end, the layer visible a frame too long), never the encoded file. For footage, nanoclip
   found the causes: rounding scene times off the frame grid left black frames, and a `<video>`
   clamped at the end of its window held a frame before the cut.
   Lab test 2026-10-14: a camera-moves test film passes with its 36 seams declared (26 dips, jump,
   match, smash, J/L cuts, whip, dissolve, wipe); 7 clean films, 0 false alarms except a real one -
   two launch films open with a spliced poster that blinks for one frame. Injected black frame,
   2 black frames, ghost, held frame before a cut, late cut, late dip and a held frame inside the
   whip: all caught. Ghosts at every cut: 21/21 on the test film; on a promo with fast moves into
   each cut 14/14 at 50% declared, 10/14 at 25% of the old shot.
11. **Poster**: the strongest settled frame (text fully in) → `poster.jpg`, and frame 0 of
   the film must already BE that settled frame (open settled; no fade-in at the start). Do
   not splice a poster over a fade-in: the spliced frame blinks (a camera-moves test film, 2026-10-14).
   If the opening must move, export `poster.jpg` as the file's thumbnail instead.
12. **Transcribe the finished file** and compare with the script:
    `mlx_whisper <film.mp4> --model mlx-community/whisper-large-v3-turbo --word-timestamps True
    --condition-on-previous-text False --language <first spoken language> --output-format json`
    (Apple Silicon; elsewhere openai-whisper: `whisper <film.mp4> --model turbo --word_timestamps True
    --condition_on_previous_text False --language <lang> --output_format json`).
    Without no-condition Whisper loops the last line over a music tail (x53 on a 72 s film); without
    `--language` it guessed Spanish on a bilingual launch film and invented a "Gracias."; without
    `--model` mlx_whisper runs whisper-tiny. Not parakeet here: it silently dropped the film's
    Spanish passage (a speech-recognition bench, 2026-10-14). Lines in a mixed film start ~0.2-0.4 s
    early in both tools - judge sync by picture checks (soundqa), not by transcript times.
13. **Independent review - every film** (borrowed: video-talkcraft). A fresh subagent that did
    not build the film reviews it against `../video-studio/references/laws.md` and writes `REVIEW.md` with P0/P1/P2 defects;
    fix P0 + P1, then show the user. Protocol: `references/review.md`.
14. **Watch it once, with sound, start to finish.** The metrics confirm; they do not judge.
