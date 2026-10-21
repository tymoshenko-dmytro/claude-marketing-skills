# Rigs: how a move is built in HyperFrames

The manual for the code: section 0 is a complete two-scene film that builds and renders with
the skill's files as they are; sections 1-7 explain each piece and give the snippet for every
rig. The numbers for each move are in `moves.md`. Read video-build's
`references/hyperframes-gotchas.md` too; the traps found while building the 24 moves are in its
section "Found on a camera-moves test reel".

## 0. A minimal film (one scene per rig)

A 2D pan between two cards (3 s), a 3-frame dip, then a 3D dolly in on a subject with a far
wall behind and two props near the lens (3 s). It uses `assets/scaffold.js` unchanged: its
example `IMPL.pan` and `IMPL.dolly` drive the two scenes. Tested on hyperframes 0.8.157
(`check` passes; stills at 0.2 / 2.9 / 3.2 / 5.9 s show the pan landing on "Second", the props
leaving the frame and the subject at x1.7 while the wall grows less).

```
mv-example/
  hyperframes.json          from video-build references/scaffold.md
  build.py                  below
  vendor/camera-kit.js      copied from scripts/
  vendor/moves.css          copied from assets/
  vendor/scaffold.js        copied from assets/
```

```python
"""Minimal video-moves film: a 2D pan, then a 3D dolly in. Uses vendor/scaffold.js as it is."""
import json, pathlib
HERE = pathlib.Path(__file__).parent
V = HERE / "vendor"                      # camera-kit.js, moves.css, scaffold.js copied from the skill
W, H = 1920, 1080

SCENES = [{"id": "s1", "impl": "pan", "dur": 3.0},      # scaffold IMPL.pan: cx 600 -> 1300 at zoom 1.5
          {"id": "s2", "impl": "dolly", "dur": 3.0}]    # scaffold IMPL.dolly: P 1880 -> 1100
t = 0.0
for s in SCENES:
    s["start"] = round(t, 3); t += s["dur"]
END = round(t, 3)

def card(text, x, y, z=None, w=420, h=300, cls="card"):
    tz = f"transform:translateZ({z}px);" if z is not None else ""
    return (f'<div class="l3 {cls}" style="left:{x}px;top:{y}px;width:{w}px;height:{h}px;{tz}">'
            f'<span>{text}</span></div>')

HTML = {
    # 2D lens: the world is wider than what the lens shows; both subjects sit inside the plate
    "s1": ('<div class="lens" data-layout-allow-overflow><div class="plate"></div>'
           + card("First", 390, 390) + card("Second", 1090, 390) + '</div>'),
    # CSS 3D world: a far wall, the subject at z=0, two props near the lens (moves.md 03)
    "s2": ('<div class="stage" style="perspective:1880px"><div class="world" data-layout-allow-overflow>'
           '<div class="l3 plate" style="left:-920px;top:-520px;width:3760px;height:2120px;'
           'transform:translateZ(-1800px)"></div>'
           + card("Subject", 750, 390)
           + card("Prop", 380, 300, z=700, w=220, h=120, cls="card prop")
           + card("Prop", 1350, 640, z=800, w=220, h=120, cls="card prop")
           + '</div></div>'),
}

CSS = """
html, body { margin: 0; width: 1920px; height: 1080px; overflow: hidden; background: #111316; }
body { font-family: "Inter", Arial, sans-serif; }
#root { position: relative; width: 100%; height: 100%; overflow: hidden; }
.plate { position: absolute; left: -400px; top: -300px; width: 2720px; height: 1680px;
  background: #1D2128 repeating-linear-gradient(90deg, #2A3039 0 4px, transparent 4px 160px); }
.card { display: flex; align-items: center; justify-content: center; background: #FFFFFF;
  color: var(--mv-ink); font-size: 64px; font-weight: 700; border-radius: 24px; }
.prop { font-size: 40px; }
"""

def page():
    body = "\n".join(
        f'<div id="{s["id"]}" class="clip scene" data-start="{s["start"]}" data-duration="{s["dur"]}" '
        f'data-track-index="0" data-layout-allow-overlap>{HTML[s["id"]]}</div>' for s in SCENES)
    meta = [{k: s[k] for k in ("id", "impl", "start", "dur")} for s in SCENES]
    return f'''<!doctype html>
<html lang="en" data-resolution="landscape">
  <head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width={W}, height={H}" />
    <link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Inter:wght@400;700&display=swap" />
    <script src="https://cdn.jsdelivr.net/npm/gsap@3.14.2/dist/gsap.min.js"></script>
    <style>{(V / "moves.css").read_text()}{CSS}</style>
  </head>
  <body>
    <div id="root" data-composition-id="main" data-start="0" data-duration="{END}" data-width="{W}" data-height="{H}">
{body}
    <div id="dip" class="clip" data-start="0" data-duration="{END}" data-track-index="1"></div>
    </div>
    <script>
{(V / "camera-kit.js").read_text()}
const SCENES = {json.dumps(meta)};
const END = {END};
const ENV = [];
{(V / "scaffold.js").read_text()}
    </script>
  </body>
</html>
'''

(HERE / "index.html").write_text(page())
(HERE / "scenes.json").write_text(json.dumps({"total": END, "scenes": [
    {"start": s["start"], "dur": s["dur"], "in": "cut" if i == 0 else "dip:3"} for i, s in enumerate(SCENES)]}, indent=1))
print(f"{len(SCENES)} scenes, {END} s -> index.html, scenes.json")
```

