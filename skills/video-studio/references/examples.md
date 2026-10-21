# Examples: three requests and what the studio does

Each walks the order of work in SKILL.md. Times are rough; the gates and the review are never
skipped.

## 1. "Make a 6-second end card with our logo and 'Try it free'."

- **Format**: motion card (`format-motion-card.md`). 16:9, plus 9:16 if the user runs Reels.
- **Ask first** (one message): the logo files, the brand colours or tokens file, voice or no
  voice, the URL or offer line if any.
- **Brief**: copy verbatim ("Try it free" + the URL), palette and fonts from the brand tokens,
  private data "none".
- **Audio first**: if voiced, one line through video-sound `gen_voice.py --must "<Brand>"`;
  a sting from the library on the logo landing, in the gap after the last word.
- **Build**: video-build scaffold, one paused GSAP timeline, the logo trimmed to its alpha box;
  `hyperframes check` clean; a still of the landed frame to confirm the logo is visible
  (check measures text, not images).
- **Gates and review**: video-check; poster = the settled logo frame = frame 0.
- **Deliver**: `endcard-16x9.mp4` (+ `-9x16`), poster; offer `ads-video-library` to name and
  catalogue it.

## 2. "Make a 20-second launch video for our new feature. Here is the app."

- **Format**: launch film (`format-launch.md`). Answer its questions; write three candidate
  structures in `plan.md`; compare against the last launch film (four of six points must
  differ); pick one signature moment from video-moves.
- **Private data**: the real app will be on screen - list what is visible (customer names,
  emails, keys, invoices) and ask: keep, or plausible stand-ins?
- **Brief**: every on-screen claim with its source (the feature's UI, docs, changelog); copy;
  scenes table; the signature moment.
- **Audio first**: voice lines generated, gated and measured; the timings go to `timing.json`.
- **Build**: the real UI captured and composed from its own classes (video-build
  `product-ui.md`), one idea per line on clean cards, captions word by word; a 10-12 s proof
  approved before the rest.
- **Sound**: a beat-mapped bed, the reveal on a strong cue, effects only where something
  visibly happens, the mix to -14 LUFS.
- **Gates and review**: the full video-check set, then a fresh reviewer; fix P0/P1, list P2.
- **Deliver**: `<name>.mp4`, poster, `share-copy.txt`, `plan.md` with number sources, `REVIEW.md`.

## 3. "Make it like this ad: <link>."

- **Format**: reference copy (`format-reference-copy.md`), then whichever format the
  reference needs - code-built cards, a launch film, or generated people.
- **Breakdown first**: `/watch` the reference (or stills + a transcript): shots with times, what
  each beat does, the moves, the sound.
- **Transfer table**: their beat → your beat; your words from your product brief, your
  characters, your aspect per channel (brand laws).
- **Generated shots** (if the ad has people): video-generated - character sheets, a set plate
  and keyframes approved at image prices before any video is generated; one paid call per new
  model, then read the dashboard.
- **Watch side by side** with the reference before showing the user.
