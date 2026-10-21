# QA tools for a WebGL / WebGPU film

The procedure is `references/qa-3d.md`; these are its tools.

- `seek-order-test.mjs` - seeks the page in order, in a seeded shuffled order and in reverse, and compares
  frame hashes. The only test that catches state carried from one seek to the next (worker renders seek in
  order inside each chunk, so they all agree with the bug). Also fails on a rejected build hold, renderAt
  errors and a blank page. Generalised from the models reel; run on the ASCII film and the models and
  WebGPU reels: 0 mismatches.
  ```bash
  node seek-order-test.mjs <film dir> --step 3 --cuts 4.5,8.5,14 [--capture canvas --canvas "#gl"] [--soft]
  ```
  Uses HyperFrames' cached chrome-headless-shell and puppeteer-core (found in the npx cache). The runtime is
  not loaded, so GSAP timelines and sub-compositions are not exercised. A full sample (every 3rd frame of a
  45 s film, ~480 frames x 3 orders) takes a few minutes with screenshot capture.
- `compare_sections.py A B --cuts 0,4.5,...` - per-section comparison of two renders: framemd5 files or
  videos (differing frames), or PNG directories (differing frames, max level difference, min PSNR; a section
  above `--psnr-floor 48` counts as unchanged). Exit 1 if any section differs.
- `blank_check.py film.mp4 --cuts 0,4.5,...` - per section: mean luma, near-black share, magenta frames (the
  renderAt try/catch colour) and the longest run of still frames. Catches the blank film a rejected build
  hold leaves behind (exit 0 from the CLI) and frozen holds.
- `look_shimmer.py <png dir> --cell WxH [--spans a-b,c-d]` - exact per-cell shimmer for grid looks (a cell's
  signature = all its bytes): change, A-B-A blip, revisit. Companion to `../ascii/ascii_shimmer.py`, which
  signs cells by an ink mask and reports temporal jitter (2.0 = a clean hard step).