```bash
python3 build.py
npx --yes hyperframes@0.8.157 check
npx --yes hyperframes@0.8.157 snapshot --at 0.2,2.9,3.2,5.9 --no-end -o snaps
```

To make it a real film: replace the cards with the film's material (a captured UI, an
illustration, footage), add an `IMPL` per scene with that material's world coordinates (start
from the entry in `moves.md`), and set the `--mv-*` tokens from the film's palette in the film's
CSS after `moves.css`. `check` reports text under `#dip` at the exact scene boundary; that is
the dip doing its job.

## 1. Frame = f(t)

- Each scene is a HyperFrames clip: `<div id="s07" class="clip scene" data-start
  data-duration data-track-index="0" data-layout-allow-overlap>`. The runtime hides
  finished clips.
- One paused GSAP timeline with ONE linear driver tween; `render(t)` runs every scene's
  `frame(u)` for the active scene (`u = t - start`). Copy `assets/scaffold.js`.

```js
const clock = { t: 0 };
const tl = gsap.timeline({ paused: true });
tl.to(clock, { t: END, duration: END, ease: "none", onUpdate: () => render(clock.t) }, 0);
render(0);                                  // the first frame before any seek
window.__timelines["main"] = tl;
```

- `IMPL[id] = (root, scene) => ({ frame(u) {...} })` - query elements once in the
  factory, write styles in `frame`. Never read layout (`getBoundingClientRect`) per frame:
  HyperFrames samples frames in parallel workers.
- Randomness only from `CK.rng(seed)`; shake held per step (`CK.shake`).
- **Toggle with `show(el, on)` = `visibility: on ? "" : "hidden"`.** Setting `"visible"`
  overrides the runtime's hidden clip and leaks the element into later scenes.
- A sequence of separate demos (or any montage where a scene change must not read as a
  cut inside a move): a full-frame `#dip` clip on its own track, opacity
  `1 - |t - boundary| / 0.1` → 3 frames out, 3 in.

## 2. 2D lens - pan, tilt, zoom, roll, shake, whip

The world is laid out in px; `.lens` (`transform-origin: 0 0`, 1920x1080) holds it.

```js
CK.lens2d(lensEl, { cx, cy, zoom, roll, dx, dy });
// = translate(W/2+dx, H/2+dy) rotate(roll) scale(zoom) translate(-cx, -cy)
```

- `(cx, cy)` is the world point at the centre of the frame. Pan = move cx, tilt = move
  cy, zoom = `logLerp` the zoom, roll = dutch, `dx/dy/roll` from `CK.handheld` (degrees →
  px with `CK.pxPerDeg()`) or `CK.shake`.
- Everything moves together - no parallax. That is correct for pan, tilt and zoom and
  wrong for anything that travels.
- Visible world rect: `cx ± 960/zoom`, `cy ± 540/zoom`. Check it against the material's
  edges and against name tags before you pick numbers.

## 3. CSS 3D world - dolly, orbit, crane, tracking, FPV, dolly zoom, rack focus

```html
<div class="stage" style="perspective:1880px">      <!-- the lens: perspective = focal length -->
  <div class="world" data-layout-allow-overflow>    <!-- preserve-3d; the camera moves THIS -->
    <div class="l3" style="left:0;top:0;width:1920px;height:1080px;transform:translateZ(-1800px)">wall</div>
    <div class="l3" style="left:358px;top:200px;transform:translateZ(0px)">subject</div>
    <div class="l3 prop" style="left:..;top:..;transform:translateZ(700px)">chip</div>
  </div>
</div>
```

```js
CK.pose3d(worldEl, { x, y, z, rx, ry, rz });   // translate3d OUTSIDE the rotations
```

- `perspective: P` makes the z=0 plane project at scale 1. A layer at depth z projects at
  `P / (P - z)`, positioned `960 + (X - 960) * P/(P - z)`. To place a prop at a screen
  point (sx, sy) at rest: `X = 960 + (sx - 960)(P - z)/P`.
- `P = CK.perspOf(mm)`; 24 mm ≈ 1880 px on 1080 p (32° vertical).
- **Dolly**: world `z` up = camera in. Interpolate the camera DISTANCE with `logLerp`
  (`z = P - logLerp(P, P_end, k)`).
- **Orbit**: `world.style.transformOrigin = "<subject x> <subject y> 0px"`, animate `ry`.
- **Crane**: animate `rx` (0 → 50°, the far edge tips away) and pull z back.
- **Tracking**: move the subject in world x and the world by `-(subjectX - 960 + offset)`;
  near layers at z>0 race, far layers crawl.
