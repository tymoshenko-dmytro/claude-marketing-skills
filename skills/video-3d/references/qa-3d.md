# QA for a WebGL / WebGPU film

On top of video-check's gates (which still apply), because `hyperframes check` cannot see a canvas: it
passes with "0/0 text checks". Tools: `assets/recipes/qa/` (README there).

1. **Lint** with `check` - root attributes, structure, overflow markers, DOM text contrast. Not a picture
   check.
2. **Snapshots at every state change** (each landing, each cut, the morph peak, the hold) with
   `hyperframes snapshot` (`--timeout 60000` for builds over 3 s), plus the first frame (it must be a
   settled, postable frame - a flat line or an empty grid makes a weak poster).
3. **Determinism protocol** (same `--browser-gpu` setting everywhere):
   ```bash
   Q="${CLAUDE_SKILL_DIR}/assets/recipes/qa"     # CLAUDE_SKILL_DIR = this skill's folder
   npx hyperframes render -q high --crf 10 --browser-gpu --workers 4 -o renders/film-w4.mp4
   npx hyperframes render -q high --crf 10 --browser-gpu --workers 1 -o renders/film-w1.mp4
   python3 $Q/compare_sections.py renders/film-w4.mp4 renders/film-w1.mp4 --cuts 0,4.5,8.5,...
   node $Q/seek-order-test.mjs . --step 3 --cuts 4.5,8.5,...
   ```
   - `--workers auto` is NOT a parallel test: HyperFrames 0.8.156 renders films of ≥ 900 frames on one
     worker. Force `--workers 4` (out-of-order chunks) against `--workers 1`.
   - The seek-order test is required as well: every worker seeks in order inside its chunk, so state carried
     between seeks renders identically with any worker count (the models reel: three identical, wrong
     renders; the shuffled test found 226 of 484 frames different). It seeks in order, shuffled and in
     reverse, and also fails on a rejected build hold and on `renderAt` errors.
   - If the MP4 checksums differ, render PNG sequences (`--format png-sequence`) and compare per section
     (`compare_sections.py` on the two directories) before blaming the scene: WebGL-only output was
     bit-identical in every film; DOM over WebGL may differ by ≤ 2 levels on a few hundred pixels; a heavy
     WebGPU section varied in ~1 frame of 600 at 73 dB (invisible).
   - Between two VERSIONS of a film, an edit changes the encoded frames before it (x264 look-ahead): prove
     an untouched section unchanged on PNGs, or by PSNR > 48 dB - not by framemd5.
4. **Blank, magenta and frozen output**: `python3 $Q/blank_check.py film.mp4 --cuts ...`. A rejected build
   hold renders a blank film with exit 0; an exception in `renderAt` shows magenta (the skeleton's catch);
   a section with a long run of still frames is a frozen hold (a hold needs visible drift; a section must
   still move in its last 0.5 s).
5. **1:1 crops** of the thinnest line, the smallest label, the sharpest bevel corner, and two consecutive
   frames in the fastest motion (sparkle, shimmer, aliasing, bokeh ladders).
6. **Chunk seams**: the frame-to-frame difference curve (`ffmpeg -i film.mp4 -vf
   "tblend=all_mode=difference,signalstats" ...`) - no step at the worker chunk boundaries above ~1.2x its
   neighbours (an unseeded SSAO pass stepped 1.47x at the boundary).
7. **Banding**: boost the contrast of a dark corner of the ENCODED file; flat runs over ~25 px mean add
   dither or raise the bitrate.
8. **Colour**: read the hero colours on a rendered frame and compare with the film's palette; tone mapping,
   light and environment rotation move hues.
9. **Quantised looks** (ASCII, pixel art, dither, halftone, toon bands, CRT): render a PNG sequence and run
   `assets/recipes/ascii/ascii_shimmer.py` (cells changing, A-B-A blips, temporal jitter per span; `--cell`
   = the grid) and `assets/recipes/qa/look_shimmer.py` (exact per-cell bytes: change, blip, revisit - it
   also catches changes between two dark colours).
   - Reference (ASCII): hold blips 0.12% / jitter 1.03, fly-through blips 1.2% / jitter 2.25.
   - Jitter is exactly 2.0 for any clean hard step (a pixel flips once and stays) and rises above 2 only on
     reversals, so hard-threshold looks (1-bit and palette dither, pixel art, toon bands) sit at ~2.0 with no
     flicker at all: judge them by A-B-A blips and blip/change (styles reel: hold blips 0.001-0.32%). CRT
     flicker and ink boil exceed 2 on purpose.
   - Before judging any glyph frame, read the luminance quantiles the pass sees (ASCII README, step 3).
10. Then video-check's sound, review and "watch once" gates.
