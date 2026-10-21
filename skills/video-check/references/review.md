# Independent review

Every film, after the machine gates in qa.md and before the user sees it, is reviewed by a
subagent that did not build it. The builder has blind spots for its own frames, and its
own plan is the yardstick it would check against - that loop passes films "with zero
defects" that are full of them. Adapted from video-talkcraft's review protocol (ideas only;
its code is under a noncommercial licence).

Two readers: the **builder** (when to dispatch, what to hand over, how to fix) and the
**reviewer** (a fresh subagent that must read this file first).

## 1. Dispatch (builder)

- **Fresh context, every time.** `Agent` tool, `subagent_type: "general-purpose"`, in the
  background. Never `fork` (it inherits the builder's view), never `SendMessage` a reviewer
  to re-review its own findings - a re-review is a new subagent.
- **The packet** is a self-contained prompt; the reviewer sees only the packet and disk:
  1. "Read `<video-check>/references/review.md` section 2 first, then
     `<video-studio>/references/laws.md`." - with the absolute paths of the two skill folders
     where they are installed (the reviewer starts in an empty context and cannot guess them).
  2. The film: the deliverable `.mp4` path and its length.
  3. Contact sheets made by the builder: `stills.py <project> --every 0.5` (whole film) and
     `--width 390 --cols 2` (phone), plus the stills folder for single frames. The reviewer
     looks at sheets first and opens single frames only where something looks wrong.
  4. The script (`lines.json` or the plan's spoken lines) and the plan (the film's plan or
     `README.md` with where every on-screen number came from).
  5. The source of truth for claims: the film's `brief.md` (copy, claims and their sources, private
     data decisions, scenes), the product folder, the measurement logs.
  6. Its ears, since it cannot listen: the transcript of the final file (qa.md 12), the
     `sfxcheck.py` report, the loudness line. Its reading clock: the `readcheck.mjs` report.
  7. Where to write: `<project>/REVIEW.md` (round 2 and on: `REVIEW-2.md`, ...).
- A film over ~60 s: two reviewers split by time range (each also gets the full sheet),
  plus one that only checks consistency across the whole film.
- **Waiting.** Done = `REVIEW.md` has its end line, not the completion notice (a notice
  can arrive with an empty report). Every few minutes check that `REVIEW.md` grows; no
  growth for 10 minutes → stop the subagent (`TaskStop`) and dispatch a new one with the
  same packet plus one line on what failed and what changed (fewer frames, a narrower
  range). Three dispatches without a report → show the film to the user marked
  "no independent review" with the three reasons. The builder never reviews itself as a
  substitute.

## 2. Review (reviewer)

- **Write as you go.** First write the skeleton of `REVIEW.md` (packet list, empty P0 / P1 /
  P2 sections), then add each defect the moment you find it. A reviewer that holds
  everything for one final message runs out of context and leaves nothing. Finish with
  the line `## Review complete · looked at <from>-<to> s of <length> s`.
- **What to look for** - film defects, judged as a viewer would:
  - **Facts and words**: every name, number, feature and quote on screen or spoken is found
    in the source (packet item 5); spelling of product names; the transcript says what the
    script says.
  - **Readability**: text cut by an edge, too small at phone width, too short on screen
    (readcheck report), text on a busy or same-colour ground, a brand accent colour used for
    small text it does not have the contrast for.
  - **Layout**: elements colliding or covering text, a caption over the thing being
    discussed, two ideas on one screen, a crop that cuts a picture or a card.
  - **Motion**: an element visible before its entrance, a flash, a double exposure, two
    motions at once, a dead frame (freezedetect list), motion with no cause on screen.
  - **Message**: the words and the screen say different things; the hook does not say what
    the product is or what pain it solves; a claim shown without the material that proves it.
  - **Sound** (from the reports): an effect that should be heard but is MASKED, a sound on a
    first syllable, a tail under speech, loudness off -14 LUFS, names misheard.
  - **Laws**: anything else in laws.md the film breaks - name the law.
  An entrance caught mid-way is not a defect; judge settled frames and the middle of
  transitions separately.
- **Grades**:
  - **P0** - every viewer notices and it hurts understanding: a wrong fact, name or typo,
    unreadable text, picture and voice out of sync, text covered, an arrow or ring on the
    wrong target.
  - **P1** - breaks a law or clearly looks wrong: a flash, an overlap, an element before its
    entrance, a line short on screen, an effect that does nothing, words and screen apart.
  - **P2** - polish: spacing, density, a nicer timing.
- **Each defect**: time (or range), what is wrong, which frame shows it (path), the law if
  one applies, and what would fix it. No "looks fine overall" - only defects.

## 3. Fixing (builder)

- Fix every P0 and P1, then show the film. P2 goes to the user as a list with the film -
  their call whether to fix it.
- **One round, then show.** After fixing, ask the user whether to run another review round;
  each round is a new reviewer. Three rounds at most - after that, hand over what is left
  with what was tried.
- **Prove a fix with numbers**, not "looks right now": the time an element first shows,
  the overlap in pixels, the seconds on screen from readcheck.
- **The user's time-coded notes**: for each, keep three frames - before the fix, after the
  fix, the same time in the final file - and list them in the fix notes. A state that
  changes over time (an entrance, an exit, a swap) is checked across its whole range: start,
  middle, end, and the edges before and after.
- **The same problem fixed twice**: write down why the first fix did not hold.
- Re-render only what changed when the composition allows it; re-run the gates the fix
  touched.
