# HyperFrames traps

Every one of these cost a wasted render or a wrong-looking deliverable. Read before
writing composition HTML.

## Layout

**`.clip { position: absolute; inset: 0; }` is required.** The runtime stretches a
root-level timed element to the frame only when it has *no computed size of its own*.
A flex container with content has one, so it collapses into the top-left corner and
every bottom-aligned caption rides up to the top. The scaffold's shared rule is what
the docs assume is present — write it yourself.

**Asset paths are root-relative in every composition, including files under
`compositions/`.** They are served with the project root as their base URL, so
`../assets/x.css` resolves outside the project and 404s in preview. Use
`assets/x.css` everywhere. (Inside a *stylesheet*, `@import` resolves relative to the
stylesheet, so a token file next to it is imported by bare filename.)

**Never size an element with a CSS `transform` that GSAP also animates.** A pop-in
tween writing `scale(1)` inline beats the stylesheet's `scale(1.5)` and the element
silently renders at its unscaled size. Put sizing on a wrapper; let the tween own the
element's own transform.

**Do not rely on `min-width` plus shrink-to-fit for a wrapping row.** `max-content`
ignores flex wrapping, so a row that will wrap is measured as one long line and the
container blows past the frame. Set an explicit width on the wrapper.

**`vmin` is 1080px in both 1920×1080 and 1080×1920.** Type sized in vmin is
physically identical in either aspect — that is the whole point — but a card sized to
fill the portrait frame is lost in the landscape one. Scale the whole stack on a
wrapper rather than re-specifying every size.

## Text reveals

**`clip-path` cannot wipe wrapped inline text.** It clips to a single rectangle
derived from the first fragment and swallows every visual line after it — the tail of
a wrapped sentence simply never appears. Reveal per word instead: one span per word,
all present at zero opacity from the first frame (so the column never reflows), then
a staggered opacity tween across the line's spoken duration. It is also more honest
for a transcript: words arrive as they are recognised.

## Media

**`<audio>` without an `id` is never mixed — the render is silent.** `lint` says so;
believe it.

**Video needs `muted`, or `data-has-audio="true"` if its own track should play.**
Generated clips usually carry audio you do not want. An undeclared track fails
`check`.

**Set an audio clip's `data-duration` to the media's real length.** A voice track
that ends before the film does (a silent end card) otherwise raises `clip_media_fit`.

## Checking

**`hyperframes check` measures text contrast, not images.** It will happily pass a
logo that is invisible on its background. Look at a rendered frame.

**Contrast failures are usually a ground problem, not a colour problem.** Dark ink
centred on a blue-to-white gradient sits on the blue half and measures 1.6:1. Decide
the ground first, then let the ink follow it.

**A decorative element that deliberately sweeps outside its parent** (a button sheen)
needs `data-layout-ignore="true"`, or `check` reports it as escaped and overflowing
on every sampled frame.

**Track density warnings are advisory.** Thirty-five captions on one track is what a
caption track looks like; leave it.

## Rendering

**h264 needs even dimensions.** 1365×768 fails to encode; 1366×768 works.

**Concatenated clips gain a frame or two each.** Five 30fps segments cut to exact
seconds came out 0.2s long overall. Measure the assembled file rather than trusting
the sum of the parts.

## Found on the first two-slide card

**A fade that ends on a clip boundary needs a `tl.set` hard kill after it.**
`check` reports `gsap_exit_missing_hard_kill`. A non-linear seek can land past the
fade and restore the stale visible state, so the outgoing slide flashes back over the
incoming one. Write both:

```js
tl.to(".fit1", {opacity:0, duration:0.30}, 8.48);
tl.set(".fit1", {opacity:0}, 8.82);   // the boundary itself
```

**`text-wrap: balance` is not enough for a headline.** It still leaves orphans -
"A live AI note-taker for sales / calls". Set the break by hand: one `div` per written
line with `white-space: nowrap`, and let the word spans live inside those. The break
then belongs to the writer, which is also what a card set needs as a per-card
parameter.

**A v3 take's length varies run to run.** The same seven words at the same `--speed`
came back at 3.02s, 3.30s and 3.35s. So the bar grid cannot be planned before the
audio exists - "audio first" is arithmetic, not taste. Generate, measure, then fit.

