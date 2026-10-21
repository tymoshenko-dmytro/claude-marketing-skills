# The HyperFrames + three.js contract

Consolidated from the notes of the private test films (the logo, globe, particles and ASCII films, the
WebGPU probe, and the seven capability reels of 2026-10-14: materials, post, styles, models, camera-text,
data, WebGPU - labels in the `capabilities.md` legend). Upstream reference: `adapters/three.md` in the
`hyperframes-animation` skill (read-only). Where tests disagreed, the reconciled rule is stated.
HyperFrames 0.8.156, three 0.181.2.

## The page

- **Root**: `data-composition-id`, `data-start="0"`, `data-duration="<s>"`, `data-width`,
  `data-height`, and **`data-no-timeline`** when the film has no GSAP layer (without it lint
  errors `missing_timeline_registry` and every render polls 45 s for a timeline). With GSAP DOM layers,
  register the real timeline; lint reads INLINE scripts only, so a timeline built in an external file
  needs an inline `window.__timelines["main"] = window.__mainTimeline;` after it.
- **Build hold** in a CLASSIC inline script in `<head>` (a module script runs too late):
  ```html
  <script>
    window.__hf = window.__hf || {}; window.__hf.buildReady = window.__hf.buildReady || {};
    window.__hf.buildReady.scene = new Promise((res, rej) => { window.__sceneReady = res; window.__sceneFail = rej; });
  </script>
  ```
  Resolve it after fonts, geometry, textures, data, decoders and `renderer.compile()`; then render once at
  `window.__hfThreeTime || 0` (the runtime does not re-dispatch a seek to the same time). A build over 3 s
  makes `check` warn "did not become render-ready within 3000ms" (it still passes); give `snapshot`
  `--timeout 60000`.
- **Warm every section in the build**: render each section (each look, each pass chain) once before the
  hold resolves. Light visibility toggles change program keys, passes allocate lazy targets (SSAA), WebGPU
  compiles pipelines - none of that may happen at seek time.
- **Failures are silent - make them visible.** A rejected build hold does NOT fail the render: HyperFrames
  0.8.156 logs the page error and renders a BLANK film with exit 0 (also with `--no-best-effort`;
  `snapshot` saves a blank frame). An exception inside the `hf-seek` handler leaves the previous frame on
  the canvas while DOM labels move on. So: wrap `renderAt` in try/catch, log to `window.__info.errors` and
  clear to magenta (the skeleton does); WebGPU films add `data-requires-webgpu` on the root (then the CLI
  fails with exit 1); QA looks for blank, magenta and frozen output (`qa-3d.md` step 4).
- **three** from a pinned CDN version (`three@0.181.2`, jsdelivr, an importmap for addons). ESM does not
  set `window.THREE` - the build hold is the wait. Other libraries pinned the same way (troika via esm.sh
  `?external=three`, d3-force, gsap).
- **No runtime fetch at seek time.** Bake data into a JS file, load models, textures, fonts and image
  sequences before resolving the hold. Canvas text needs `await new FontFace(...).load()`.
- The canvas: CSS 1920x1080; `data-layout-allow-overflow="true"` if the scene overfills. Shades and
  gradients behind captions go BELOW every text layer (`text_occluded`); fade projected labels near the
  frame edge.
- **Check the camera path against the geometry in the build** (sample the rail every frame, compare with
  heights or bar tops) and reject the hold if it clips - a camera inside a hill renders a dim, odd frame,
  not an error.
- **Sub-compositions**: `hf-seek` carries ROOT time inside a sub-composition - subtract the `data-start`
  of every `[data-composition-src]` ancestor (`hostStart()`, `assets/recipes/compositing/`). The file must
  start with `<template>`; a standalone `-c` render keeps index.html's `<head>` and only `<script src>`
  body children, so scene code lives in external scripts; `data-no-timeline` goes on the HOST element
  (else a 45 s wait per render).

## Time

