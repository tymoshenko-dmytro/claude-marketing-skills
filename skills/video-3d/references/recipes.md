# Recipes

Proven kinds of 3D scene, each proven by a private test film (named by the labels in the legend of
`capabilities.md`), and the pieces worth building or lifting. The test films do not ship; their lessons and
numbers are here. The techniques are universal - fill them with the film's own assets and palette.
Reusable code lives in `assets/recipes/<name>/` (a README in each). Everything else three.js can do for a
film, with a status per item: `capabilities.md`.

The first four are finished film looks; the seven after them are capability reels (one capability per
section, hard cuts) - lift a section, not the reel.

## Object (solids, logos, props)

Status: proven. Example: the logo film, an 11 s logo reveal: the mark extruded from its
real SVG, orbit close to show side walls and bevels, pull back and land in the official lock-up,
wordmark slides out from behind it, 3% push-in hold.

- Geometry from the real vector (one helper, e.g. `buildPiece(path)`): SVG path → `ExtrudeGeometry` with
  `bevelOffset = -bevelSize` (silhouette stays exact), `scale(K, -K, -K)` (flips SVG y without
  inverting the winding), `toCreasedNormals`. A gradient from the SVG → vertex colours.
- Light: `RoomEnvironment` through PMREM (`environmentIntensity` ~0.55), clearcoat for gloss; a
  per-frame contact shadow (`capabilities.md` 4.3), with text planes hidden from its depth pass.
- Landing an object at a given screen position and size: the lock-up solve in `capabilities.md` 1.5 -
  solve in camera space, do not tween in screen space.
- Text that lands with it: the wordmark SVG drawn at 4096 px into a `CanvasTexture` on a plane, revealed
  by a clipping plane at the object's edge.
- Opens: 3D end cards and logo stings; icons and props from the real identity as objects; UI as
  thin rounded slabs with a screenshot texture (render the texture at 2x its largest size); 3D
  kinetic type from font outlines; material variants (glass `transmission`, brushed metal).
- Since proven in the reels: rack focus (post reel), a light bar sliding over a product (RectAreaLight,
  materials reel), glass and brushed-metal variants (materials reel), a device with a live screen
  (camera-text reel).

## Data in space (globes, maps, networks)

Status: proven. Example: the globe film, 11 s: a 15k-dot globe, arcs drawn
city to city with a glowing head, a ripple and a label at each landing, the camera following the
arcs then pulling back, a 1.5°/s drift on the hold (0.6°/s read as frozen).

- Bake the data in Node (a land-dot script you write; the TopoJSON decode is in
  `assets/recipes/data/build-map.mjs`): antimeridian-safe rasterising (unwrap ring
  longitudes, close pole-wrapping rings, even-odd per ring, cells modulo 360), Fibonacci sampling.
- Shaders to lift: analytic anti-aliased instanced dots with a heat input (landing pulses);
  draw-on tube (`discard` past `uHead`, white head glow); back-face atmosphere with a soft edge
  (alpha 0 at its own silhouette rising to the limb); half-Lambert body with dither.
- A label layer: project each anchor every frame, fade by facing (hidden behind the horizon),
  place to a side with a gap and an SVG leader line, pop in on landing.
- Spherical camera rig: `lat, lon, dist, roll`; in-out cubic orbit, `logLerp` distance, constant
  drift for holds.
- Plan the order and the camera path together against the real geography: some places cannot
  share a frame (São Paulo and Tokyo sit on opposite sides).
- Opens: reach and network maps (languages, users, offices, call routes), bars or spikes from
  cities, data as terrain to fly over, spatial walkthroughs with true occlusion.

## Particles and shaders (counts, morphs, grounds)

Status: proven. Example: the particles film, 12 s: 64k particles form strands driven by a real voice's
20 ms RMS (from an offline analysis script), lift off on helix paths, form "Hola", re-form as "Hello"; a
story-time slow-motion beat at the morph peak with the camera still orbiting.

- Position = f(story time, per-particle attributes) in the vertex shader; attributes from one
  seeded PRNG; nothing carried between frames.
- Text → points: draw the word on an offscreen canvas, rejection-sample by alpha with a seeded PRNG,
  then sort by x so particle i keeps its left-to-right rank across shapes - morphs read left to
  right.
- A narrow flight band (`dur / stag ≈ 0.45`) so a frame holds finished letters, the cloud in
  flight and the source at once; strong bokeh on many points makes mush (keep CoC small).
- Passes: splats (ONE/ONE, HalfFloat) → glow at 1/4 resolution → composite (ground mixed from two
  tokens, hue-preserving tone map, coverage occlusion, dither after `toSRGB`).