**Eleven Music is gated.** `POST /v1/music` returns 403 `feature_not_available` until
the account accepts the separate music terms, and it carries its own pricing. Not a
decision to make on the account owner's behalf - use an existing bed, or ask.

## Sound over speech

**Nothing with a tail goes over a voice, and the first syllable is the worst place
of all.** A 0.88s shimmer laid on the opening word of a card was heard as a fault in
the recording, twice, in two different projects — the second time because the fix
was applied to one card and not to its sibling. The rule that survived: the only
audio allowed over a spoken line is texture at −24 dB or below, the kind you notice
only when it is missing. Everything that is meant to be *heard* as an event — a
confirm, a swell, a chime — waits for a beat where nobody is talking. On a
two-slide card that means the beat after the last word, and the cover.

**A card's grid should match the library the beds come from.** Ours was 110 because
the first project happened to be built there. The marketplace we buy from lives at
120 — seven of thirteen candidates, four within 0.2 BPM — so the grid moved to 120,
where the bar is exactly 2.0s. A bed running at its own tempo puts the percussive
effects between its own hits, which reads as slop.

## Animating a supplied asset

**A baked shadow is invisible travel.** A directional reveal spends its ease over the
asset's *box*, not over what you can see in it. One identity SVG carried 61px of bottom
margin for a drop shadow that measures 1/255 against brand blue — 16% of its height, so
on `power2.out` the last third of the tween moved through nothing. Measure the asset's
margins against the actual ground, then trim the viewBox; do not compensate with the
curve.

**`clip-path` is the safe reveal for a box `check` measures.** The obvious
alternative — an `overflow: hidden` wrapper animated from zero height — makes the child's
bounding rect larger than its parent for the whole reveal, which the layout sampler
reports as escaped and overflowing, and it reflows whatever sits below as it grows.
`clip-path` leaves the box alone and only changes paint. Write both endpoints explicitly
with matching component counts (`inset(0% 0% 100% 0%)` → `inset(0% 0% 0% 0%)`) and repeat
the closed state in CSS, so a seek to frame 0 never parses it back out of a computed
style. Use height-on-overflow only when something must stay pinned to the moving edge.

That "matching component counts" is not pedantry. On a second project GSAP **silently
refused to interpolate the same two endpoints** — Chromium serialised them with different
numbers of values — and the panel snapped open in a single frame. No error, no warning,
`check` clean. If a `clip-path` reveal appears to have no duration, that is what happened;
switch it to a transform.

**Two `<img>` nodes with the same src, start and duration raise
`duplicate_media_discovery_risk`.** If the same asset is needed twice — a faint whole and
a bright clipped copy — paint one of them as a CSS `background-image`. Same URL, so the
browser shares one decode, and only one media node exists.

**A heavy embedded raster defeats the renderer's static-frame dedup while it moves.**
Reuse fell from 97% on a held frame to 20% during a reveal. It costs capture time, not
correctness — do not downscale a 7.5 MB asset on suspicion.

## GSAP traps that pass every check

**A `fromTo` whose from-state is visible applies it at build time.** `immediateRender`
defaults to true, so an orange glow written as a from-state sits on the element from
frame one. It appears to work only because HyperFrames seeks per frame and a seek reverts
pre-start tweens — luck, not design. Pass `immediateRender: false`.

**A wrapper at `opacity: 0` hides its children whatever their own opacity is** — and
passes every contrast check, because the text is in the DOM. Put the reveal class on the
word spans themselves, never on a group above them.

**Chained `to()` tweens on one property want a `tl.set` anchor at t=0.** Three steps on
one `height` otherwise let a non-linear seek inherit whatever a previous seek left.

**`power2.out` on a fade spends 75% of the alpha in the first half** — an 0.8s flash is
effectively over in 0.3s. Use `power1.out` for anything meant to be *seen* fading.

**A `box-shadow` with zero blur is a solid band with a hard outer edge.** A spread-only
pulse reads as a focus ring for its first frames. Blur at both ends of the tween. Only
visible in a 1:1 crop, never in a full frame.

## Composing a card around somebody else's graphic

**Namespace the wrapper's CSS or it reaches into the graphic.** A graphic written from
the same reference as the cover uses the same class names — `.fit`, `.sub` — so the
cover's `.fit { transform: scale(1.42) }` also matched the graphic's own stack and blew
it up by 42% until its icons hung off both edges. Nothing in `check` notices: contrast,
layout and motion all pass on a frame whose content is 42% too big. Scope every rule the
wrapper adds under the wrapper's own clip id.

