# The 24 moves

A catalogue for ANY code-built film - an ad, a launch film for a product or a side project,
a UI walkthrough, an illustrated scene. Each entry is written in roles, not in
one film's content: the **subject** (what the move is about), **near props** (things
between the lens and the subject), the **background** (things behind it), **A/B** (the two
shots of a transition). Fill the roles from the film's own material.

Every entry: what the move tells the viewer, how to build it, the numbers to start from,
what must be visible for it to read, traps, sound, and one example line from the test reel
the moves were built on (77 s, all 24 staged on one recorded video call: a call window with
participant tiles, a shared product panel, a live transcript, the call's real audio). The
example shows one way it was solved - do not copy its content into another film.

Status: all 24 built and reviewed on the test reel (2026-10-14: three independent reviewers,
0 P0, 12 P1 fixed). When a move is used in a real film and the user approves it, add
"Proven in: <film>" to its entry; when rejected, write why.

Contents: 01 Pan · 02 Tilt · 03 Dolly in · 04 Zoom · 05 Tracking · 06 Orbit · 07 Crane up ·
08 Dolly zoom · 09 Rack focus · 10 Handheld · 11 FPV · 12 Dutch angle · 13 Slow motion ·
14 Speed ramp · 15 Time-lapse · 16 Freeze frame · 17 Jump cut · 18 Match cut · 19 Whip pan ·
20 Cross dissolve · 21 Wipe · 22 Smash cut · 23 J-cut · 24 L-cut

## Rules for every move

- Pick by meaning: a move needs a finished "the camera moves because...".
- Build the scene that makes the move visible: parallax needs layers at different depths,
  rack focus needs two planes, a dolly zoom needs a far, structured background, a match
  cut needs two shapes that really match.
- Real UI text: the camera is still between moves (no continuous drift or zoom over text -
  re-rasterised glyphs shimmer). Moves are short, have a cause and land.
- A raster plate ends at its edge: pan, tilt or rotate only inside material. Capture more
  than the frame when a move will travel (a full window, a taller page).
- Crops keep labels, name tags and text lines either whole or fully out of frame.
- Props near the lens fly away from wherever the film keeps its captions or labels.
- Durations: a move starts 0.1-0.3 s after its cut, runs ~1.5-2.5 s, and the landed frame
  holds ≥ 1 s. Camera curves: in-out cubic; hits (crash zoom, whip landing): ease-out;
  zoom, crane and long dollies: log scale (`CK.logLerp`), or they read as braking.

---

## 01 Pan

- **Tells**: we look around; the eye is led from one thing to another.
- **Build**: 2D lens (`lens2d`), move `cx` from the first subject to the second at a zoom
  that frames each; everything shifts together.
- **Numbers**: ~2 s; a sweep of 0.3-0.6 of the material's width.
- **Reads when**: there is no parallax (that would be tracking) and the move ends on its
  subject, centred.
- **Traps**: panning past the material's edge; landing with the subject at the frame edge.
- **Sound**: soft moving air (`air`), ~-24 dB under the bed.
- **Example**: on a full video-call window, the shared panel → the speaker's tile, zoom 1.55.

## 02 Tilt

- **Tells**: height, scale; from a person to what they look at.
- **Build**: 2D lens, move `cy`.
- **Numbers**: ~2 s.
- **Reads when**: there is something at both ends; an empty sky or an empty tile at the
  start kills it.
- **Traps**: a plate that cuts the start subject (capture taller material).
- **Sound**: `air`.
- **Example**: the listener's tile (whole avatar and name) → the panel above it.

## 03 Dolly in

- **Tells**: we come closer; tension rises; we enter the subject's world.
- **Build**: CSS 3D. Subject at z=0, background well behind (z -1500 … -2500), 2-4 near
  props in front (z +600 … +900) spread across the frame. Move the world's z: camera
  distance `P → P_end` with `logLerp`.
- **Numbers**: P 1880 → 1100 (subject x1.7); props leave the frame around 70% of the move.
- **Reads when**: something passes the lens AND something behind grows less than the
  subject. Without both it reads as a zoom.
- **Traps**: props starting at the frame edges are gone before the move is seen; the
  camera must stop before the subject (≥ 2.5x its height away).
- **Sound**: `air` + a short whoosh when the props exit.
- **Example**: a product panel card, a wall of call thumbnails behind, four small chips in
  front; panel x1.71, wall x1.27.

## 04 Zoom in

- **Tells**: an accent, "look at this"; a crash zoom is a comic or hook beat.
- **Build**: 2D lens zoom (`logLerp`). Over a 3D set: a `.lens` wrapping the `.stage`.
- **Numbers**: smooth ~2 s to x1.5-x2; crash 0.3-0.5 s ease-out to x3-x5, then hold.
- **Reads when**: shown against a dolly with the same timing and end size, everything
  grows together and near props are cropped, never passed; or as a crash and a hold.
- **Traps**: a linear scale tween brakes; a slow continuous zoom on UI text shimmers.
- **Sound**: crash: a fast rising whoosh into a soft hit on the landing.
- **Example**: the dolly's set, zoom to the same x1.71.

## 05 Tracking shot

- **Tells**: a journey, a process moving, "we go along".
- **Build**: CSS 3D. The subject moves along x at a steady speed and the world moves by
  `-(subjectX - 960 + offset)`, so the subject stays put on screen; near layer at
  z ≈ +900 (posts, frames, edges), far layer at z ≈ -2400 (a texture, dots).
- **Numbers**: subject 400-800 px/s; near layer ~1.9x, far ~0.4x.
- **Reads when**: the near layer races and the far one crawls while the subject holds.
- **Traps**: a near post covering the subject at the key moment - keep the near layer
  out of the subject's band.
- **Sound**: `air`, low.
- **Example**: the product's pill-shaped badge gliding past a row of participant tiles.

## 06 Orbit (arc shot)

- **Tells**: the subject is the centre of the world; a reveal, a triumph, a finale.
- **Build**: CSS 3D, subject at z=0, background behind; `transformOrigin` at the
  subject's centre, animate the world's `ry`.
- **Numbers**: ±30° for flat subjects (cards, screens), up to ±50°; ~2 s.
- **Reads when**: the background visibly swings the other way.
- **Traps**: flat things seen side-on become lines; check every angle for an object
  behind the subject lining up with it.
- **Sound**: `air`.
- **Example**: the panel card turning -32° → +32° against a wall of calls.

## 07 Crane up

- **Tells**: scale, one among many, a closing move.
- **Build**: CSS 3D floor (a grid of related items, the subject among them); animate the
  world's `rx` up and pull z back (`logLerp`), slightly up in y.
- **Numbers**: rx 0 → 45-55°, distance x3-x4; ~2.3 s.
- **Reads when**: the far edge recedes while the subject shrinks and stays findable.
- **Traps**: the subject lost among identical items - dim or mark the rest.
- **Sound**: `air` + a low swell.
- **Example**: one live call in a 5x5 floor of calls, the others dimmed to 55%.

## 08 Dolly zoom (vertigo)

- **Tells**: realisation, shock, the ground goes; a strong hook.
- **Build**: CSS 3D, subject at z=0 (always scale 1), background far behind. Animate the
  stage's `perspective` (the focal length) with `logLerp`; the subject keeps its size
  exactly, the background grows or recedes `P/(P + depth)`.
- **Numbers**: P 700 → 2600 over ~1.8 s (fast variant ~1.3 s); background ≥ 2000 px deep.
- **Reads when**: the background is far and structured.
- **Traps**: no shake - the eye must see the background move smoothly.
- **Sound**: tone 110 → 520 Hz + rising noise (`riser`).
- **Example**: the panel card in front of a wall of calls 2400 px deep.

## 09 Rack focus

- **Tells**: attention moves; two things are connected.
- **Build**: CSS 3D: a big near object (z ≈ +1000) and the far subject (z=0); blur the
  LEAF layers: far 9 → 0 px, near 0 → 14 px; corner brackets travel from one to the other.
- **Numbers**: the pull ~0.6 s after a 1 s hold; blur values for a 1920-wide frame.
- **Reads when**: the near object is big and coloured and the brackets land on the target.
- **Traps**: blur on a preserve-3d element flattens it; brackets in a colour that vanishes
  on either ground.
- **Sound**: one soft click on the pull (`kenney("tick")`).
- **Example**: a big language chip in front → the transcript column in that language behind.

## 10 Handheld

- **Tells**: presence, documentary, unease; a hard short shake sells an impact.
- **Build**: `CK.handheld` (sums of low sines in degrees) → px with `pxPerDeg`, on the
  lens; an impact: `CK.shake` (seeded, held per 1/12 s, decaying).
- **Numbers**: ~0.5-0.8° yaw/pitch/roll; a hit 8-16 px decaying over ~1 s.
- **Reads when**: the motion is slow and organic.
- **Traps**: a fresh random offset per frame reads as digital jitter; zoom in enough
  (~1.15) that the edges never show.
- **Sound**: none of its own.
- **Example**: the call at zoom 1.15 with a 0.8° sway.

## 11 FPV drone shot

- **Tells**: speed, a chase, flying through a space; an opening.
- **Build**: CSS 3D corridor: items as walls (`translateZ(z) rotateY(±90deg)`) every
  ~700 px, a floor (`rotateX(90deg)`), a landing subject at the far end. Camera z with
  `1-(1-x)^2.2`, a weave on world x, bank as a 2D `rotate()` on the stage proportional to
  lateral speed; weave and bank fade out for the landing.
- **Numbers**: ~9000 px of travel in ~2.6 s; weave ~170 px; bank ~11°.
- **Reads when**: things pass close; an empty space looks slow.
- **Traps**: bank against the turn; anything on the path the camera would fly into.
- **Sound**: saw buzz ~185 Hz with vibrato (`buzz`) + whooshes as walls pass.
- **Example**: an alley of call thumbnails ending on the panel card.

## 12 Dutch angle

- **Tells**: confusion, the world is broken, the problem.
- **Build**: lens `roll`, a slight zoom; corners hidden by `rollCover()` or a matching
  ground.
- **Numbers**: 15-21° over ~1 s, then hold.
- **Reads when**: clearly tilted - under 10° looks like a crooked tripod, over 25° like a
  flip.
- **Traps**: rotated corners exposing the stage.
- **Sound**: a detuned low swell (`drone`).
- **Example**: the call tipping 18°.

## 13 Slow motion

- **Tells**: the peak, the beauty of the moment.
- **Build**: story time (`{until 1.0, rate 1}, {until 1.3, to 0.25}, {rate 0.25}`). The
  world runs on story time; something must move continuously in it (particles, a scope,
  words rising into place, an object in flight) so the slowing is SEEN. A readout
  ("×1,00" → "×0,25") is optional. The camera stays still or also runs on story time.
- **Numbers**: x0.25 (120 fps shown at 30).
- **Reads when**: a moving element visibly slows 4x. Only text fading in reads as a hang.
- **Traps**: anything left in real time while the world slows.
- **Sound**: the recording slowed like tape (`voice_at` on story time) + heartbeats.
- **Example**: a voice scope of the call's real audio scrolling on story time.

## 14 Speed ramp

- **Tells**: an impact, a jump, the accent at the top of an action.
- **Build**: story rate fast → slow → fast; the event sits in the slow minimum.
- **Numbers**: x2 to 0.9 s, ease to x0.2 by 1.3 s, hold to 2.2 s, back to x2 by 2.55 s.
- **Reads when**: the event lands in the slow part and a moving element shows the speed.
- **Traps**: an empty slow stretch; an opaque graph over the subject.
- **Sound**: varispeed voice (fast, then a natural tape stop), `tape_stop` 260 → 45 Hz, a
  heartbeat in the slow part.
- **Example**: a translated line landing at x0.2, with the scope and a rate graph.

## 15 Time-lapse

- **Tells**: hours passed, waiting, day into evening.
- **Build**: changes in STEPS (0.05-0.12 s): a clock, content piling up, things flicking
  on/off from a seeded rng; light shifts (a multiply grade to warm).
- **Numbers**: 6-8 hours in 2-4 s; 10-minute clock steps.
- **Reads when**: things jump in steps; smooth change reads as normal footage.
- **Traps**: looking like a jump cut - give it the stepping and the light shift.
- **Sound**: ticks that speed up (`ticks()`), an arpeggio up at the end.
- **Example**: a clock 10:00 → 18:00, the transcript piling up, the picture warming.

## 16 Freeze frame

- **Tells**: "this moment", a pause to explain or for a joke.
- **Build**: story rate 0 at the peak; an accent border and a pause mark while it holds.
- **Numbers**: 0.9-1.8 s at the top of the action.
- **Reads when**: everything stops - check the freeze frame alone for anything covering
  the subject.
- **Traps**: an overlay moving during the freeze; a mark over the subject or the logo.
- **Sound**: everything cuts, a high ring (`ring`, 1760 Hz), a whoosh out.
- **Example**: a transcript line frozen mid-word with the scope stopped.

## 17 Jump cut

- **Tells**: time skips, waiting, a ragged rhythm.
- **Build**: one locked frame, N states (`CK.jumpIndex`); the states differ in LAYOUT
  (position, presence, pose), not only in text.
- **Numbers**: 3-5 states x 0.45 s (fast) to 1.2 s.
- **Reads when**: each jump changes the picture's shape.
- **Traps**: any camera move turns it into a plain cut; text-only changes read as a
  screen updating.
- **Sound**: a click on every jump.
- **Example**: a video-call window: screen share off, camera off, a guest leaves.

## 18 Match cut

- **Tells**: a rhyme - two scenes are one idea.
- **Build**: push in on a shape in A until it sits at a chosen point and size; hard cut to
  B framed so the matching shape is at the same point and size; then reveal B. If A and B
  differ in brightness, a scrim on B keeps A's ground around the shape (the hole follows
  the shape) and lifts after the cut.