- `addEventListener("hf-seek", e => renderAt(e.detail.time))`. No `requestAnimationFrame`, no
  `setAnimationLoop`, no clock. `e.detail.waitUntil(promise)` exists and the capture awaits it (used for
  WebGPU's `onSubmittedWorkDone()`).
- **Every visual state is set absolutely from t** - camera, uniforms, visibility, label positions, clip
  times. Nothing is incremented or carried between frames: workers seek out of order, and inside a chunk
  in order (state carried in order looks right in every worker render - only the seek-order test sees it).
- Randomness only from a seeded PRNG (mulberry32) or a lattice. Libraries that default to `Math.random` get
  a seeded source: `withSeed()` around constructors (SSAOPass, GTAOPass, `DenoiseNode`),
  `setRandomGenerator(rng)` (MeshSurfaceSampler), `randomSource(rng)` (d3-force - and `.stop()` it on
  construction, it starts its own timer; then `tick(n)`).
- Story time (slow motion, freeze, ramps) = one uniform `uS = story(u)` for the world; the camera reads
  `u` (video-moves `makeStoryTime`).
- **Decisions on integer frames.** Cuts, sections, shot choice and discrete steps (scramble, flicker,
  boil, grain seed) compare `frame = Math.round(t * fps)` with `Math.round(cut * fps)` - never floats
  (`12.2 - 11.0 < 1.2` showed the old shot one frame late) and never `floor(t * rate)` in a shader.
  Continuous motion stays a function of t.
- **Decisions in shaders** hash integers (GLSL 3 `uint`, pcg): identical on GPU and SwiftShader. Float
  `fract(sin(x))` hashes are fine for dither, not for choices.
- **No frozen ends, no empty starts.** A section camera that ends on an ease stops before the cut (data reel:
  0.01-0.04 mean frame difference over the last 0.5 s): mix ~30% linear speed in,
  `drift(x) = 0.7 * ease(x) + 0.3 * x`. A growth or draw-on that starts at the section's t = 0 makes a flat
  first frame - start it a fraction of a second before.
- **No measured times in on-screen text.** `performance.now()` differs per worker (a bake-time caption made
  different DOM text in different chunks); show only build-invariant numbers (counts, sizes, draw calls).

## Picture

- **Supersampling**: geometry with edges at `setPixelRatio(2)` on a fixed 1920x1080 buffer (or MSAA x4
  render targets in a composer). Particle splats at pixel ratio 1 with energy-normalised Gaussian splats
  (σ ≥ 0.75 px). Grid passes at any ratio work in FILM pixels (Post-processing below).
- **`frustumCulled = false`** on every mesh whose vertices move after its bounds were computed: skinned
  meshes (the bounding sphere is computed lazily from the first pose a worker renders - per-worker state),
  `Flow` (culled by the straight geometry), instanced meshes moved per frame, VAT and shader-displaced meshes.
- **Lines** that must be seen are ≥ 2 px: tubes, or `Line2` / `LineSegments2` with `linewidth` in output
  px and NO `resolution` set and no pixel-ratio factor (its `onBeforeRender` overwrites `resolution`).
  Never `gl.LINES`.
- **Text**:
  - a label that keeps its size and only travels = DOM (or `CSS2DRenderer`), positioned from the projected
    3D anchor each frame, faded by facing or by ray occlusion;
  - text that the camera scales, turns or occludes = an SVG or canvas drawn ONCE at high resolution into a
    texture (`toneMapped: false`, max anisotropy), or troika SDF text synced in the build. Resizing or
    `scale()`-ing DOM text every frame flickers;
  - words as shapes = points sampled from text on an offscreen canvas.
- **Colour**:
  - flat colours: `THREE.ColorManagement.enabled = false`, `renderer.outputColorSpace =
    THREE.LinearSRGBColorSpace` - hex in = pixel out; or `MeshBasicMaterial` with `toneMapped: false`;
  - lit objects: `NeutralToneMapping` + an environment, then MEASURE the hero colours on a frame
    (`readPixels`). Tone mapping alone shifts a hue (Neutral darkens and saturates, ΔE 3.5; ACES +12° hue;
    AgX halves chroma); light and environment rotation shift it more. A matcap baked in the build is the
    most colour-stable lit material. Do not light a brand colour with a coloured light;
  - additive light on a coloured ground shifts hue: accumulate light AND coverage in a HalfFloat target,
    composite `ground·exp(-coverage·k)` + a hue-preserving tone map;
  - **uniform colours** in a `ShaderMaterial`: `new THREE.Color("#hex")` is converted to linear when colour
    management is on - right inside the lit scene, wrong for a display-space pass after `OutputPass`: parse
    the hex yourself (`hex3()`, in the ascii and looks recipes).
- **Banding** on dark gradients: a ±0.5-1 LSB dither after the sRGB transfer (or in the last pass while
  values are still HalfFloat), hashed from the pixel; master at `-q high --crf 10`. Judge banding only on
  high quality renders.
- **Shading seams**: half-Lambert on dark bodies. Acute corners in extruded SVG throw bevel spikes - round
  them before extruding.

## Post-processing (EffectComposer)

Proven by the ASCII film and the post and styles reels (every stock pass in `capabilities.md` 5-6).

- **`composer.render(0)`**: without an argument the composer hands every pass a wall-clock delta.
- **Order**: `RenderPass` (linear HDR) → linear effects (bloom, DOF, AO, SSR, motion blur) → `OutputPass`
  (tone map + sRGB) → display-space passes (LUT, grades, grain, vignette, glitch, ASCII, dither, CRT).
- **One composer, state set absolutely**: add every pass once and set each pass's `enabled` every frame
  (`runMain(list)`), or swap a prebuilt pass list per look into `composer.passes` (`runChain()`). With
  passes that re-render the scene (SSAO, Bokeh, SSAA, sub-frames): `shadowMap.autoUpdate = false` and
  `needsUpdate = true` once per frame.
- **Film pixels at composer pixel ratio 2**: stock passes count TARGET pixels - `HalftonePass` takes its
  grid from `setSize`, `DotScreenPass` reads the read buffer size, `RenderPixelatedPass` divides target px,
  `SobelOperatorShader`'s `resolution` starts at (0, 0) and is its tap spacing. Fix grids in film pixels
  (no-op `setSize` + film-px uniforms, `pixelSize = film px × 2`); own grid passes compute
  `uPR = target width / 1920` (`FilmPixelPass`, `assets/recipes/looks/`).
- **State captured at construction**: SSAOPass and GTAOPass call `Math.random()` (construct inside
  `withSeed()`: unseeded, 0/210 frames matched between worker counts); SSRPass, SAOPass and GTAOPass copy
  the camera projection (set FOV/aspect first; no animated FOV under SSR/SAO); SMAAPass loads lookup images
  asynchronously (`await whenImagesReady()` before the hold).
- **Time and randomness inside passes**: `FilmPass` time = `hash01(frame)` (its noise is periodic in time
  with period 1 - `time = t` repeats the grain every second); `GlitchPass` never - `ShaderPass(DigitalGlitch)`
  with a seeded `tDisp` and per-frame hashed uniforms; `OutlinePass` `pulsePeriod = 0`.
- **History - never**: `AfterimagePass`, `TAARenderPass` with `accumulate`, `SSRPass` with `bouncing: true`,
  `OutlineEffect.render()` (it never clears: the frame depends on what the buffer held - use
  `HullRenderPass`). A pass that leaks the previous frame is caught by the seek-order test or a poison probe
  (fill the target with magenta first), not by worker counts.

## Models and animation

- **Mixer**: per frame set each clip's `action.time` and weight absolutely (clamped for one-shots, modulo for
  loops), `enabled = true`, `paused = false`, then `mixer.update(0)` (`pose()`,
  `assets/recipes/models/rig.js`). The mixer writes a property only when its value changed since its last
  update, so never reset to the rest pose and undo every procedural write (look-at, bone aim) before the
  next update. `LoopOnce` + `mixer.setTime(t)` past the end disables the action for later seeks.
  `crossFadeTo` never - weights from t.