**A parked element flies invisibly.** Sliding a graphic up from below the frame on your
own schedule wastes the movement if the graphic sets its own opacity or crop later — the
travel is spent before anything can be seen. Read the graphic's first non-headline beat
out of its timeline and align the arrival to land exactly there.

**Shift a borrowed timeline with a child, never by rewriting positions.** Put the lifted
statements on `var g = gsap.timeline()` and `tl.add(g, delay)`. The internal tuning — an
ease across a crop, the pitch of a stagger — survives untouched, and there is no
arithmetic to get wrong.

**Splitting a timeline into statements: count brackets, but skip comments and strings.**
A bracket inside a `//` comment throws the depth off and cuts a tween in half, and the
resulting syntax error quotes the comment's own words back at you. Line-based splitting
on a trailing number fails differently — the builders wrap long tweens across four
lines, so it matched four statements of thirteen in one project and none in another.

**A borrowed headline carries the wrong stagger.** Each graphic tuned its headline to
its own duration; the spoken line is usually twice as long, so the words appear at twice
the speed they are said. Discard the graphic's headline statements and write them from
the measured take.

**Audio first has exactly one exception, and it is this.** A graphic tuned by hand to a
duration is a finished thing; refitting it to whatever length a voice came out is
throwing that away. Let slide 1 last the longer of the two and let the graphic hold —
but then give the ground a breath spanning the whole card, or the tail is a genuinely
frozen frame. Everywhere else, the audio still leads.


## Two more, from wiring nine cards

**Do not fade text out — slide it out.** A 0.30s cross-fade at the end of slide 1 puts
the headline at partial opacity, and if a contrast sample lands inside that window the
card fails WCAG. It is luck: the identical fade passed on two sibling cards and failed on
the third. A transform exit never lowers anything's contrast, and the opacity can be
killed hard on the clip boundary, where nothing is measured.

**Finding a borrowed graphic's first beat: skip `tl.set` and skip the ground.** To land a
fly-up exactly where the graphic's own entrance begins you need that time out of its
timeline — but `tl.set` is state initialisation, and the ground's `#glow` breath sits at 0
and spans the whole film. Taking the minimum across all statements finds a 0, the graphic
gets pushed a second and a half late, and the frame sits empty while the voice is already
talking. Match on the stage element's own id, among `to`/`fromTo` only.


## Found on a launch film (2026-09-27)

**Never return a GSAP timeline from Playwright `evaluate`.** `seek()` returns the
timeline; Playwright tries to serialise it with every child tween and DOM target, and on
~150 statements it never finishes. It looks exactly like an infinite loop in the page,
and a bisection run on it lies. Write `window.__timelines.main.seek(t, false), 0` - or
use `hyperframes snapshot --at`.