- Cost: 2.5-4.4 ms of GPU per frame at 64k; the screenshot dominates - 500k should be affordable.
- Opens: voice → text → translation as one object; logo assembles from what came before; data as
  dots that re-sort into a number or a map; bullet-time (freeze the world in story time, move the
  camera in real time); shader grounds under any UI film.

## ASCII cinema (a 3D scene as monospace glyphs)

Status: proven. Example: the ASCII film, 11 s: a camera flies down a contour-lined valley on a
CatmullRomCurve3 rail to a turning torus knot, all as 160 x 45 glyphs; the field forms a big word cell by
cell, and a caption decodes into readable text. 4-worker and 1-worker renders identical; also the first
film through `EffectComposer`. Reusable code and wiring: `assets/recipes/ascii/` (`ascii-pass.js`,
`README.md`, `ascii_shimmer.py`).

- Pipeline: `RenderPass` → (bloom etc.) → `OutputPass` → `AsciiPass`. The pass reads display
  values and writes the film's palette exactly; `composer.render(0)`.
- Glyph atlas from a monospace font, built ONCE after `await FontFace.load()`, cell = the font's
  advance x a line (JetBrains Mono 20 px = 12 x 24), copied 1:1 (`NearestFilter`, pixel ratio 1).
  The cell must divide the frame; the grid never moves, content moves through it.
- Anti-shimmer, measured: an EXACT box average per cell (not a centre sample: -25% hold jitter)
  and a narrow crossfade band around each ramp step (not a hard switch: -27% hold jitter).
- The ramp is sorted by MEASURED ink in the font. Symbols (`RAMP_CLASSIC` " .:-=+*#%@") read as
  picture; letters read as scrambled text.
- Edge glyphs `| / - \` from a Sobel on the cell grid (angle corrected for non-square cells) draw
  contours; saturated scene colours keep their hue (`uSceneColor`), greys take the palette.
- Words: a shape mask the field forms (big type or a logo, keyed left to right with seeded jitter)
  and text cells that scramble then settle (integer hash, steps from the frame index; identical on
  GPU and SwiftShader). Feathered quiet zones dim the scene behind words.
- Light for glyphs: read the cells target's luminance quantiles (median ~0.3, deep blacks) before
  judging; a normally lit scene fills every cell. Flat surfaces need structure (contour lines).
- Motion: content crossing more than ~1 cell per frame strobes (no motion blur in glyphs).
- QA: `ascii_shimmer.py` on a PNG sequence (blips and jitter per span), 1:1 crops of consecutive frames.
- Opens: title and end cards that resolve out of a scene; data or terrain flights in a terminal
  look; a product object in glyphs; captions that decode; any recipe above run through the pass
  (the globe or the particles as characters).

## Rendered looks (toon, outlines, print, dither, CRT, pixel art, ink)

Status: proven. Example: the styles reel (44 s, 11 looks over one still life and one camera move). Code:
`assets/recipes/looks/` (`looks.js`: `FilmPixelPass`, `HullRenderPass`, `SobelInkPass`, `DitherPass`,
`CrtPass`, `InkPaperPass`, `InvertPass`, `WipeQuad`; chains per look in the README).

- One composer at pixel ratio 2; every grid pass works in film pixels; stock passes fixed to film pixels.
- A look per shot: a prebuilt pass list per look swapped in each frame; a look change inside a shot = both
  looks rendered, mixed by an edge from t.
- Ink and paper: tones from a key-light-only render, boil stepped every 3 frames, static seeded paper.
- QA: `look_shimmer.py` + `ascii_shimmer.py`; judge hard-threshold looks by A-B-A blips.
- Opens: a whole film in a print or terminal look; a look switch as a transition; product objects in toon
  with constant-width outlines.

## Post chain (AO, depth of field, AA, grain, grades, LUT, glitch, SSR, motion blur)

Status: proven. Example: the post reel (44.5 s, one scene, a section per pass, wipes and 1:1 tiles). Code:
`assets/recipes/post/` (`post-kit.js`: `withSeed`, `hash01`, `whenImagesReady`, `SubframeMotionBlurPass`,
`Presenter`, `glitchSchedule`; chain, settings and ms per pass in the README).

- Seeded construction for SSAO/GTAO; FilmPass time = a hash of the frame; Vignette ramps `offset`;
  LUTs as `FloatType`; SSR without bouncing, with an MSAA beauty target.
- Rack focus = view depth of the subject lerped from t (BokehPass ladders thin bright lines).
- Motion blur = 16 sub-frames inside the shutter (32 ms per frame) - the only seek-safe blur.
- Opens: a grade per film from its own .cube; real rack focus; contact AO under products; glitch accents
  on cuts; reflections on a glossy floor.

## Materials and light (vessels, physical materials, shadows, HDRI, baked AO, sky)

Status: proven. Example: the materials reel (50.5 s, one lathe vase on a plinth, the same arc per section).
Code: `assets/recipes/materials/` (`lathe.js`, `ao-bake.js`; shadow-type switch, ShadowMesh sign, HDRI sun
in the README).

- Glass, iridescence, sheen, anisotropy, matcap, toon on one hero; what each does to a known colour
  (orange albedo `#e0893c`, ΔE2000 of the rendered patch to the albedo): matcap 1.5, HDRI-lit 1.8, plain
  lit 2.6, planar shadow 3.7, baked AO 4.9, toon 6.5, area light 16.2, glass 19.7 (lighter, +16° hue),
  anisotropy 29.0, sheen 33.9 (both darker, hue held), iridescence 45.9 (+102° hue). On the same lit frame
  Neutral tone mapping moved it 3.5 from no tone mapping, ACES 8.9, AgX 9.6.
