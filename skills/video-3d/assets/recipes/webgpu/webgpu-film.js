// video-3d: the pieces a WebGPURenderer film needs in HyperFrames (from the WebGPU reel's scene module,
// three 0.181.2). Import map: "three" and "three/webgpu" -> build/three.webgpu.js, "three/tsl" ->
// build/three.tsl.js, "three/addons/" -> examples/jsm/. Put data-requires-webgpu on the composition root.
import * as THREE from "three/webgpu";
import {
  Fn, If, Return, uniform, float, uint, vec4, uvec2, instanceIndex, instancedArray,
  atomicAdd, atomicStore, atomicLoad, textureStore, time, deltaTime, hash, screenCoordinate,
} from "three/tsl";

// ---- 1. film time for every TSL clock --------------------------------------------------------------
// TSL `time` / `deltaTime` read performance.now() (FilmNode grain, oscSine(), mx_timer(), addons that
// animate). Rebind them ONCE at module top; then set the film time before each frame.
export function filmClock(fps) {
  let T = 0;
  time.onRenderUpdate(() => T);
  deltaTime.onRenderUpdate(() => 1 / fps);
  return { set: (t) => { T = t; }, get: () => T };
}

// ---- 2. WebGPU or nothing ----------------------------------------------------------------------------
// Without a hardware adapter (--no-browser-gpu, Docker, Lambda) three SILENTLY falls back to WebGL 2.
// Reject the build hold - and keep data-requires-webgpu on the root: a rejected hold alone still
// renders a blank film with exit 0.
export async function requireWebGPU(renderer) {
  await renderer.init();
  if (!renderer.backend.isWebGPUBackend) throw new Error("WebGPU backend unavailable (WebGL 2 fallback): render with --browser-gpu on a GPU machine");
  return renderer.backend.device;
}

// ---- 3. the seek driver --------------------------------------------------------------------------------
// renderFrame(t) sets everything from t and renders (post.render(), renderer.compute(...)).
// - a NEW NODE FRAME per seek: node post (pass(), bloom(), dof() ...) re-renders its targets once per node
//   frame, and three r181 advances that counter only in its own requestAnimationFrame loop - two seeks in one
//   browser frame reuse the first one's targets (stale frames: 1109 of 1260 differed in a 4-worker render).
//   `renderer._nodes.nodeFrame.update()` is a PRIVATE API: re-check it on any three upgrade.
// - hands device.queue.onSubmittedWorkDone() to e.detail.waitUntil (HyperFrames 0.8.156 awaits it);
// - same t again = no work: with data-requires-webgpu the runtime re-dispatches the last seek every 250 ms
//   while paused, which would re-run a heavy frame under the screenshot;
// - an exception clears to magenta and is logged (a silent stale canvas is worse).
export function seekDriver({ renderer, clock, renderFrame, duration }) {
  const info = (window.__info ||= {}), errors = (info.errors ||= []);
  let lastT = null, lastDone = null, ready = false;
  function renderAt(t) {
    if (!ready) return null;
    t = Math.max(0, Math.min(duration - 1e-6, Number(t) || 0));
    if (t === lastT) return lastDone;
    clock.set(t);
    renderer._nodes.nodeFrame.update();
    try { renderFrame(t); }
    catch (err) { errors.push(`t=${t}: ${(err && err.stack) || err}`); console.error(err); renderer.setClearColor(0xff00ff, 1); renderer.clear(); }
    lastT = t; lastDone = renderer.backend.device.queue.onSubmittedWorkDone();
    return lastDone;
  }
  window.addEventListener("hf-seek", (e) => {
    const p = renderAt(e.detail.time);
    if (p && e.detail && typeof e.detail.waitUntil === "function") e.detail.waitUntil(p);
  });
  // warm(times): render each section once in the build so every pipeline compiles before the hold resolves
  return { renderAt, start: () => { ready = true; }, warm: async (times) => { ready = true; for (const t of times) await renderAt(t); lastT = null; } };
}

// ---- 4. display-space dither (+-0.5 LSB, integer hash of the pixel) ------------------------------------
export const dither = () => hash(screenCoordinate.x.add(screenCoordinate.y.mul(4099)).toUint()).sub(0.5).div(255);