**A `tl.set` at exactly 0 does not render while the playhead sits at 0.** Initial states
(hidden scenes, the first scene visible, a cursor's start position) go in CSS; `lint`
reports this as `gsap_timeline_set_initial_hide`.

**A `fromTo` with `immediateRender:false` shows the element's NATURAL state until it
starts.** Staggered rows were all visible a second before their entrances. Hide them in
CSS and let the tween bring them in.

**An `<img>` with width/height attributes under CSS `width:100%` keeps the attribute
height** - the cover rendered 872×600 instead of 872×436 and was read as "pixelated".
Give it `height:auto`. Only a 1:1 zoom shows this; a contact sheet does not.

**Content scrolled under a caption band is reported as `content_overlap`** even when the
window's `overflow:hidden` clips it. Mark the scroller `data-layout-allow-overlap="true"`.

**Fonts are remapped by the renderer** (`Segoe UI` → Roboto, `Helvetica` → Inter, `Menlo`
→ JetBrains Mono). `-apple-system` and local `@font-face` files survive; check a still if
a product's UI font matters.

**`-q high` is ~3.8 Mbit/s.** Master with `--crf 10`, encode the deliverable once.

## Found by the first independent review (a speech-product promo, 2026-10-09)

**`clip-path: inset(...%)` on an SVG `<path>` measures the percent against the path's own
bounding box, not the `viewBox`.** A waveform revealed with `inset(0 100% 0 0) → inset(0 0 0 0)`
over the call's length, in a 1520-wide viewBox, ran at 0.67× real time because the Spanish path
ended at x=1015 (the English at 0.95×); the customer's wave kept "playing" 4 s after the
"stopped talking" mark while the playhead (moved in px) was right. Reveal in px: animate a
`<clipPath><rect>` width, clip a wrapper of the full width, or give the path a full-width
invisible point. Seen only by comparing the fill edge with the playhead on one frame.

## Found on a camera-moves test reel (2026-10-14)

**Never show an element with `visibility: visible`.** The runtime hides a finished clip with
`visibility: hidden`, and an explicit `visible` on a child beats the inherited value: the
child keeps rendering in every later scene. Most of it stays covered by the later scenes'
opaque grounds, so nothing looks wrong until a z-indexed child leaks: a match-cut scrim
(z-index 30) from scene 18 sat over scenes 21-24 as a grey wash with a hole. To toggle an
element, set `visibility` to `"hidden"` or `""` (inherit), never `"visible"`.

**One pure render function is a clean way to drive a camera.** A single linear driver
tween (`tl.to(clock, {t: END, ease: "none", onUpdate: () => render(clock.t)})`) plus
`render(0)` at load; `render(t)` finds the active scene and writes every transform from
`t` alone. Story time (slow motion, speed ramp, freeze) is then one curve per scene that
both the picture and the film's audio script read. Module: `../video-moves/scripts/camera-kit.js`; the build
manual is `../video-moves/references/rigs.md`.

**`data-layout-allow-overlap` must sit on the text element itself** (the `span`, the line
`div`), not on a wrapper: on a wrapper `check` kept reporting chips in front of the
transcript and a scrolling column under its bubble.

**SVG `clipPath` ids repeated across scenes resolve to the FIRST element with that id**,
which may sit in a hidden scene: the Spanish flags rendered empty in the language picker.
Use CSS shapes or unique ids.

**A 2D or 3D camera on a raster screenshot needs material around it.** The plate ends at
its edge; a tilt or pan past it shows the scene ground. Capture more than the frame: on the
test reel a full-window screenshot (2462x1591 at plate scale) kept the toolbar and every
participant tile whole, so a pan or tilt could travel inside the material.

## Real footage (`<video>`), measured on 0.8.157 (2026-10-14)

nanoclip-cutting-room's frame laws (verified on 0.8.3/0.8.4), re-measured with clips whose
every frame carries its source frame number: a 24 fps Seedance shot with 8 cuts, 25 fps
OmniHuman, 29.97 fps over 69 s, VFR, and a clip with dropped frames, in a test project.
Helper: `scripts/footage_proxy.py`.

**What the engine already does.** At render every `<video>` is decoded by ffmpeg and
resampled to the render fps by timestamp: frame k shows the source frame on screen at
`data-media-start + (k/30 - data-start)`. 24, 25, 29.97, VFR and dropped-frame clips rendered
straight matched that on every frame (0 of 4,077 off, no drift after 69 s of 29.97). Windows
are half-open, `[start, start + duration)`. So a 30 fps proxy is no longer needed for a
correct render; the rules below are what still breaks.

**Write every time as an exact double, never rounded.** `data-start`, `data-duration` and
`data-media-start` are `frame / 30` in shortest round-trip form (Python `repr(31/30)` and JS
`String(31/30)` both give `1.0333333333333334`). A rounded edge sits off the sample grid; the
engine snaps visibility onto the grid but runs the clip's media clock from the unsnapped
value. Measured on 13 edges: 4 decimals gave a black frame at 3, a duplicated first frame at
4, and a media start rounded down showed the frame before the in-point for the whole window;
2 decimals gave 6 black frames; exact doubles, 0 of 440 frames off.

**Take in-points and cut times from the file you render, in that file's own time.** On the
raw clip: the frame's exact pts (pts x time_base). On a proxy: proxy frame / 30. Never move a
24 fps frame onto the 30 grid, and never carry a cut list from one file to another. On the
Seedance shot, in-points rounded to the 30 grid opened one shot with a frame of the previous
shot (cut 305 = 381.25 frames -> 12.7 s),
and the proxy's cut list applied to the raw file did the same; exact pts on the raw file and
the proxy's own cuts on the proxy were clean at 8 of 8 cuts.

**Make a proxy when it earns its place, with `scripts/footage_proxy.py`.** It resamples the
way the engine does (proxy frame k == rendered frame k: 0 of 2,240 frames off on 29.97, VFR,
25 fps and dropped-frame clips), re-detects cuts on the proxy, puts a keyframe every second and
prints the window attributes. Worth it for VFR screen recordings (re-normalised on every
render), sparse keyframes (OmniHuman exports have one per 10 s: the render stays exact, but
render warns and the live player seeks slowly), and long footage cut into many windows. Do not
reuse nanoclip's `fps=30` chain as is: it rounds to the nearest frame and shows frames up to
half a frame early, so its cuts are one frame off a raw render at some cuts (381 vs 382).

**In the live player, hold every video on its first frame until its window opens.** A render
never shows a stale frame. `hyperframes play` without priming: 9 of 13 window openings showed
the file's frame 0 for 1-4 display frames (17-67 ms) on first play, 8 of 13 showed the previous
pass's frame on replay. With the snippet below: no stale frame at 52 openings (two runs, play
and replay), and the render is unchanged (0 of 440). It needs a numeric `data-start` and the
registered timeline spanning the film (`tl.set({}, {}, END)`); paste it after the media:

