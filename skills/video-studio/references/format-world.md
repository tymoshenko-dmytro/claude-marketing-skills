# Format: world film (one illustrated world, a cast, one camera)

A 45-90 s film that explains a team, a system or a process as a place where characters work: a
map with houses, interiors where the work happens, characters who carry the work between them.
Use it when the film would otherwise be a run of cards ("agent + what it does" × N): that reads
as a slideshow, however good each card is.

Worked example: this kit's own launch film, *Claude Growth Team* (66 s, attached to the v2.1.0
release). It was made with these skills: a pixel island with four houses on a ring road (Research,
Strategy, Launch, Analysis), 20 agents drawn in code, one request carried round the loop. It took
five animatic rounds with the owner, then the gates and three independent reviewers.

## Why the card version failed

- Every scene had one layout: a header card (agent + line) over a data card. That is a
  slide template.
- Each card held about 5 s with one or two things moving. In the reference films nothing holds
  still longer than ~1 s.
- Transitions were slide changes: a zoom on a picture inside the slide, a side pan, a whoosh.
  The owner called them cringe.

The fix is structural: one world and one camera, not better cards.

## Order of work

1. **Teardown of the references** the user sent: how they move, what carries each transition,
   how much text is in one frame. Write the film's design rules from it and ask the open
   questions: the hero object, how the characters look, the ground.
2. **World, interiors, cast.**
   - World: one generated map (for example `gpt-image-2.5`, 1536×1024, medium quality for drafts)
     with one place per stage on a path. Each place gets an interior with one blank surface (a
     board, a screen, a wall) where the work will sit.
   - Cast: one family drawn in code (SVG rects on an 18×18 grid), so it is crisp at any scale and
     easy to animate: stand, two walk frames, blink, arms up. Silhouette shared; colour = the
     place it belongs to; a held tool = its role; leads wear a mark (a crown).
3. **Three style frames** (opening, a work scene, the peak) as stills. Get them approved before
   any motion.
4. **Rough animatic** with the final voice, the music and the camera. Prefer it to a full
   storyboard: the user judges motion and pace, which a storyboard cannot show.
5. **Rounds of the user's notes** on the animatic. Expect several; each round fixes one class of
   problem. In the example: chaos in the opening, then tidiness, then the UI style, then what the
   copy means, then fonts.
6. **Upgrade the art when the layout is final.** Use an image *edit* at high quality with the
   prompt "redraw at high resolution, same composition, same positions and sizes" (for example
   `gpt-image-2.5-sunburst`, 3072×2048). In the example, the boards moved by at most 3 px.
   Re-measure them (label the board colour, take its bounding box) and re-trace any path the
   film follows.
7. Gates and independent review as for every film (video-check).

## Shape

- **Bookend on the hero object.** Open on the request line, already typed on frame 0 (it is the
  poster), in the middle of the map. The cast springs out of it, each colour group on the side of
  its own house. Close on a new request, born from the last scene's result and carried back to
  the first house. Then the title.
- **Map → dive → work → carrier → next place.**
  - The camera dives into a house (video-moves, "World moves") and the interior grows in.
  - The work happens on the interior's surface.
  - The room shrinks back into its house.
  - A character carries the result (a case, a scroll, a crate) along the road to the next
    house, and the camera follows.
- **A stage marker** in one corner (a ring in four quarters) says where the loop is. It switches
  on the word that names the stage and is gone before the end card.

## Rules that came from the user's notes (all made it into the approved cut)

- **One colour, one place.** A colour group walks straight to its own door when the voice names
  its stage. No group visits two houses and no paths cross. A character who works in another
  house is seen leaving its own door on the map, and its sprite at the door is gone while it is
  away (no clones).
- **Nothing hangs on an empty screen.** Every number, card and chip sits on a surface of the
  world: a board, a screen, a wall.