// ---- 5. atomic density splat: millions of points into a per-pixel count ---------------------------------
// WebGL has no scatter writes; this is what WebGPU adds for a film. Each point is projected and added with
// bilinear weights in FIXED POINT (/256) by atomicAdd - integer adds commute, so the result is
// order-independent and bit-exact. Measured (M1 Max, 1080p): 16M points 14 ms per frame (clear + splat +
// resolve), 64M 54 ms; 16M Gaussian sprites cost ~170 ms.
//   pointAt(i) -> { position: vec3 node (world), layer?: bool node (true = second buffer) } built from
//   hash(4i + j) streams (NOT hash(i + 2^k): PCG is linear in the seed before mixing, offset streams correlate)
//   shade(n0, n1) -> vec3 node in DISPLAY space from points per pixel (n1 = 0 with one layer)
// Show `texture` with a PostProcessing whose outputColorTransform = false:
//   post = new THREE.PostProcessing(renderer, vec4(texture(splat.texture, screenUV).rgb.add(dither()), 1)); post.outputColorTransform = false;
export function densitySplat({ width: W, height: H, count: N, pointAt, shade, layers = 1 }) {
  const NB = W * H;
  const dens = Array.from({ length: layers }, () => instancedArray(NB, "uint").toAtomic());
  const tex = new THREE.StorageTexture(W, H); tex.type = THREE.HalfFloatType;
  const viewProj = uniform(new THREE.Matrix4());
  const clear = Fn(() => { for (const d of dens) atomicStore(d.element(instanceIndex), uint(0)); })().compute(NB);
  const add4 = (d, base, w00, w10, w01, w11) => {
    atomicAdd(d.element(base), w00); atomicAdd(d.element(base.add(uint(1))), w10);
    atomicAdd(d.element(base.add(uint(W))), w01); atomicAdd(d.element(base.add(uint(W + 1))), w11);
  };
  const splat = Fn(() => {
    const i = instanceIndex;
    // three splits dispatches above 65,535 workgroups into 2D and runs extra invocations: guard every big kernel
    If(i.greaterThanEqual(uint(N)), () => { Return(); });
    const pt = pointAt(i);
    const clip = viewProj.mul(vec4(pt.position, 1.0)).toVar();
    If(clip.w.greaterThan(0.05), () => {
      const ndc = clip.xy.div(clip.w);
      const px = ndc.x.mul(0.5).add(0.5).mul(W).sub(0.5);
      const py = float(1).sub(ndc.y.mul(0.5).add(0.5)).mul(H).sub(0.5);
      const x0 = px.floor(), y0 = py.floor(), fx = px.sub(x0), fy = py.sub(y0);
      If(x0.greaterThanEqual(0).and(y0.greaterThanEqual(0)).and(x0.lessThan(W - 1)).and(y0.lessThan(H - 1)), () => {
        const base = y0.toUint().mul(uint(W)).add(x0.toUint()).toVar();
        const w00 = float(1).sub(fx).mul(float(1).sub(fy)).mul(256).round().toUint();
        const w10 = fx.mul(float(1).sub(fy)).mul(256).round().toUint();
        const w01 = float(1).sub(fx).mul(fy).mul(256).round().toUint();
        const w11 = fx.mul(fy).mul(256).round().toUint();
        if (layers > 1 && pt.layer) If(pt.layer, () => add4(dens[1], base, w00, w10, w01, w11)).Else(() => add4(dens[0], base, w00, w10, w01, w11));
        else add4(dens[0], base, w00, w10, w01, w11);
      });
    });
  })().compute(N);
  const resolve = Fn(() => {
    const i = instanceIndex, x = i.mod(uint(W)), y = i.div(uint(W));
    const n = dens.map((d) => atomicLoad(d.element(i)).toFloat().div(256));
    textureStore(tex, uvec2(x, y), vec4(shade(n[0], n[1] ?? float(0)), 1.0));
  })().compute(NB);
  // per frame: camera from t, then splat.run(renderer, camera), then post.render()
  const run = (renderer, camera) => {
    camera.updateMatrixWorld(); camera.updateProjectionMatrix();
    viewProj.value.multiplyMatrices(camera.projectionMatrix, camera.matrixWorldInverse);
    renderer.compute(clear); renderer.compute(splat); renderer.compute(resolve);
  };
  return { texture: tex, viewProj, clear, splat, resolve, run };
}