- **Dolly zoom**: subject at z=0, animate the stage's `perspective` (700 → 2600, log); the
  subject never changes size, the background grows `P/(P + depth)`.
- **FPV**: tiles as walls (`translateZ(z) rotateY(±90deg)`), a floor
  (`translateZ(-6000px) rotateX(90deg)`), camera z by `1-(1-x)^2.2`, weave on world x,
  bank as a 2D `rotate()` on the stage, both faded out for the landing.
- **Rack focus**: `filter: blur()` on the LEAF layers only. A `filter`, `opacity < 1`,
  `overflow`, `clip-path` or `mask` on `.world` (preserve-3d) flattens the scene.
- A 2D zoom over a 3D stage = `.lens` wrapping `.stage` (moves.md 04, zoom vs dolly).
- Heavy grids: use half-size images (`*-small.png`) for anything that is never seen large.

## 4. Story time - slow motion, speed ramp, freeze

```js
// per scene in scenes.json: story: { s0: 0.71, segs: [{until:0.9, rate:2}, {until:1.3, to:0.2},
//                                                      {until:2.2, rate:0.2}, {until:2.55, to:2}, {rate:2}] }
const T = CK.makeStoryTime(CK.piecewiseRate(sc.story.segs), { until: sc.dur + 0.1, s0: sc.story.s0 });
const s = T.story(u);           // story seconds; T.rate(u) for a readout or a graph
CK.riseWords(words, s);         // words float into place on story time
scope(s);                       // the voice scope (below)
```

- Everything in the world uses `s`: word reveals, the voice (`move_audio.story_curve`
  reads the same `segs`), a scope, an object's position. The camera and the cut use `u`.
- `{rate: 0}` is a freeze; `{until, to}` eases between rates with smoothstep.
- Something must move continuously in story time or the slowdown reads as a hang. In the
  test reel: the voice scope and rising words (`.w { display: inline-block }` for the rise).

## 5. Transitions - two layers A and B

- **Hard cut / smash / match / J / L**: `show(A, u < cut); show(B, u >= cut)`.
- **Dissolve**: B on top, `opacity = CK.dissolve(u, {start, dur})`.
- **Wipe**: B on top, `clipPath = inset(0 ${W - x}px 0 0)`, `x = CK.wipeX(u, W, ...)`,
  plus a 4 px edge line.
- **Whip**: ONE world with A and B side by side; move the lens across; blur from speed:
  `hblur = min(150, v * 0.03)` (v in px/s, numeric derivative of the lens path), on a
  wrapper with `filter: url(#hb)`, `<feGaussianBlur stdDeviation="${hblur/3} 0">`.
  Switch the filter off when blur < 0.5.
- **Match cut ground**: if A and B differ in brightness, put a scrim on B with a hole that
  follows the matched shape (`radial-gradient(circle at x y, transparent 0 r-1, dark r+2)`,
  x/y/r from the lens transform) and lift it after the cut.
- **Jump cut**: N states in one locked frame, `CK.jumpIndex(u - t0, N, step)`; states
  must differ in layout.

## 6. Overlays (styles in `assets/moves.css`)

Colours: every overlay uses the `--mv-*` tokens. Set them per film from the colours of the
material being edited (its UI, illustration or footage) in the film's own stylesheet after
`moves.css`; the scope reads them too. No brand is baked in.

- **Label** `.label` bottom-left (accent number ≥ 48 px bold on white, name, muted term) -
  for teaching reels. In: 0.28 s from 0.10 s; out: 0.16 s before the end.
- **Readout pill** `.readout` top-right, tabular digits, one style for speed ("×0,25",
  two decimals) and clock ("10:47").
- **Voice scope** `.scope` with a canvas: bars of the recording's RMS (20 ms bins, 0..1,
  computed at build time) at `x = head - (s - i*0.02) * 300`, playhead in the accent.
- **Edit strip** `.strip` for J/L demos: video and sound tracks, the gap highlighted,
  a playhead; labels ≥ 28 px; on the label's bottom line.
- **Focus brackets** `.focus`, **freeze border** `.freeze` (12 px) - both in the accent.
- Keep the bottom-left label band and the overlays clear of the subject.

## 7. Checks

- `hyperframes check`: put `data-layout-allow-overlap` on the TEXT elements that are meant
  to overlap (a chip over a transcript, a scrolling column), not on a wrapper;
  `duplicate_media_discovery_risk` on repeated grid images is fine.
- Stills at the start, middle and landing of each move and either side of each cut
  (video-check `scripts/stills.py`). Sheets from a rendered file: select frames by number,
  never `fps=N` (it labels tiles 0.233 s early).
- A frozen stretch over 1 s that is not a freeze frame, a card hold or a deliberate pause
  is a dead frame: give it a 2-4% push (cards) or keep the story running.