- **Numbers**: same centre, same diameter (±2 px); hold 0.2 s either side of the cut.
- **Reads when**: position, size and ground match.
- **Traps**: a brightness jump beats the rhyme; a hole bigger than the shape leaves a
  ring; build the B side as vector if it is zoomed hard.
- **Sound**: a bell or soft hit on the cut frame, audible over the bed.
- **Example**: a round avatar → a round language flag, 268 px.

## 19 Whip pan

- **Tells**: energy, "meanwhile", cause here → effect there.
- **Build**: ONE world with A and B side by side; throw the lens across; horizontal blur
  from speed (SVG `feGaussianBlur stdDeviation="x 0"`), off when < 0.5 px.
- **Numbers**: 0.5-0.6 s in-out; blur `min(150, v*0.03)` (≈ 8% of the frame at the peak).
- **Reads when**: there is no gap between A and B.
- **Traps**: two scenes slid apart expose the ground; out and in in different
  directions; too wide a sweep smears into a blob.
- **Sound**: a cause sound (a click), then a whoosh with a rising band.
- **Example**: a "Create" button click → the result next door.

## 20 Cross dissolve

- **Tells**: a soft change of place or time; the final card.
- **Build**: B on top with `opacity = CK.dissolve(...)`; A keeps moving under it.
- **Numbers**: 0.8-1.2 s.
- **Reads when**: one side is calm.
- **Traps**: two busy layouts make a muddy double exposure; a dead hold after it (push
  the card 2-4%).
