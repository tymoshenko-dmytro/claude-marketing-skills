# A WebGPU film - node frame, film clock, compute, atomic density

Proven in a test film (the WebGPU reel: 42 s, 9 sections on `WebGPURenderer`: TSL material,
`bloom`, `dof`, `anamorphic` + `chromaticAberration` + `film`, `transition`, 2M compute particles, 16M points
by `atomicAdd`, WebGL vs WebGPU split; six full renders bit-identical across worker counts).
`webgpu-film.js` collects that film's set-up into functions. The film's own scene module was the rendered
version; this file is syntax-checked and its nodes build in Node (the kernels are the film's, with its torus
knot replaced by `pointAt` / `shade` callbacks).

## Set-up

```html
<div id="root" data-composition-id="main" ... data-no-timeline data-requires-webgpu>
<script type="importmap">{ "imports": {
  "three": "https://cdn.jsdelivr.net/npm/three@0.181.2/build/three.webgpu.js",
  "three/webgpu": "https://cdn.jsdelivr.net/npm/three@0.181.2/build/three.webgpu.js",
  "three/tsl": "https://cdn.jsdelivr.net/npm/three@0.181.2/build/three.tsl.js",
  "three/addons/": "https://cdn.jsdelivr.net/npm/three@0.181.2/examples/jsm/" } }</script>
```

```js
import { filmClock, requireWebGPU, seekDriver, densitySplat, dither } from "./webgpu-film.js";
const clock = filmClock(30);                         // module top: TSL time/deltaTime = film time
const renderer = new THREE.WebGPURenderer({ canvas, antialias: false });
renderer.setPixelRatio(2); renderer.setSize(1920, 1080, false);
const drive = seekDriver({ renderer, clock, duration: DUR, renderFrame });   // renderFrame(t): everything from t
async function build() {
  const device = await requireWebGPU(renderer);    // rejects the hold on a WebGL 2 fallback
  /* scenes, PostProcessing objects (built ONCE), compute nodes; renderer.compute(init) */
}
```
Then, at the end of `build()`: `await drive.warm(sectionMidTimes)` (every pipeline compiles in the build),
`await drive.renderAt(window.__hfThreeTime || 0)`, resolve the hold.

## Rules the film found (all in `contract.md`, WebGPU part)

- `renderer._nodes.nodeFrame.update()` at the top of every frame - PRIVATE API, re-check on any three upgrade
  (without it 1,109 of 1,260 frames of a 4-worker render were stale).
- `bloom()` copies the uniforms you pass: drive `const bl = bloom(...); bl.strength.value = f(t)`. `dof()`,
  `anamorphic()`, `chromaticAberration()`, `film()`, `transition()` use the node you pass.
- `anamorphic()` sums 48 samples unnormalised and tints blue: threshold above lit surfaces (2.5), gain ~0.05,
  `an.colorNode = vec3(...)` from the film.
- `WebGPURenderer` tone-maps the whole frame including the background ((0, 2, 4) for #07090b where WebGL gives
  (7, 9, 11)): pre-compensate or draw the ground as a node, and measure.
- Points are 1 px: use an instanced `Sprite` (`sprite.count = N`, `positionNode = storage.toAttribute()`,
  `sizeNode` in CSS px) with `alphaToCoverage = false` for additive splats.
- Hash streams `hash(4i + j)`; guard big kernels (`If(instanceIndex >= N) Return()`); storage buffers above
  128 MiB need `requiredLimits` from `adapter.limits`.
- A transition between two scene passes + 2M particles varied in ~1 frame of 600 at 73 dB: compare PNGs of a
  differing frame before calling the film non-deterministic.

## When WebGPU is worth it

Counts: compute + `atomicAdd` draws 16M points in 14 ms and 64M in 54 ms (sprites: 16M in ~170 ms; WebGL has
no scatter writes). For closed-form particles under ~8M a WebGL vertex shader is within 1.0-1.5x, and TSL
materials and node post look the same as WebGL (54.9 dB on lit objects) - stay on WebGL 2, which also renders
on SwiftShader. Software WebGPU (`PRODUCER_ALLOW_SOFTWARE_WEBGPU=true`) builds but runs 100-1000x too slow.
The numbers above come from a bench page made for the WebGPU reel (WebGPU compute vs a WebGL vertex shader,
atomic splat). It does not ship: for numbers on your GPU, time the same three cases in a one-page
bench of your own.