- Morph influences AFTER the mixer update (clips carry morph tracks), every influence every frame.
- Decoders (Draco, meshopt, KTX2) in the build only; GLTFLoader sanitises node names (`UpperArm.R` →
  `UpperArmR`).
- **Simulations are baked**: a Node script with a fixed dt writes per-frame transforms (JSON) or vertex
  positions (a VAT); the page imports no engine and reads `frame = t * fps` with lerp/slerp. Bake files
  carry no timings (rebakes are byte-identical); a GPU sim in the page is replayed or baked into layers
  (`capabilities.md` 7.6). Node tools in a non-ASCII path: `fileURLToPath`, not `URL.pathname`.

## Render

- CLI: hyperframes ≥ 0.8.156, pinned in `package.json`. WebGL (and WebGPU) turns fast capture off:
  screenshot capture, ~90 ms per frame - capture and the CRF 10 encode, not the GPU, bound render time
  (45-50 s films: 1.5-3 min on the M1 Max).
- **Determinism protocol** (commands: `qa-3d.md` step 3):
  1. `--workers auto` renders films of ≥ 900 frames on ONE worker ("single-worker drawElement streaming
     preferred"), so auto vs `--workers 1` proves nothing: compare `--workers 4` with `--workers 1` (same
     `--browser-gpu` setting).
  2. PLUS the in-page seek-order test (in order, seeded shuffle, reverse): it caught a mixer bug that all
     three worker renders shared (226 of 484 frames).
  3. If MP4 checksums differ, compare PNG sequences per section before blaming the scene. WebGL-only output
     was bit-identical in every film; DOM over WebGL may differ by ≤ 2 levels; a heavy WebGPU section varied
     in ~1 frame of 600 at 73 dB.
  4. An edit changes the ENCODED frames before it (x264 look-ahead/mbtree): to prove a section unchanged
     between versions, compare PNGs or require PSNR > 48 dB - not framemd5.