- **Sound**: the bed carries it.
- **Example**: the call into the end card.

## 21 Wipe

- **Tells**: a new chapter; before/after.
- **Build**: B on top with `clip-path: inset(0 W-x 0 0)`, x by `CK.wipeX`; a thin line on
  the edge.
- **Numbers**: ~1.1 s, in-out.
- **Reads when**: the edge line is visible on both grounds.
- **Traps**: changing direction within a film.
- **Sound**: a soft moving swish.
- **Example**: the call without the product → with it.

## 22 Smash cut

- **Tells**: shock, a joke, waking up; a hook.
- **Build**: a quiet A (wide, still, near silent) → hard cut to a contrasting B (close,
  tilted, shaking, loud).
- **Numbers**: A ~1-1.5 s; B shake decaying over ~1 s; B roll ~-7°.
- **Reads when**: everything contrasts at once and the hit lands on the cut frame.
- **Traps**: the sound one frame off; a scene boundary just before it with the same
  contrast becomes a false smash cut (separate with a dip).
- **Sound**: hum only on A, the bed cut; the hit and B's sound on the cut frame.
- **Example**: a silent call → a shaking close-up of the transcript with the voice.

## 23 J-cut

- **Tells**: the next scene's sound calls us into it.
- **Build**: B's sound starts before B's picture; in a teaching reel an edit strip shows
  both cuts.
