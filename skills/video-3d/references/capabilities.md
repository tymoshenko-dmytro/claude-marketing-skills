# three.js capabilities for video - the catalogue

Everything in three.js (0.181.2, the pinned version) that is useful for a FILM rendered by HyperFrames,
by area. Each entry: what it gives a film, how to use it deterministically (every visual state a pure
function of t - HyperFrames seeks frames out of order in parallel workers), traps, a sketch where it
helps, and a STATUS. The binding rules are in `contract.md`; this file does not repeat them all.
The films named in the statuses are private test films (they do not ship; their measurements are
summarised here). Reusable code is in `assets/recipes/<name>/`.

**Status legend**
- `proven (film)` - rendered in that test film, HyperFrames 0.8.156, M1 Max GPU path, 4-worker and
  1-worker renders compared (from the capability reels on, also the seek-order test).
- `proven, partial (film): what` - rendered, but only the part named.
- `never` - not seek-safe as shipped; the entry says what to use instead.

**Not in this catalogue** (never rendered in a test film; left out to keep the file to what works): 3D
Gaussian splat captures (async splat sorting), fracture / decals / marching cubes, fluid and soft-body
caches, lightmaps, cascaded shadows, stencil portals, the WebGPU post passes not named in 15.3. Before
promising any of these in a film: a 3-5 s probe, the determinism protocol (`qa-3d.md` step 3), frames.

**Test film labels** (the names inside a status). Four finished film looks, about 11-12 s each: the
`logo film` (an extruded logo, PBR, contact shadow), the `globe film` (15k instanced dots, tube arcs, DOM
labels), the `particles film` (64k points, splats, morphs, audio envelope), the `ASCII film` (terrain, rail
camera, composer, ASCII pass); a `WebGPU probe`. Then the seven capability reels of 2026-10-14 (41-50.5 s,
one capability per section, hard cuts): the `materials reel` (physical materials, shadows, area light,
HDRI, baked AO, sky), the `post reel` (every composer pass), the `styles reel` (toon, outlines, print,
dither, CRT, pixel art, ink), the `models reel` (glTF, mixer, skinning, morphs, baked sims, Flow), the
`camera-text reel` (ortho, dolly zoom, shake, cuts, 3D text, lines, screens, image sequences, DOM/GSAP,
sub-composition, alpha), the `data reel` (bars, maps, networks, terrain and audio from data, BatchedMesh,
GPGPU), the `WebGPU reel` (WebGPURenderer film, TSL, node post, compute, atomics). `all films` and
`every reel` mean what they say.

## Contents