- GPU and SwiftShader frames are close (PSNR 41-55 dB) but NOT equal: pin `--browser-gpu` (or
  `--no-browser-gpu`) for a deliverable and never mix chunks. SwiftShader is ~6-10x slower (a GPGPU bake
  42x). Quantised looks amplify the difference (~5% of ASCII cells flip); chaotic GPU sims diverge
  completely (0% bit-equal after 500 steps).
- Bitrate at `-q high --crf 10`: UI films ~4 Mbit/s, lit 3D 6-16, particles/terrain/density ~25, a screen
  of glyphs 18, per-pixel grain 156, glitch bursts 73. Use `--crf 14-16` for delivery copies.
- `check` passes but sees nothing in the canvas ("0/0 text checks") - QA by frames (`qa-3d.md`).
- Toggle DOM labels with `visibility` `"hidden"` / `""` in JS and keep only `opacity: 0` in the
  stylesheet (`"visible"` leaks the element into later clips).

## WebGPU

Proven by the WebGPU reel (42 s on `WebGPURenderer`, bit-identical across worker counts). Code:
`assets/recipes/webgpu/webgpu-film.js`.

- Only on the hardware GPU path. On SwiftShader `requestAdapter()` returns null and three SILENTLY falls
  back to WebGL 2: `await renderer.init()`, reject the hold unless `renderer.backend.isWebGPUBackend`, AND
  put `data-requires-webgpu` on the root (the CLI then fails with exit 1 instead of a blank film). Render
  with `--browser-gpu`. Software WebGPU (`PRODUCER_ALLOW_SOFTWARE_WEBGPU=true`) is 100-1000x too slow.
- **`renderer._nodes.nodeFrame.update()` at the top of every `renderAt`** - node post (`pass()`, `bloom()`,
  `dof()` ...) re-renders once per node frame, and r181 advances that only in its own rAF loop (without it
  1,109 of 1,260 frames were stale). PRIVATE API: keep it, and re-check it on any three upgrade.
- **TSL clocks = film time**, once at module top: `time.onRenderUpdate(() => FILM_T)`,
  `deltaTime.onRenderUpdate(() => 1 / FPS)` (`film()`, `oscSine()`, `mx_timer()` read `time`).
- `bloom()` copies the uniforms you pass - drive its own (`bl.strength.value`).
- Hand `device.queue.onSubmittedWorkDone()` to `e.detail.waitUntil()`; return at once for the same t (with
  `data-requires-webgpu` the runtime re-dispatches the last seek every 250 ms while paused).
- TSL hash streams `hash(4i + j)` (`hash(i + 2^k)` streams are correlated); guard kernels against the 2D
  dispatch overshoot above 65,535 workgroups (`If(instanceIndex >= N) Return()`); storage buffers over
  128 MiB need `requiredLimits`.
- It tone-maps the whole frame, background included: measure dark grounds (they come out darker than WebGL).