- **Numbers**: lead 0.3-0.5 s, measured from B's first AUDIBLE sound (`speech_onset`).
- **Reads when**: the lead is heard and B's sound is recognisable.
- **Traps**: a recording with silence at its head shortens the lead; over 1 s reads as a
  sync error.
- **Sound**: B's sound with a 10 ms attack.
- **Example**: the call's first words heard over the setup form.

## 24 L-cut

- **Tells**: the previous scene's feeling does not let go.
- **Build**: A's sound runs past the picture cut and fades.
- **Numbers**: tail 0.3-1.5 s, fade over the last 0.5 s.
- **Reads when**: the tail is clear and fades.
- **Traps**: no fade clicks; a loud tail over a loud B is mush; start A's clip on a
  phrase, never mid-word.
- **Sound**: A's sound, faded.
- **Example**: the speaker's last line finishing over the end card.

---

# World moves (beyond the 24)

Moves for a film set in one drawn world (a map with places, interiors, characters); recipe:
video-studio `format-world.md`. Proven on a world film (the kit's own launch film, 2026-10-23).

## W1 Dive into a place

- **Tells**: we go inside the place on the map where this stage happens. It replaces the cut
  between the map and an interior.
- **Build**: the camera key on the house zooms the world 2.4 → 5.2 with a blur rising to 6 px
  over ~0.35 s. In the same window the interior layer (a full-frame room picture plus its work)
  fades in from 0 and scales 1.22 → 1 about its centre (transform-origin 50% 45%). The exit is the
  reverse: the room scales to 0.55 and fades over 0.35 s while the world sharpens and pulls back
  to 2.4.
- **Reads when**: the house is at the centre of the frame before the dive, so the room seems to
  come out of it.
- **Traps**: text on the room's board appears only after the room has settled (+0.4 s). A push
  onto the board inside the room starts after that too, or the scale jumps (cut-seam scan:
  FLASH). A long room scene still needs motion inside it: the dive does not carry 12 s.
- **Sound**: a short two-note "door" synth on the room's first frame.

## W2 Along the road

- **Tells**: the loop is a real path; stage → stage is a journey, clockwise.
- **Build**: an "arc" camera key interpolates the angle around the road's centre, not x/y. Lean on
  the road: `cx = lerp(road(θ), straight(θ), 1 - 0.75·sin(πu))`, so the camera follows the road
  mid-way and lands exactly on the next key. Lift the zoom by 16% mid-way
  (`z *= 1 - 0.16·sin(πu)`) to see more of the road while travelling.
- **Trap**: never assume the road is an ellipse. Trace its centreline from the picture: a colour
  mask, runs along rays from the centre, a robust Fourier fit, one point per degree. The assumed
  ellipse was 19 px off and the owner saw that "the ring does not follow the road". Re-trace after
  any redraw of the art.

## W3 The carrier

- **Tells**: the work moves from one team to the next; the result of one stage is the input of the
  next.
- **Build**: a small character is placed at the camera's road point every frame. It walks (frames
  alternate at 8 fps) and faces the direction of travel, from the road's tangent. Its item sits at
  hand height on the side it faces, not over its head. It fades in and out over 0.15 s at the
  ends. The same character's sprite at its home door is hidden while it is away.
- **Reads when**: the item it carries is the item that left the last room (a case, a scroll, a
  crate), and the next room starts with the character putting it down.
- **Sound**: soft footsteps (a low-passed noise tick at ~7/s) at texture level.