```html
<script>
  // Live player only: hold every <video> on its first frame until its window opens.
  (function () {
    var root = document.querySelector('[data-composition-id]');
    var vids = [].slice.call(document.querySelectorAll('video[data-media-start]'));
    function tick() {
      var tl = window.__timelines && window.__timelines[root.dataset.compositionId];
      var t = tl && typeof tl.time === 'function' ? tl.time() : null;
      for (var i = 0; i < vids.length; i++) {
        var v = vids[i], ms = parseFloat(v.dataset.mediaStart), start = parseFloat(v.dataset.start);
        if (t != null && t <= start + 0.001 && v.paused && !v.seeking && v.readyState >= 1 &&
            Math.abs(v.currentTime - ms) > 0.001) {
          try { v.currentTime = ms; } catch (e) {}
        }
      }
      requestAnimationFrame(tick);
    }
    requestAnimationFrame(tick);
  })();
</script>
```

**Quarter-frame starts and tails are optional player polish.** Exact contiguous windows never
left a hole in the player (no sample without a visible video); a cut sometimes lands one display
frame late on replay. nanoclip's windows (start `(f - 0.25)/30`, a 2-frame tail under the next
shot on an alternating track, media start exact) remove that and render identically (0 of 440),
at the cost of alternating tracks and z-order. A render does not need them.

**Never time a `<video>` inside a timed wrapper.** lint reports
`video_nested_in_timed_element` and `check` fails, but `render` does not stop: the nested video
played from composition time 0 over the first shot and its own window rendered black (62 of 94
frames wrong). Time the video itself; wrap it in an untimed div for a frame or a crop.

**`class="clip"` on a `<video>` is harmless now.** nanoclip's rule against it no longer
measures: lint and check pass, render 94 of 94 correct, player clean.

**`data-has-audio="true"` on a file without an audio stream fails the render** at compile:
"composition asset(s) do not match their authored media element type (expected: audio)". Stabilised
or re-encoded OmniHuman files are often silent; ffprobe before declaring sound.

**A video's own sound is sample-exact.** It starts at `data-start` from `data-media-start`
(cross-correlation with the source: 0.00 ms offset, r = 1.000, also through the proxy) at the
source level per channel. A mono source comes out as dual-mono stereo, so a mono downmix of
the render reads 3 dB hotter than the source: a measuring artefact, not gain.

**Scene-cut threshold 0.12 is for camera and generated footage.** Seedance cuts score
0.81-0.87, the highest non-cut 0.07; a UI recording gave 19 "cuts" in 13 s at 0.12 and 2 at
0.3. Use `--threshold 0.3` on screen recordings; `--split` never makes a shot under 8 frames.

**Two tweens on one property still disagree between render and snapshot; lint now says so.**
0.8.157 warns `overlapping_gsap_tweens`. A 0-to-1 opacity rise over 1 s with a revert starting
at 0.5 s: at 0.6 s the render showed 0.25 (the revert started from the value it met at 0.5),
`snapshot --at 0.6` showed 0.30. End the rise before the revert starts, and check overlay motion
on rendered frames.

**A Google Fonts `<link>` is not flagged on 0.8.157** (nanoclip saw `google_fonts_import` on
0.8.4). The scaffold's link stays.