- **Characters act on the material.** Examples from the cut:
  - the ad analyst jumps, and with each jump a batch of ads is pinned on the wall;
  - the critic jumps onto the screen's edge and strikes the line;
  - the designer hops from banner to banner as each ad size appears;
  - the QA reviewer hops as a check lands on each clip's name plate;
  - the crew cheers each approval;
  - the analysts jump onto the consoles to point at the number.
  Invent such a detail for every beat.
- **Items in hands, not on faces.** A carried item sits at hand height on the side the character
  faces. A sprite turns to where it moves (take the facing from its keyframes).
- **Characters stand in front of screens only where the screen is empty.** Make the build assert
  it: an analyst standing on a console would have covered a number.
- **No silent stretch where only a character runs.** Fill every gap in the voice with an action
  that adds meaning, such as pointing at the week that grew.
- **The UI matches the world.** In a pixel world:
  - panels, chips, buttons, the cursor, check marks, logos and subtitles are pixel art in the
    world's palette;
  - panels are paper with an ink border (four offset box-shadows give notched corners) and a
    hard drop shadow;
  - logos are 16×16, drawn from the real SVG, in brand colours, with a hard palette;
  - subtitles are a dialogue box.
  "Old plaques pasted into a new world" was rejected at once.
- **Two fonts.** One display face in the world's style, one reading face. The approved pair:
  Pixelify Sans Bold (labels, titles) and JetBrains Mono (the request line, board text,
  subtitles, every digit). Choose the pair on stills: 3-5 pairs on the same scene.
  Press Start 2P is too wide for small chips.
- **Check a pixel font letter by letter at phone size.** Pixelify Sans Bold's C and c are almost
  closed: "CLAUDE" read as "OLAUDE". Its 2, 5 and 8 read alike: "26" read as "86". The fix that
  kept the chosen font: open the C, G and c with fontTools (move the ends of the right arms
  away from the middle) and set every digit in the mono face.
- **Board copy answers one question in plain words.** A number always carries its meaning.
  - "0 clicks" became "11,761 times shown in Google, 352 clicks".
  - "26" became "26 sign-ups per week, up from 15", over a chart of the weeks that show it.
  - "Test: sell to one person on their calls" was not understood. It became three rows,
    WHO / SAY / WHERE, each with a grey line saying where it came from.
- **Collections are galleries, not dashboards.** Show the rivals' ads as a wall of real vertical
  video ads playing muted, uncropped, across the whole room. A small board with text over the
  thumbnails read as messy. The ads must belong to the rivals named in the research behind the
  numbers next to them.
- **No repeats in a collection.** One creative in two language versions on the same wall stood
  out at once. Check the wall on a contact sheet of the clips' frames before the render.
- **Push onto the board while text is on it, gently.** The interiors frame the board at ~38% of the
  width. For the text beats, the room scales ×1.12-1.15 about the board's top centre: the board
  grows down and a character on its top edge stays in frame. At ×1.3 the characters left the
  frame. The push starts only after the room has settled (a push that starts during the room's
  entrance makes the scale jump), and it is back at 1 before floor action and before the room
  exits.
- **The world is alive but quiet.** Faint pixel sparkles on the water: ~70 tiny rects, each on
  its own sin^8 curve.

## Build notes

video-build `hyperframes-gotchas.md`, "Found on a world film": the text-fit check at build time,
the font a browser rejects silently, sorted keyframes, hidden elements that ramp in, typed text
reset, `<video>` walls, logo rasterising, characters over boards, sprite facing. video-moves
`moves.md`, "World moves": the dive, the road arc, the carrier. video-sound `audio.md`, "Synth
effects for a stylised world".

## Cost and time (the example)

- Images: one draft world, four rooms and their high-quality redraws cost about $2.
- Renders: a 66 s render took about 9 minutes. Each animatic round took one render plus stills.
- Rounds: five animatic rounds after the style frames, then the gates and one review round
  (three reviewers: 4 P0, about 30 P1, all fixed).
