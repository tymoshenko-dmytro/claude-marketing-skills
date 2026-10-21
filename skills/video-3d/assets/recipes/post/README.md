# Post-processing chain - AO, depth of field, AA, grain, grades, LUT, glitch, SSR, motion blur

Proven in a test film (the post reel: 44.5 s, 12 sections; auto, `--workers 4` and `--workers 1` decode
to 1,335/1,335 identical frames). `post-kit.js` here is that film's file, unchanged.

## What is in post-kit.js

- `rng(seed)`, `withSeed(seed, make)` - construct a pass that calls `Math.random()` in its constructor with a
  seeded generator (SSAOPass kernel + noise, GTAOPass denoise noise). Unseeded: 0/210 frames identical between
  worker counts, a visible step at the chunk boundary.
- `hashU32`, `hash01` - integer hash for per-frame CPU decisions (grain time, glitch).
- `whenImagesReady([smaa._areaTexture, smaa._searchTexture])` - SMAAPass loads lookup images from data URLs
  and renders wrong until they load (22,318 pixels differed); await before resolving the hold.
- `SubframeMotionBlurPass(scene, camera, { samples: 16, shutter: 0.5 / fps, setTime, width, height })` -
  replaces RenderPass; renders the world at N times inside the shutter and sums them 1/N each. `setTime(t)`
  must put the WHOLE world (objects, camera, shadows) at that time. 16 samples = 31.9 ms per frame.
- `Presenter` - copies composer results to canvas rectangles 1:1 (`texelFetch`) with a static +-1 LSB dither
  while values are still HalfFloat: wipes, tiles and before/after splits; `solid()` for dividers.
- `seededDispTexture(seed)` + `glitchSchedule({ seed, firstFrame, lastFrame, bursts })` - `DigitalGlitch`
  driven by the frame index (`GlitchPass` stays never).

## Chain (one composer, passes added once, `enabled` set absolutely every frame)

```js
camera.updateProjectionMatrix();          // SSRPass, SAOPass (and GTAOPass in setSize) COPY the projection now
main = new EffectComposer(renderer, new THREE.WebGLRenderTarget(W, H, { type: THREE.HalfFloatType, samples: 4 }));
// order: render | motion blur | ssr -> ssao | gtao | sao -> bokeh -> OutputPass -> lut, grades, vignette, rgb shift, film, glitch
P.ssr = new SSRPass({ renderer, scene, camera, width: W, height: H, selects: [floor] });
P.ssr.beautyRenderTarget.samples = 4;    // else SSR frames are aliased in an MSAA chain; keep bouncing = false
P.ssao = withSeed(SEED + 5, () => new SSAOPass(scene, camera, W, H, 32));
Object.assign(P.ssao, { kernelRadius: 0.6, minDistance: 0.0003, maxDistance: 0.02 });   // fractions of (far - near)!
P.gtao = withSeed(SEED + 6, () => new GTAOPass(scene, camera, W, H));
P.gtao.updateGtaoMaterial({ radius: 0.9, scale: 2.2, samples: 16 });                    // scale = strength (ao^scale)
P.sao = new SAOPass(scene, camera, new THREE.Vector2(W, H));
Object.assign(P.sao.params, { saoIntensity: 0.05, saoScale: 2, saoKernelRadius: 50 });  // 0.25 draws halos
P.bokeh = new BokehPass(scene, camera, { focus: 8, aperture: 0.005, maxblur: 0.015 });  // blur <= ~11 px
lutLoader.setType(THREE.FloatType);       // LUTCubeLoader's default UnsignedByte truncates
P.film = new FilmPass(0.45, false);
function runMain(on) { for (const k of ORDER) P[k].enabled = on.includes(k); main.render(0); return main.readBuffer.texture; }
// per frame, from t:
P.bokeh.uniforms.focus.value = lerp(viewDepth(near), viewDepth(far), k);   // viewDepth = -(viewMatrix * p).z
P.film.uniforms.time.value = hash01(frame, SEED);                          // NOT t: the grain repeats every second
P.vignette.uniforms.offset.value = ramp;  P.vignette.uniforms.darkness.value = 1;   // darkness 0 is white, not off
Object.assign(P.glitch.uniforms, ...)     // from glitchSchedule().uniforms(frame), each value .value = x
```

Shadow maps: with passes that re-render the scene (SSAO normals, Bokeh depth, SSAA x16, sub-frames x16) set
`renderer.shadowMap.autoUpdate = false` and `shadowMap.needsUpdate = true` once per frame in `world(t)`.
AO needs a mid-dark floor: a multiply on near-black shows nothing. TAARenderPass with `accumulate = false` is
pixel-identical to SSAARenderPass at the same `sampleLevel` (and its default level 0 is one sample) - use SSAA.

## Cost (ms per 1080p frame, M1 Max ANGLE Metal, chain incl. OutputPass)

Render + Output (MSAA x4) 2.63 | + SSAO 4.53 | + GTAO 7.82 | + SAO 4.47 | + Bokeh 3.62 | SSR 14.72 |
motion blur x16 31.87 | AA chain without MSAA 1.27, + FXAA 1.44, + SMAA 1.49, SSAA x16 8.74 | + Film 3.22 |
+ LUT 3.79 | + Vignette + RGBShift 4.50. A display-space ShaderPass ~0.6 ms on MSAA HalfFloat targets.
AA quality (RMSE vs SSAA x16): none 7.58, FXAA 6.60, SMAA 4.77.
Bitrate at CRF 10: film grain 156 Mbit/s, glitch 73, everything else 10-17 (the present dither roughly
doubles clean sections). The CRF 10 encode, not the GPU, bounds render time.