1. [Cameras and rigs](#1-cameras-and-rigs)
2. [Geometry](#2-geometry)
3. [Materials](#3-materials)
4. [Light, shadows, environments](#4-light-shadows-environments)
5. [Post-processing](#5-post-processing)
6. [Stylisations](#6-stylisations)
7. [Particles and GPU compute](#7-particles-and-gpu-compute)
8. [Simulations](#8-simulations)
9. [Animation and models](#9-animation-and-models)
10. [Textures, screens and video](#10-textures-screens-and-video)
11. [Text in 3D](#11-text-in-3d)
12. [Data visualisation](#12-data-visualisation)
13. [Compositing with DOM, GSAP and footage](#13-compositing-with-dom-gsap-and-footage)
14. [Audio-driven visuals](#14-audio-driven-visuals)
15. [WebGPU, TSL and node materials](#15-webgpu-tsl-and-node-materials)
16. [Assets and sources](#16-assets-and-sources)
17. [Seek-safety cheat sheet](#17-seek-safety-cheat-sheet)

---

## 1. Cameras and rigs

Camera grammar (which move, why, how long) belongs to video-moves; its `camera-kit.js` math
(`ease`, `seg`, `logLerp`, `rng`, `handheld`, `shake`, `makeStoryTime`) is copied into the scene
module. Every camera value is written from t; `camera.updateMatrixWorld()` after each change. A
section camera that ends on an ease freezes before the cut: mix ~30% linear speed in (`contract.md`, Time).

### 1.1 PerspectiveCamera - `proven (all films)`
- Use: fixed aspect `W / H`; tight `near`/`far` for depth precision.
- Traps: after changing `fov`, `zoom`, `near`, `far` call `camera.updateProjectionMatrix()`. Never
  `OrbitControls` or any control with damping - it is state. SSR/SAO passes copy the projection at
  construction (5.20).

### 1.2 OrthographicCamera - `proven (camera-text reel)`
- Gives: isometric and 2.5D looks, diagrams and maps without perspective.
- Use: frustum from the frame (`left = -h*aspect/2` ...); true isometric elevation `atan(1/√2)` = 35.264°;
  zoom with `camera.zoom` on a log curve (+ `updateProjectionMatrix()`).
- Traps: no parallax; a default `Fog` with an ortho camera parked far away fogs the whole frame
  (camera-text reel: ~20% contrast) - no fog, or fog distances from the ortho rig.

### 1.3 Look-at and spherical rigs - `proven (logo film, globe film, particles film, post reel, styles reel, data reel)`
- Use: position from angles of t, distance with `logLerp`, `camera.lookAt(target)`; roll after `lookAt`
  with `camera.rotateZ(roll)`; constant drift on holds (the globe film's 0.6°/s read as frozen, 1.5°/s did
  not).
```js
const k = seg(t, A, B), az = rad(lerp(-35, 0, k)), el = rad(lerp(18, 6, k)), d = logLerp(4.2, 6, k);
camera.position.set(d * Math.sin(az) * Math.cos(el), d * Math.sin(el), d * Math.cos(az) * Math.cos(el));
camera.lookAt(target); camera.rotateZ(rad(roll)); camera.updateMatrixWorld();
```

### 1.4 Curve rails (CatmullRomCurve3) - `proven (ASCII film, data reel)`
- Use: `new THREE.CatmullRomCurve3(points, false, "centripetal")`; `getPointAt(k)` is arc-length - ease
  `k`, not the points. Enter an in-out ease at 25% so frame 0 already moves. FPV: look at
  `getPointAt(min(1, k + 0.02))`.
- Traps: long rails need `curve.arcLengthDivisions = 2000` (+ `updateArcLengths()`). Check clearance
  against the geometry in the build (`contract.md`; data reel: every frame against bar heights and terrain).
  Glyph or pixel styles strobe if content crosses > ~1 cell per frame.
```js
const rail = new THREE.CatmullRomCurve3(PTS, false, "centripetal");
const E0 = ease(0.25), fly = (x) => (ease(0.25 + 0.75 * x) - E0) / (1 - E0);
rail.getPointAt(fly(clamp01(t / T.railEnd)), camera.position); camera.lookAt(targetAt(t));
```

### 1.5 Landing an object at a screen position and size - `proven (logo film)`
Solve in camera space: `F = (H/2) / tan(fov/2)`, distance for an on-screen height `D = F * worldH / px`,
offset in px times `D / F`. Never tween in screen space.

### 1.6 FOV, focal length, dolly zoom - `proven (camera-text reel)`
- Use: hold the subject's visible height: `th = logLerp(tan(fovA/2), tan(fovB/2), k)`,
  `dist = VIS_H / (2 * th)`, camera at the subject's face plane + dist (camera-text reel: FOV 12° → 76°,
  the device stayed 432.000 px tall in all sampled frames).
- Traps: fog is by distance - a dolly zoom with fog changes the subject's brightness; start the fog
  behind the farthest camera position.

### 1.7 Handheld and shake from seeded noise - `proven (camera-text reel)`
- Use: camera-kit `handheld(t)` and `shake(t, {seed})` (values stepped every 1/12 s, decaying), applied as
  small rotations after `lookAt`; shake in px → degrees via `H / fov`.
- Traps: a fresh random per frame reads as digital jitter; `Math.random` is never allowed.
```js
const h = handheld(t), s = shake(t - T.hit, { seed: 7 });
camera.lookAt(target); camera.rotateY(rad(h.yaw)); camera.rotateX(rad(h.pitch)); camera.rotateZ(rad(h.roll + s.roll));
```

### 1.8 Cuts and sections inside one canvas - `proven (camera-text reel; every reel)`
- Use: cut and section times as named constants; choose the shot or section on INTEGER frames
  (`Math.round(t * fps)` vs `Math.round(cut * fps)`) - `12.2 - 11.0 = 1.1999999999999993 < 1.2` showed the
  old shot one frame late. Continuous motion stays a function of t. Each section can own a scene and a
  camera (a `sectionAt(frame)` lookup, or one `[start, end, make]` module per section). Verify the frames
  either side of every cut.

### 1.9 Story time: slow motion, freeze, bullet time - `proven (particles film)`
One world uniform `uS = story(u)` (`makeStoryTime(piecewiseRate(...))`); the camera keeps real time, so
it can orbit a frozen world.

### 1.10 Depth of field - see 5.4 (BokehPass) and 15.3 (`dof()`).

---

## 2. Geometry

Build all geometry once in the build (before the hold resolves). Per-frame changes go through uniforms
or attributes written from t. `frustumCulled = false` on every mesh whose vertices move after its bounds
were computed: skinned, Flow, instanced, VAT and shader-displaced (`contract.md`, Picture).

### 2.1 Primitives - `proven (globe film, ASCII film, post reel, styles reel)`
Box, Sphere, Icosahedron, Torus, TorusKnot, Plane, Cylinder, Capsule, Cone, Ring; addons
`RoundedBoxGeometry`, `TeapotGeometry`. Segment counts high enough for silhouettes at hero size.

### 2.2 SVG extrusion - `proven (logo film)`
- Use: `SVGLoader.createShapes(path)` → `ExtrudeGeometry` with `bevelOffset = -bevelSize` (exact
  silhouette), `scale(K, -K, -K)` (flips SVG y without inverting the winding), `toCreasedNormals`.
- Traps: very acute corners throw bevel spikes - fillet them first. Gradients: bake into vertex colours.

### 2.3 Lathe - `proven (materials reel, styles reel)`
- `assets/recipes/materials/lathe.js`: `vaseProfile()` (real wall thickness, round lip, inner floor;
  normals face out of the material), `turned(points)` = `LatheGeometry` + `uv1` by arc length (bake target
  for aoMap) + `indicesPerSegment` for a drawRange sweep from t.
- Traps: a flat base sitting on a plinth z-fights (make it slightly concave); a coarse profile shows
  facets in toon bands (spline to ~120 points).

### 2.4 Tube along a curve - `proven (globe film)`
`TubeGeometry(curve, segs, radius)` ≥ 2 px on screen; draw-on = a `ShaderMaterial` that `discard`s past
a `uHead` uniform along the tube's u.

### 2.5 TextGeometry - `proven (camera-text reel)`
Any TTF → typeface JSON in Node (`TTFLoader`, in a short script you write) → `FontLoader` →
`TextGeometry` with bevel, two materials (face, sides). Heavy for long text; for type as an object the
SVG route (2.2) on font outlines is lighter.

### 2.6 SDF text (troika-three-text) - `proven (camera-text reel)`
- Use: `troika-three-text@0.52.4` from esm.sh with `?external=three` next to the importmap; in the build
  `await Promise.all(texts.map((t) => new Promise((r) => t.sync(r))))`. Animate `fillOpacity`,
  `curveRadius`, `colorRanges` and transforms - no re-layout. Proof: 0 `syncstart` events after the hold
  (troika calls `sync()` from `onBeforeRender` every frame as a no-op, so counting calls proves nothing).
- Traps: never change `text` or font properties at seek time (layout and SDFs are async); wrapped text
  longer than the cylinder's circumference overlaps itself. SDFs are generated on the GPU - SwiftShader
  not tested.

### 2.7 Instancing and BatchedMesh - `proven (globe film, data reel)`
- `InstancedMesh`: static layout in the build; per frame either the shader from t and per-instance
  attributes, or `setMatrixAt` for all from t + `instanceMatrix.needsUpdate = true` (8,000 lit shards per
  frame on the CPU were cheap). `setColorAt` once.
- `BatchedMesh` (data reel): `addGeometry` x N, `addInstance` per unit, `setVisibleAt` + `setMatrixAt` from t;
  1 draw call with `WEBGL_multi_draw` (also on SwiftShader). Every geometry indexed or none
  (`geo.setIndex([...Array(n).keys()])` on a non-indexed polyhedron).

### 2.8 Custom BufferGeometry and attributes - `proven (particles film, ASCII film)`
Per-vertex or per-particle attributes from one seeded PRNG in the build; heights written on the CPU;
`computeVertexNormals()` after displacement.

### 2.9 Morph targets - `proven (models reel)`
`mesh.morphTargetInfluences[i] = f(t)` every frame (face blends Angry / Surprised / Sad). glTF clips may
carry morph-weight tracks: set influences AFTER the mixer update and set every influence every frame
(`setMorphs()` in `assets/recipes/models/rig.js`). Draco keeps morph targets exactly.

### 2.10 Terrain and displacement - `proven (ASCII film, data reel)`
- Use: displace a plane on the CPU in the build (fbm, an image, a CSV, a spectrogram), then
  `computeVertexNormals()`. `displacementMap` on the GPU does not update normals.
- Contour lines via `onBeforeCompile` with the width in pixels:
  `(0.5 - abs(fract(u) - 0.5)) / fwidth(u)` (a half-width in height units becomes blobs on plateaus).
- Taper heights to 0 near the edges (no cut cliffs); from audio see 12.5.

### 2.11 Points from a mesh surface (MeshSurfaceSampler) - `proven (models reel)`
- Use: `new MeshSurfaceSampler(mesh).setRandomGenerator(rng(SEED)).build()` (default `Math.random`).
  On a skinned mesh keep face + barycentrics (`_sampleFaceIndex()` is private in r181) and skin per frame:
  `getVertexPosition()` for all vertices once, then barycentric per point (24,000 points).
- Traps: faces are weighted by LOCAL area - a node scale (the robot's hands, x100) gets no points; split
  the point budget by world area measured on posed vertices.

### 2.12 Shape → points from a canvas - `proven (particles film)`
Draw text or a logo on an offscreen canvas after the font loads, rejection-sample by alpha with a seeded
PRNG, sort by x so particle i keeps its rank across shapes.

### 2.13 Lines - `proven (globe film: tubes; camera-text reel: Line2, LineSegments2, dashed)`
`Line2` / `LineSegments2` give constant pixel width: `linewidth` = output px. Do NOT set
`material.resolution` (its `onBeforeRender` overwrites it with the renderer viewport in CSS px) and do not
multiply by the pixel ratio (2 px measured 1.94; with the ratio applied 3.85). Draw-on and marching dashes
from t. `gl.LINES` is 1 px and aliases - never for lines that must be seen.

### 2.14 Bending along a path (CurveModifier `Flow`) - `proven (models reel)`
`flow.uniforms.spineOffset.value = 0` (default 161), `flow.uniforms.pathOffset.value = f(t)` (a 0..1
fraction; `moveAlongCurve` adds - state), `frustumCulled = false` (culled by the straight geometry's
bounds). Closed curves only (the path wraps); the shadow pass draws the straight mesh (the ribbon cannot
cast); the outer face may come out upside down (rotate the texture 180°).

---

## 3. Materials

Colour: tone mapping alone moves a hue (materials reel, `#e0893c` lit): Neutral darkens and saturates
(ΔE 3.5), ACES turns it yellow (+12° hue, ΔE 8.9), AgX halves chroma (ΔE 9.6). Measure hero colours.

### 3.1 MeshStandardMaterial - `proven (ASCII film, materials reel, data reel)`
PBR roughness/metalness; needs an environment (4.6) or lights. `envMapIntensity` per material.

### 3.2 MeshPhysicalMaterial - `proven (logo film: clearcoat; materials reel: the rest below)`
- clearcoat: lacquer, car paint. Metal vs dielectric roughness series 0.05-0.85.
- transmission + thickness + ior + attenuationColor: glass refracting what is behind it; 7.2 ms per frame,
  the costliest material. Shadow maps ignore transmission - `castShadow = false` on glass.
- iridescence: thickness range from t over a seeded noise `iridescenceThicknessMap`.
- sheen: reads on a dark base with a fine weave normal map (otherwise hammered metal).
- anisotropy 0 → 0.9 from t: the highlight stretches round the circumference (`anisotropyRotation 0`
  follows uv u; no tangent attribute needed).
- `RectAreaLight` has no clearcoat or sheen term (4.5).

### 3.3 Toon - `proven (materials reel, styles reel)`
`MeshToonMaterial` + a 3-4 step `gradientMap` (`RedFormat` DataTexture, `NearestFilter`); receives PCF
shadows; bands hold a few exact colours. Outlines: 6.2.

### 3.4 Matcap - `proven (materials reel)`
`MeshMatcapMaterial({ matcap })` with the matcap RENDERED IN THE BUILD (a lit physical sphere, ortho camera,
HalfFloat target, tone-mapped once by the material): the most colour-stable material (ΔE2000 1.5).

### 3.5 Unlit (MeshBasicMaterial) - `proven (logo film)`
Flat colours, text planes, UI textures: `toneMapped: false` keeps the hex exact.

### 3.6 ShaderMaterial and onBeforeCompile - `proven (globe film, particles film, ASCII film, data reel, models reel)`
Procedural dots, draw-on tubes, atmospheres, splats, contour lines, map borders, VAT playback. Uniforms
from t only; integer hashes for decisions. `customProgramCacheKey` lets many patched materials share one
program.

### 3.7 Utility materials - `proven (logo film, styles reel, models reel)`
`MeshDepthMaterial` (contact shadow, VAT shadow depth), `MeshNormalMaterial` (ink pass), `MeshDistanceMaterial`.

### 3.8 Node materials / TSL - see 15.2, `proven (WebGPU reel)`.

---

## 4. Light, shadows, environments

### 4.1 Punctual lights - `proven (logo film, ASCII film, materials reel)`
A key with no fill renders a black cutout - add a hemisphere or environment fill. Do not light a brand
colour with a coloured light. A low front rim light makes a hot spot on a glossy floor (post reel: raise it to
~52° so its reflection leaves the frame).

### 4.2 Shadow maps - `proven (materials reel: PCFSoft, VSM; data reel, models reel)`
- Use: `PCFSoftShadowMap` or `VSMShadowMap` (`radius`, `blurSamples`; bleeds light under contacts); a tight
  shadow camera; `bias` ~ -0.0005; `mapSize` 2048.
- Traps: three r181 does NOT recompile materials when `renderer.shadowMap.type` changes - set
  `needsUpdate` on every material when it changes (`setShadowType()`, `assets/recipes/materials/README.md`).
  With passes that re-render the scene (SSAO, Bokeh, SSAA, sub-frames): `shadowMap.autoUpdate = false` and
  `needsUpdate = true` once per frame.

### 4.3 Contact shadow - `proven (logo film)`
Depth of the object seen from the floor upward, blurred twice, on a ground plane; per frame. Hide text
planes from its depth pass; fade it out at grazing camera angles.

### 4.4 Planar shadows (ShadowMesh) - `proven (materials reel)`
Hard, exact silhouettes on one plane, the light from t. `ShadowMesh.update(plane, light4D)` projects onto
`n·p = +constant` - the OPPOSITE sign of `THREE.Plane`: a floor at height h is `new Plane(up, +h)`
(`-h` draws nothing, silently).

### 4.5 Area lights - `proven (materials reel)`
`RectAreaLight` + `RectAreaLightUniformsLib.init()`: a light bar sliding round a product, soft pools on
the floor. Its reflection shows in the base layer only (no clearcoat/sheen term): glossy base, roughness
~0.1, no clearcoat. Show the bar itself as an unlit tube. No shadows.

### 4.6 Environments - `proven (logo film, ASCII film: RoomEnvironment; materials reel: HDRI)`
- `pmrem.fromScene(new RoomEnvironment(), 0.04).texture` → `scene.environment`: procedural, no file.
- HDRIs: `HDRLoader` → `pmrem.fromEquirectangular(tex)`, `GroundedSkybox` for a visible ground;
  `environmentRotation` and the skybox's `rotation.y` from t. Local copy in the film's assets (Poly Haven,
  `https://dl.polyhaven.org/file/ph-assets/HDRIs/hdr/2k/<name>_2k.hdr`, ~6 MB at 2k).
- The HDRI's sun from its pixels drives a shadow light: HDRLoader row 0 is the image TOP, so
  `θ = (0.5 - v)·π` (the sun snippet in `assets/recipes/materials/README.md`).
- Traps: rotating the environment moves the light on the subject, not only reflections (logo film: orange
  #f04a20 → #b23004 at 90°; materials reel: ΔE 37 with the HDRI sun behind).

### 4.7 Baked AO - `proven (materials reel)`
`bakeAO()` (`assets/recipes/materials/ao-bake.js`): a deterministic GPU bake in the build, 384 Fibonacci
directions, visible and open weights accumulated (AO = R/G), ~0.3 s; `aoMap` on `uv1`,
`aoMapIntensity` from t.

### 4.8 Fog - `proven (ASCII film, materials reel, camera-text reel)`
`Fog` / `FogExp2`. Fog colour = `scene.background` gives an infinite floor (fog runs after tone mapping, in
output space). Custom shaders need `fog: true` and the fog chunks. Ortho and dolly-zoom traps: 1.2, 1.6.

### 4.9 Sky, lens flare, light probes - Sky, Lensflare `proven (materials reel)`; LightProbe `proven, partial (materials reel): baked keys only`
- `Sky`: sun position from t, a sun light with shadows, tone-mapped at exposure ~0.55.
- `Lensflare` with procedural flare textures; geometry occludes the sun and the flare vanishes (framebuffer
  read - deterministic).
- `LightProbeGenerator.fromCubeRenderTarget` is async: bake SH at keys along the light path in the build
  (13 keys) and lerp by t. A per-frame probe is not possible.

---

## 5. Post-processing

The composer path is `proven (ASCII film, post reel, styles reel)`. Rules (`contract.md`):
`composer.render(0)`; linear passes before `OutputPass`, display-space passes after it; passes are added
once and their `enabled` set absolutely every frame (or a prebuilt pass list per look swapped in); at
composer pixel ratio 2 stock passes count TARGET pixels. Chain, numbers and `post-kit.js`:
`assets/recipes/post/`.

```js
const composer = new EffectComposer(renderer, new THREE.WebGLRenderTarget(W, H, { type: THREE.HalfFloatType, samples: 4 }));
composer.addPass(new RenderPass(scene, camera));
composer.addPass(new UnrealBloomPass(new THREE.Vector2(W, H), 0.35, 0.4, 0.85));
composer.addPass(new OutputPass());
// display-space passes here (ASCII, LUT, grain, dither, CRT)
function renderAt(t) { /* camera, uniforms from t */ composer.render(0); }
```

| # | Pass (addon) | Gives | Time or randomness inside | Drive from t / fix | Status |
|---|---|---|---|---|---|
| 5.1 | `RenderPass` | the scene into a linear HDR target | none | - | proven (ASCII film, post reel, styles reel) |
| 5.2 | `OutputPass` | tone map + sRGB, mid-chain OK | none | - | proven (ASCII film, post reel, styles reel) |
| 5.3 | `UnrealBloomPass` | glow on highlights | none | strength/threshold | proven (ASCII film, styles reel) |
| 5.4 | `BokehPass` | rack focus from real depth | none | `focus` = view depth `-(viewMatrix·p).z` lerped; aperture 0.005, maxblur 0.015 (≤ ~11 px) | proven, partial (post reel): thin bright lines ladder into its 41 taps |
| 5.5 | `SSAOPass`, `GTAOPass` | ambient occlusion | `Math.random` at construction | `withSeed()` construction; SSAO min/maxDistance are fractions of (far - near); GTAO strength = `scale` | proven (post reel) |
| 5.6 | `SAOPass` | AO, older | none | intensity ~0.05 (0.25 draws halos) | proven (post reel) |
| 5.7 | `SSAARenderPass` | N jittered renders, best AA | none | `sampleLevel` 4 = 16 samples, 8.7 ms | proven (post reel) |
| 5.8 | `TAARenderPass` | AA | history when `accumulate` | `accumulate = false` is pixel-identical to SSAA (default level 0 = 1 sample): use SSAA | proven, redundant (post reel); never with accumulate |
| 5.9 | `SMAAPass`, `FXAAPass` | edge AA | SMAA lookup images load async | await `whenImagesReady()` | proven (post reel) |
| 5.10 | `FilmPass` | grain | `time += delta`; `rand(fract(uv + time))` | `time = hash01(frame)` (`time = t` repeats the grain every second); it only brightens (+25% at 0.5) | proven (post reel) |
| 5.11 | `OutlinePass`; `SobelOperatorShader` | outlines; edge detect | OutlinePass pulse = `performance.now()` | `pulsePeriod = 0`, `edgeStrength` from t; Sobel `resolution` set by hand | proven (styles reel) |
| 5.12 | `ShaderPass(VignetteShader)` | vignette | none | ramp `offset` from 0, `darkness` 1 (darkness 0 mixes to WHITE) | proven (post reel) |
| 5.13 | `ShaderPass(RGBShiftShader)` | chromatic aberration | none | `amount`, `angle` | proven (post reel) |
| 5.14 | `LUTPass` + `LUTCubeLoader` | grading from a .cube | none | `setType(FloatType)` (default truncates); after OutputPass | proven (post reel) |
| 5.15 | grade shaders | quick grades | none | uniforms | proven, partial (post reel): BrightnessContrast, HueSaturation, BleachBypass |
| 5.16 | `RenderPixelatedPass` | pixel art with edges | none | `pixelSize` in target px; set edge strengths after construction | proven, partial (styles reel): crawls under an orbit |
| 5.17 | `HalftonePass`, `DotScreenPass` | print looks | none | grid in film px (6.3) | proven (styles reel) |
| 5.18 | `GlitchPass` | glitch | `Math.random()` per frame + counter | `ShaderPass(DigitalGlitch)` + `seededDispTexture` + `glitchSchedule` (proven, post reel) | never |
| 5.19 | `AfterimagePass` | trails | reads the previous frame | render past states from t | never |
| 5.20 | `SSRPass` | floor reflections | `bouncing: true` reads the previous frame | `selects: [floor]`, `bouncing: false`, `beautyRenderTarget.samples = 4` in an MSAA chain; copies the projection at construction | proven (post reel) |
| 5.21 | plumbing | `SavePass`, `ShaderPass(CopyShader)`; `MaskPass`, `ClearPass`, `TexturePass` | none | - | proven, partial (styles reel): SavePass, ShaderPass, CopyShader |
| 5.22 | custom `Pass` with own targets | anything | yours | yours | proven (ASCII film, styles reel, post reel) |

Cost per 1080p frame (M1 Max, incl. OutputPass): base 2.6 ms; SSAO 4.5, GTAO 7.8, SAO 4.5, Bokeh 3.6,
SSR 14.7, FXAA/SMAA ~1.5 on a no-MSAA chain, SSAA x16 8.7. Bitrate at CRF 10: grain 156 Mbit/s, glitch 73.

**Seeded Math.random swap** for constructors (5.5; also `DenoiseNode` in 15.3):
```js
function withSeed(seed, make) { const keep = Math.random; Math.random = rng(seed);
  try { return make(); } finally { Math.random = keep; } }
const ao = withSeed(11, () => new GTAOPass(scene, camera, 1920, 1080));
```

**Motion blur by sub-frame accumulation** - `proven (post reel)`: `SubframeMotionBlurPass` replaces RenderPass,
renders the world at 16 times inside a 180° shutter and sums them 1/N (31.9 ms). Velocity-buffer blur
needs the previous frame's matrices - never as shipped.

**Wipes, tiles, splits** - `proven (post reel, materials reel)`: `Presenter` copies composer results 1:1 into
screen rectangles (with a static dither); or scissored renders of two set-ups per frame (materials reel:
reset every light and material, then apply each side's set-up, per frame).

---

## 6. Stylisations

Display-space passes on the proven composer path. Code and chains: `assets/recipes/looks/` (styles reel).
Grid styles amplify GPU vs SwiftShader differences (ASCII film: ~5% of cells flip) - pin the backend. Judge
hard-threshold looks by A-B-A blips (`qa-3d.md` step 9).

### 6.1 ASCII cinema - `proven (ASCII film)`
Recipe and code: `recipes.md` and `assets/recipes/ascii/`.

### 6.2 Toon / cel with outlines - `proven (styles reel, materials reel)`
- Inverted hull: `HullRenderPass` (clears, renders, then `effect.renderOutline()`); `OutlineEffect.render()`
  never clears - it made frames depend on seek order. Hull width is in NDC (~4 px horizontal, ~2.3 vertical).
- `OutlinePass`: additive only (no dark ink), ~2 film px at any thickness.
- Sobel ink: Luminosity → Sobel → `SobelInkPass` over a `SavePass` copy (silhouettes and band edges).

### 6.3 Halftone - `proven (styles reel)`
`HalftonePass` between two `InvertPass`es = CMY ink on paper; feed it `(ink/π)^(1/2.25)` (dot-gain
compensation, else mid-tones print dark and orange prints red); grid set in film px. `DotScreenPass`:
`scale = 2π / (period × 2)` at pixel ratio 2. Hold blips 0.063% (the ASCII reference is 0.12%).

### 6.4 1-bit and ordered dithering - `proven (styles reel)`
`DitherPass`: 1-bit (Bayer 8x8 on 2x2 px dots) or palette (two nearest of N + Bayer 4x4, 3 px pixels);
exact box average per dot; the pattern is fixed to the screen. Hold blips 0.001% / 0.011%. Error diffusion
is sequential - not a GPU pass.

### 6.5 CRT and scanlines - `proven (styles reel)`
`CrtPass` after bloom: barrel, Gaussian scanlines on the curved glass, aperture grille, vignette; flicker
`1 + 0.03 * (hash01(frame) - 0.5)`, roll from t.

### 6.6 Pixel art - `proven, partial (styles reel)`: deterministic, but crawls under a perspective orbit
`RenderPixelatedPass` (6 film px = `pixelSize` 12 at ratio 2) on toon materials. In a hold 3.4% of art
pixels change per frame, one in ten as A-B-A; texel snapping works only for ortho cameras and pans.

### 6.7 Ink and paper - `proven (styles reel)`
`InkPaperPass`: edges from a 1/z Laplacian (zero on planes) + normal creases, boil `floor(frame / 3)`,
hatching from a KEY-LIGHT-ONLY render (luminance hatching hatches a whole dark studio), static seeded paper.

### 6.8 Switching looks inside a shot - `proven (styles reel)`
Both looks rendered every frame, A copied to a 2x target, `WipeQuad` mixes them by an edge from t.

---

## 7. Particles and GPU compute

### 7.1 Points with position = f(t, attributes) - `proven (particles film, WebGPU reel)`
64k particles, 2.5-4.4 ms GPU per frame (WebGL). Attributes from one seeded PRNG; everything in the
vertex shader from story time. Same closed-form motion as Gaussian sprites: WebGL vertex shader 1M in
10.7 ms, 16M in ~204 ms; WebGPU compute + sprites only 1.0-1.5x faster (15.4).

### 7.2 Gaussian splats with energy normalisation - `proven (particles film, WebGPU reel)`
`w = E·exp(-r²/2σ²)/(2πσ²)`, σ ≥ 0.75 px, quad padded to ±3σ; ONE/ONE into HalfFloat targets; light AND
coverage accumulated so colours keep their hue on a coloured ground; glow at 1/4 resolution.

### 7.3 Shape-to-shape morphs - `proven (particles film)`
Point sets from canvas text (2.12), mesh surfaces (2.11) or data; rank-sorted; a narrow flight band
(`dur / stag ≈ 0.45`).

### 7.4 Instanced lit particles - `proven (data reel)`
8,000 flat octahedron shards, `MeshStandardMaterial` + environment + PCF soft shadows, `setMatrixAt` from
closed-form motion; no sparkle at 1:1 on consecutive frames.

### 7.6 GPUComputationRenderer (ping-pong state) - `proven (data reel)`: replay and bake
State at film frame f = f × steps from the seeded initial texture. `assets/recipes/data/gpgpu.js`:
1. **Closed form** first (7.1) - almost always possible for film.
2. **Replay inside every seek** (`replayAt`): ~0.039 ms per step up to ~1M particles (three's per-pass
   overhead), total `0.039 ms × S × F²/2` - usable to ~1-2 min of sim per shot; start the sim at the shot.
3. **Bake into `WebGLArrayRenderTarget` layers** in the build (`bakeLayers`): frames × particles × 16 B per
   WORKER (≤ ~0.5 GB: 36k particles ~30 s, 1M particles 1-2 s).
- (2) and (3) are bit-identical on one GPU (0 differing floats checked in the build). A chaotic sim diverges
  between GPU and SwiftShader (0% bit-equal after 500 steps) - pin the backend, or bake on the CPU (8).
- The class has no reset: render the initial texture into BOTH targets, `currentTextureIndex = 0`.

### 7.7 WebGPU compute (TSL `compute()`) - `proven (WebGPU reel)`
2M particles from `f(t, hash(index))` in 0.2-0.3 ms; 16M points splatted with `atomicAdd` in 14 ms
(`densitySplat()`, `assets/recipes/webgpu/`). Hash streams `hash(4i + j)`; guard kernels above 65,535
workgroups; storage over 128 MiB needs `requiredLimits` (15.1). WebGPU path only.

---

## 8. Simulations

Rule: **simulate at build time, play back by t.** The page imports no physics engine (the addon helpers
step on a clock). Bake files carry no timings (byte-identical rebakes). Playback code:
`assets/recipes/models/baked-playback.js`; the bake scripts are yours to write in Node (formats in its
header, the models reel's settings and costs in `assets/recipes/models/README.md`).

- **Rigid bodies** - `proven (models reel)`: Rapier (`@dimforge/rapier3d-compat`) in Node, fixed dt 1/240,
  8 substeps per film frame; position + quaternion per body per frame in JSON (34 bodies, 6 s: 0.2 s bake,
  307 KB); `rigidAt()` lerps and slerps between frames, hides bodies before their spawn frame.
- **Cloth (VAT)** - `proven (models reel)`: own PBD in Node, Uint16 xyz quantised to the bbox (41x41 grid,
  165 frames, 1.7 MB, 10-13 s bake); the vertex shader reads row `frame` (`texelFetch`), normals from
  neighbouring texels; patch the colour AND the shadow-depth material. Draw colliders slightly smaller than
  their bake shapes and round sharp corners (the grid cuts chords).
- **Flocks** - `proven (models reel)`: boids baked (160 birds); heading and bank from neighbouring frames,
  wingbeat in the vertex shader from t (a `flockAt()` you write next to `rigidAt()`).
- **Force-directed layouts** - `proven (data reel)`: d3-force 3.0.0 in the build:
  `forceSimulation(nodes).randomSource(rng(SEED)).stop()` (it starts a timer on construction), `tick(400)`.

---

## 9. Animation and models

Code: `assets/recipes/models/` (models reel).

### 9.1 GLTF and decoders - `proven (models reel)`
- `GLTFLoader` + `DRACOLoader` (`setDecoderPath(".../three@0.181.2/examples/jsm/libs/draco/")`),
  `MeshoptDecoder`, `KTX2Loader` (`libs/basis/`, `detectSupport(renderer)`) - in the build only;
  `renderer.compile()` after the model is in the scene. Robot 464 KB → Draco 250 KB, meshopt 221 KB.
- Traps: GLTFLoader sanitises node names ("UpperArm.R" → `UpperArmR`); `KTX2Loader.parse` transfers the
  ArrayBuffer (read `byteLength` first). Compress with gltf-transform + `ktx2-encoder` (WASM) in Node.

### 9.2 AnimationMixer - `proven (models reel)` with `pose()`
- Use: per character, each clip's `action.time` and weight set ABSOLUTELY from t (clamped for one-shots,
  modulo for loops), `enabled = true`, `paused = false`, then `mixer.update(0)`. Blend = weights you compute
  from t (no `crossFadeTo`). `mixer.setTime(t)` is fine only for looping clips at fixed weights.
- Traps: the mixer writes a property only when its value CHANGED since the mixer's previous update - a
  rest-pose reset or a look-at between updates survives (only in order, so every worker render agrees and
  only the seek-order test caught it: 226 of 484 frames wrong). Never reset to rest; undo procedural writes
  before the next update. LoopOnce + `setTime` past the end disables (or pauses) the action for good.

### 9.3 Skinned characters - `proven (models reel)`
`SkinnedMesh` from glTF, `SkeletonUtils.clone()` copies each with its own mixer (a fully skinned fox +
4 robot clones). `frustumCulled = false`: the bounding sphere is computed lazily from the first pose a
worker renders. Retargeting is a build-time job.

### 9.4 Procedural animation of models - `proven (models reel)`
Bone aim on top of a clip (`aimBone()`: world-space pre-rotation, clamped, weighted, recorded for undo),
head look-at at a target on a closed-form path; transforms, morph influences and uniforms from t.

---

## 10. Textures, screens and video

### 10.1 CanvasTexture drawn once - `proven (logo film, ASCII film, data reel)`
SVG or text at 2x its largest on-screen size, max anisotropy, mipmaps; or 1:1 with `NearestFilter` for a
glyph atlas. Await fonts first. A whole map ground at 4096 px (data reel).

### 10.2 CanvasTexture redrawn per frame - `proven (camera-text reel)`
Redraw from t in `renderAt` (`drawLive()`: frame counter, timecode, a bar chart, a scrolling list), then
`needsUpdate = true`. A CPU canvas rasterises identically in every worker.

### 10.3 DataTexture - `proven (ASCII film, materials reel, data reel)`
Per-cell layers, masks, normal maps and noise built in JS (`dataTex()`), `NearestFilter`, `texelFetch`.

### 10.4 Render-to-texture: screens, mirrors, portals - `proven (camera-text reel)`
- Monitor: a second camera into a HalfFloat render target each frame, the screen hidden during its own pass.
- `Reflector` mirror.
- Portal: the other scene rendered with `inverse(portal.matrixWorld) * camera.matrixWorld` into a
  drawing-buffer-sized target, sampled at `gl_FragCoord / uRes` with the tonemapping + colorspace chunks;
  layers keep helper meshes out of the mirror's and monitor's cameras.

### 10.5 Video as a texture: an image sequence - `proven (camera-text reel)`; `VideoTexture` `never`
- Why not `VideoTexture`: a `<video>` decodes asynchronously, the capture does not wait for `seeked`.
  (`hf-seek` carries `e.detail.waitUntil(promise)` in 0.8.156 - an async route, untested for video.)
- Use: frames at the film's fps (`ffmpeg -i clip.mp4 -vf "fps=30,scale=960:-1" seq/%04d.jpg`), all loaded
  in the build with `createImageBitmap(blob, { imageOrientation: "flipY" })` and `texture.flipY = false`;
  swap `texture.image` by `index = frame - sectionStartFrame`. Burn the source frame number into a test
  copy to verify the index (105 frames, 960x540).
- Traps: GPU memory (1080p RGBA ~8 MB per frame): downscale, crop, or KTX2 arrays. Flat footage that needs
  no 3D stays a HyperFrames DOM video clip.

### 10.6 Compressed textures (KTX2/Basis) - `proven (models reel)`
ETC1S for colour, UASTC for normals; on the GPU path ETC1S → ETC2, UASTC → ASTC 4x4. The saving is GPU
memory, not download size.

---

## 11. Text in 3D

| Text that... | Use | Status |
|---|---|---|
| keeps its size and travels (labels, readouts) | DOM positioned from the projected anchor every frame, faded by facing / ray occlusion; or `CSS2DRenderer` | proven (globe film, data reel, camera-text reel) |
| the camera scales, turns or occludes | SVG/canvas drawn once at high resolution on a plane, `toneMapped: false` | proven (logo film) |
| becomes particles | points sampled from canvas text | proven (particles film) |
| is made of characters | ASCII text cells and shape masks | proven (ASCII film) |
| is a solid object | font outline as SVG → extrusion (2.2), or `TextGeometry` (2.5) | proven (logo film, camera-text reel) |
| is long, any angle, many sizes, wraps on a curve | troika SDF text (2.6) | proven (camera-text reel) |
| runs along a path | a text texture on a strip bent by `Flow` (2.14) | proven (models reel) |

Never resize or `scale()` DOM text every frame (flicker, software-render differences); never
`CSS3DRenderer` (it scales DOM - the same flicker).

---

## 12. Data visualisation

Code: `assets/recipes/data/` (data reel). Label "sample data" when it is.

### 12.1 Globes - `proven (globe film)`
Baked land dots (Fibonacci sampling, antimeridian-safe rasterising), instanced AA dots with a heat input,
draw-on tube arcs, back-face atmosphere, DOM labels with leaders and facing fade, a spherical rig.

### 12.2 Bars and spikes - `proven (data reel)`
`InstancedMesh` boxes translated to stand on y = 0, height via `setMatrixAt` scale-y from t, `setColorAt`
once; the growth wave starts before the section so frame 0 is not a flat grid; camera clearance checked
against every bar at every frame in the build; DOM labels faded by 5-ray occlusion.

### 12.3 Flat and extruded maps - `proven (data reel)`
`build-map.mjs` (TopoJSON, per-ARC simplification so neighbours share borders, outlying polygons dropped,
equirectangular projection) → ground drawn once into a 4096 px canvas → `ExtrudeGeometry` per country with
holes, height = `scale.y` from t → borders on the tops by a mask in `onBeforeCompile`. ~8% of the map width
is the tallest extrusion that still reads as a map.

### 12.4 Networks and graphs - `proven (data reel)`
Layout by d3-force in the build (section 8); nodes as instanced spheres popping when their edge lands;
edges as unit cylinders via `setMatrixAt`, drawn on in BFS order with an accent head.

### 12.5 Terrain from data - `proven (ASCII film: noise; data reel: a spectrogram)`
160 x 240 log-frequency spectrogram as heights (CPU displacement, normals, px-wide contours), a rail
checked against the heights. Interpolate magnitudes at bin centres (narrow log bins repeat one FFT bin as
stairs); 4096-point STFT.

---

## 13. Compositing with DOM, GSAP and footage

All `proven (camera-text reel)` unless noted; wiring in `assets/recipes/compositing/`.

- **Transparent canvas over a CSS ground** (`alpha: true`, clear alpha 0) - `proven (logo film)`.
- **DOM labels over the canvas**, projected in the same `renderAt` - `proven (globe film, data reel)`; DOM over WebGL
  may differ by ≤ 2 levels between workers (invisible). `CSS2DRenderer` labels - proven (translate only).
- **Canvas under DOM layers animated by a GSAP timeline**: GSAP owns the DOM, `hf-seek` the canvas; a GSAP
  ring and a three square on one rail stayed 0.00 px apart in all 120 frames.
- **Transparent canvas over footage** (a DOM `<video>` clip below).
- **A 3D layer as a sub-composition**: `hf-seek` carries ROOT time - `hostStart()`; the file starts with
  `<template>`; `data-no-timeline` on the host.
- **Alpha export**: `-c layer.html --format webm` (VP9 alpha, 4.5 MB for 3.6 s) or `--format mov` (ProRes
  4444, 186 MB); straight alpha, no fringe; additive glows keep their alpha.
- Marks that must match DOM coordinates: an ortho pixel-space overlay scene.

---

## 14. Audio-driven visuals

- **Precomputed envelopes** - `proven (particles film)`: RMS per 20 ms from a build script, sampled at t.
- **Bands, onsets, waterfalls** - `proven (data reel)`: 24 log bands per 10 ms, each normalised to its own
  8th-99th percentile (one global dB scale barely moves), attack/release run offline; onsets from spectral
  flux REFINED to the attack (flux comes ~17 ms early): 13/15 beats within 30 ms, median 7 ms. A waterfall
  row r shows the spectrum at `(floor(s/dt) - r)·dt` - the past as a pure function of t (features from an
  offline script you write, baked into a JS data file; details in `assets/recipes/data/README.md`).
- **Never** analyse audio live (`AnalyserNode` is real time and stateful).
- The law (video-studio laws.md): **motion has a cause** - audio drives only what the picture is about.
```js
const env = [/* RMS per BIN s */], BIN = 0.02;
const envAt = (s) => { const x = Math.max(0, s / BIN), i = Math.floor(x), f = x - i;
  return lerp(env[Math.min(i, env.length - 1)] ?? 0, env[Math.min(i + 1, env.length - 1)] ?? 0, f); };
```

---

## 15. WebGPU, TSL and node materials

Code and rules: `assets/recipes/webgpu/`, `contract.md` (WebGPU part).

### 15.1 WebGPURenderer for a whole film - `proven (WebGPU reel)`
- 42 s, 9 sections on the WebGPU backend (adapter apple / metal-3), bit-identical across worker counts
  once the page (a) calls `renderer._nodes.nodeFrame.update()` per seek (private API), (b) rebinds TSL
  `time`/`deltaTime` to film time, (c) drives `bloom()` through its own uniforms.
- Hardware GPU only: on SwiftShader three silently falls back to WebGL 2 - check `isWebGPUBackend` AND put
  `data-requires-webgpu` on the root (a rejected hold alone renders a blank film, exit 0).
- It tone-maps the whole frame, background included (#07090b → (0, 2, 4) vs WebGL's (7, 9, 11)).
- Points are 1 px: instanced `Sprite` + `sizeNode`, `alphaToCoverage = false`.

### 15.2 TSL and node materials - `proven (WebGPU reel)`
`MeshStandardNodeMaterial` with `colorNode`, `roughnessNode`, `emissiveNode`, `positionNode` (fractal
noise marbling, fwidth-antialiased contour veins, fresnel, displacement) from a uniform set from t.
Look the same as WebGL materials (54.9 dB on lit objects).

### 15.3 Node post-processing (`three/addons/tsl/display/`) - `proven, partial (WebGPU reel)`: `bloom`, `dof`, `anamorphic`, `chromaticAberration`, `film`, `transition`
- `bloom()` copies passed uniforms - drive `bl.strength.value`. `anamorphic()` sums 48 samples
  unnormalised and tints blue - threshold 2.5, gain ~0.05, own `colorNode`. `dof()` shows its dotted kernel
  on small bright props at `bokehScale` 20. `film()` needs TSL `time` rebound. `transition()` with a seeded
  CPU fbm `DataTexture`. One `PostProcessing` per look, built once.
- `never`: `TRAANode`, `AfterImageNode` (history), velocity `MotionBlur` (previous matrices).

### 15.4 When to choose WebGPU
Only for what WebGL 2 cannot do - scatter writes: millions of points as density, X-ray or nebula looks via
compute + `atomicAdd` (16M in 14 ms, 64M in 54 ms, order-independent, bit-exact), or compute results that
several passes reuse - AND rendered on a GPU machine. Closed-form particles under ~8M, materials and post
look the same on WebGL 2, which also renders on SwiftShader. Software WebGPU is 100-1000x too slow.

---

## 16. Assets and sources

Load everything in the build, from the film's own `assets/` (CDN only for three and pinned libraries).
Free assets from the sources below are a good start. Check each file's licence before it goes into a
deliverable (CC0 where you can; many Sketchfab models carry attribution or non-commercial terms). Write
one line per downloaded file in the film's notes with its source and licence, so it can be found,
credited or swapped later.

| Source | What |
|---|---|
| Kenney (kenney.nl) | low-poly models, kits, UI, fonts, sounds |
| Quaternius (quaternius.com) | low-poly models, rigged animated characters |
| Poly Haven (polyhaven.com) | HDRIs, PBR textures, scanned models (CDN with CORS) |
| ambientCG (ambientcg.com) | PBR materials, HDRIs |
| Khronos glTF-Sample-Assets | test models (Fox: a fully skinned walk), material showcases |
| three.js repo / npm package (r181) | example models (RobotExpressive), fonts, LUTs, textures |
| world-atlas (npm, jsdelivr) | country and land TopoJSON (Natural Earth) |
| Poly Pizza, Smithsonian Open Access 3D, Sketchfab | models, scans |
| Google Fonts, JetBrains Mono | fonts for atlases and canvas text |

---

## 17. Seek-safety cheat sheet

| Not seek-safe as written | Instead |
|---|---|
| `requestAnimationFrame`, `setAnimationLoop`, `Clock`, `performance.now()`, `Date.now()` | `renderAt(t)` on `hf-seek` |
| measured times (`performance.now()`) in on-screen text | only build-invariant numbers (counts, sizes) |
| `Math.random()` (yours or in a constructor: SSAO, GTAO, `DenoiseNode`, `MeshSurfaceSampler`, `SimplexNoise`) | mulberry32; `withSeed()` around constructors; `setRandomGenerator(rng)` |
| `x += speed` anything; float comparisons for cuts | x = f(t); cuts and sections on integer frames |
| `composer.render()` without an argument | `composer.render(0)`; time uniforms from t |
| `FilmPass` with `time = t` (grain repeats every second) | `uniforms.time.value = hash01(frame)` |
| `GlitchPass`, `AfterimagePass`, `TAARenderPass` accumulate, `SSRPass` `bouncing: true`, `TRAANode`, `AfterImageNode` | `DigitalGlitch` with seeded per-frame values; past states from t; `bouncing: false` |
| `OutlinePass.pulsePeriod > 0`; `OutlineEffect.render()` (never clears) | `edgeStrength` from t; `HullRenderPass` (clear + render + `renderOutline()`) |
| `SMAAPass` rendered before its lookup images load | `await whenImagesReady([...])` before the hold |
| `SSRPass`, `SAOPass`, `GTAOPass` built before the final FOV/aspect; an animated FOV with them | set the projection first; no FOV animation under SSR/SAO |
| changing `renderer.shadowMap.type` | `needsUpdate = true` on every material when it changes |
| `LightProbeGenerator` per frame (async) | SH baked at keys in the build, lerped by t |
| `AnimationMixer` + a rest-pose reset or other foreign write between updates | absolute action times and weights, `mixer.update(0)`, undo list (`pose()`) |
| `LoopOnce` + `mixer.setTime(t)`; `crossFadeTo` | `action.time` clamped, `enabled = true`, `paused = false`; weights from t |
| culling on skinned, Flow, instanced, VAT meshes | `frustumCulled = false` |
| `Flow.moveAlongCurve`; default `spineOffset` (161) | `pathOffset = f(t)` (0..1); `spineOffset = 0` |
| troika: changing `text` or font at seek time | build every text and await `sync()` in the build; animate opacity, curve, transforms |
| `VideoTexture` | image sequence indexed by frame (10.5) |
| physics stepping in the page; `GPUComputationRenderer` stepping once per seek; d3-force's own timer | bake (8); replay from frame 0 or bake into array layers (7.6); `.stop()` + `tick(n)` |
| TSL `time` / `deltaTime` (wall clock) | `time.onRenderUpdate(() => FILM_T)`, `deltaTime.onRenderUpdate(() => 1 / FPS)` |
| node post without a new node frame per seek | `renderer._nodes.nodeFrame.update()` at the top of `renderAt` (private API) |
| `bloom(input, uStrength ...)` with your own uniforms | `const bl = bloom(...)`; `bl.strength.value = f(t)` |
| `hf-seek` time inside a sub-composition | `t - hostStart(el)` |
| fetching anything at seek time; fonts not awaited | everything loaded before the build hold resolves |
| float `sin` hashes for decisions; TSL `hash(i + 2^k)` streams | integer (`uint`) hashes; `hash(4i + j)`; steps from the frame index |
| an exception inside `renderAt` (silent stale canvas) | try/catch, log, clear to magenta |
| WebGPU on SwiftShader | `isWebGPUBackend` check + `data-requires-webgpu`, render `--browser-gpu` |