- Split frames (two renderer set-ups per frame, scissored) to compare light set-ups side by side.
- Baked AO on `uv1` faded in from t; light probes baked at keys and lerped; procedural lens flare that
  geometry occludes.
- Opens: product heroes with real glass and metal; a light bar sliding over a product; a sunset over an
  object; any baked lighting without Blender.

## Models and baked simulations

Status: proven. Example: the models reel (46.5 s, a downloaded robot model on a stage: decoders, skinned
clones, mixer blends, procedural bones, morphs, rigid bodies, cloth, flock, Flow ribbon, surface points).
Code: `assets/recipes/models/` (`rig.js`: seek-safe mixer and bone aim; `baked-playback.js`: rigid bodies
and VAT cloth); the bakes are Node scripts you write (formats in the `baked-playback.js` header, settings
and costs in the README).

- Every clip time and weight from t, `mixer.update(0)`, undo list for procedural writes.
- Physics, cloth and flocks simulated in Node with a fixed dt, shipped as files, read by frame.
- Proven only by the seek-order test, not by worker renders (the first version was wrong in all three).
- Opens: characters and mascots acting to a script; product drops and falls; fabric reveals; flocks of
  icons; a model dissolving into points.

## Screens and compositing (cameras, 3D text, lines, screens, footage, alpha)

Status: proven. Example: the camera-text reel (47.2 s: ortho, dolly zoom, handheld + shake, cuts in one
canvas, TextGeometry, troika, Line2, a live canvas screen, monitor/mirror/portal, an image sequence on a
screen, GSAP DOM over the canvas, a sub-composition over footage, alpha export). Code:
`assets/recipes/compositing/` (`host-start.js`, sub-composition and alpha wiring).

- A device with a real screen: a canvas redrawn from t, a render target from a second camera, or an image
  sequence indexed by frame.
- Cuts and sections chosen on integer frames; each section owns its scene and camera.
- A 3D layer rendered alone with alpha (`-c layer.html --format webm`) and composited elsewhere.
- Opens: UI walkthroughs on a 3D device; product films with footage plates; 3D titles with any font;
  vertigo moves on a subject.

## Data maps, graphs and terrain

Status: proven. Example: the data reel (41 s: bars and spikes, an extruded country choropleth, a
force-directed network, a spectrogram terrain, audio bands and onsets, 8k instanced shards, BatchedMesh,
GPGPU replay vs bake). Code: `assets/recipes/data/` (`build-map.mjs`, `gpgpu.js`; bars, labels, borders,
network, audio snippets in the README).

- Bake data in Node (maps, layouts, audio features); the page reads it at t.
- Maps: per-arc simplification, outlying islands dropped, borders on the extruded tops.
- Labels fade by ray occlusion; cameras checked against the data every frame in the build.
- GPU state: replay per seek up to ~1-2 min of sim per shot, or bake into array layers (memory-bound).
- Opens: market and reach maps; growth bars; graph explainers; a track or a voice as a landscape;
  equaliser looks that follow the actual sound.

## WebGPU counts (compute, atomic density)

Status: proven. Example: the WebGPU reel (42 s on `WebGPURenderer`: TSL material, node post, 2M compute
particles, 16M points by `atomicAdd`, WebGL vs WebGPU split). Code: `assets/recipes/webgpu/`
(`webgpu-film.js`: film clock, backend check, seek driver with the node frame, atomic density splat).

- Choose it only for counts WebGL cannot draw: density, X-ray or nebula looks from millions of points.
- Required: `data-requires-webgpu`, backend check, a node frame per seek, TSL time = film time, GPU render.
- Opens: a voice or a dataset as a cloud of millions of points; X-ray views of a product; nebula grounds.

## Not covered

What was never rendered is listed in the legend of `capabilities.md`; probe it before promising it.
The reels ran on the GPU path; on SwiftShader (`--no-browser-gpu`) only the data reel's GPGPU,
BatchedMesh and d3-force were checked.
