// video-3d post kit (from the post reel) - reusable, seek-safe post-processing helpers.
// Everything here is a pure function of its inputs: no clock, no Math.random at render time.
import * as THREE from "three";
import { Pass, FullScreenQuad } from "three/addons/postprocessing/Pass.js";

// ---- seeded randomness ---------------------------------------------------------------------
export function rng(seed) {                                    // mulberry32
  let a = seed >>> 0;
  return () => { a = (a + 0x6d2b79f5) >>> 0; let t = a;
    t = Math.imul(t ^ (t >>> 15), t | 1); t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296; };
}
// Construct a pass that calls Math.random() in its constructor (SSAOPass kernel + noise,
// GTAOPass denoise noise via SimplexNoise(Math)) with a seeded generator, then restore.
export function withSeed(seed, make) {
  const keep = Math.random; Math.random = rng(seed);
  try { return make(); } finally { Math.random = keep; }
}
// integer hash (pcg-style) -> [0, 1); for per-frame decisions computed on the CPU
export function hashU32(a, b = 0) {
  let h = (Math.imul(a >>> 0, 747796405) + 2891336453 + Math.imul(b >>> 0, 1664525)) >>> 0;
  h = Math.imul((h >>> ((h >>> 28) + 4)) ^ h, 277803737) >>> 0;
  return ((h >>> 22) ^ h) >>> 0;
}
export const hash01 = (a, b = 0) => hashU32(a, b) / 4294967296;

// ---- async textures inside passes ------------------------------------------------------------
// SMAAPass loads its area/search lookup textures from data-URL <img>s and sets needsUpdate in
// onload. Await them before resolving the build hold, or early frames render without them.
export async function whenImagesReady(textures) {
  await Promise.all(textures.map((tex) => {
    const img = tex.image;
    const done = () => { tex.needsUpdate = true; };
    if (img.complete && img.naturalWidth > 0) { done(); return Promise.resolve(); }
    return new Promise((res, rej) => {
      img.addEventListener("load", () => { done(); res(); }, { once: true });
      img.addEventListener("error", rej, { once: true });
    });
  }));
}

// ---- motion blur by sub-frame accumulation -----------------------------------------------------
// Replaces RenderPass. Renders the world at N times inside the shutter, centred on t, each into a
// (multisampled) HalfFloat target, and adds them into the composer's read buffer with weight 1/N.
// setTime(time) must put the WHOLE world (objects, camera, shadows) at that time; the pass puts it
// back at `this.time` when done. Deterministic: only t is read. Costs N scene renders.
export class SubframeMotionBlurPass extends Pass {
  constructor(scene, camera, { samples = 16, shutter = 0.5 / 30, setTime, width, height, msaa = 4 }) {
    super();
    this.scene = scene; this.camera = camera; this.samples = samples; this.shutter = shutter;
    this.setTime = setTime; this.time = 0; this.needsSwap = false;
    this._rt = new THREE.WebGLRenderTarget(width, height, { type: THREE.HalfFloatType, samples: msaa });
    this._mat = new THREE.ShaderMaterial({
      uniforms: { tDiffuse: { value: null }, weight: { value: 1 } },
      vertexShader: "varying vec2 vUv; void main(){ vUv = uv; gl_Position = vec4(position.xy, 0.0, 1.0); }",
      fragmentShader: "uniform sampler2D tDiffuse; uniform float weight; varying vec2 vUv;" +
        "void main(){ gl_FragColor = texture2D(tDiffuse, vUv) * weight; }",
      // ONE, ONE: plain sum (AdditiveBlending would multiply by src alpha a second time)
      blending: THREE.CustomBlending, blendSrc: THREE.OneFactor, blendDst: THREE.OneFactor,
      blendEquation: THREE.AddEquation, blendSrcAlpha: THREE.OneFactor, blendDstAlpha: THREE.OneFactor,
      depthTest: false, depthWrite: false, transparent: true,
    });
    this._quad = new FullScreenQuad(this._mat);
  }
  // sub-frame times for frame time t (exposed for QA)
  times(t) {
    const n = Math.max(1, this.samples | 0), out = [];
    for (let i = 0; i < n; i++) out.push(t + ((i + 0.5) / n - 0.5) * this.shutter);
    return out;
  }
  setSize(w, h) { this._rt.setSize(w, h); }
  render(renderer, writeBuffer, readBuffer) {
    const ts = this.times(this.time), w = 1 / ts.length;
    const keepAuto = renderer.autoClear; renderer.autoClear = false;
    const keepColor = renderer.getClearColor(new THREE.Color()), keepAlpha = renderer.getClearAlpha();
    const dst = this.renderToScreen ? null : readBuffer;
    renderer.setRenderTarget(dst); renderer.setClearColor(0x000000, 0); renderer.clear();
    this._mat.uniforms.tDiffuse.value = this._rt.texture; this._mat.uniforms.weight.value = w;
    for (const ti of ts) {
      this.setTime(ti);
      renderer.setRenderTarget(this._rt); renderer.setClearColor(keepColor, keepAlpha); renderer.clear();
      renderer.render(this.scene, this.camera);
      renderer.setRenderTarget(dst);
      this._quad.render(renderer);                              // += sub-frame / N
    }
    this.setTime(this.time);                                    // leave the world at t
    renderer.setClearColor(keepColor, keepAlpha); renderer.autoClear = keepAuto;
  }
}

// ---- presenting composer results to the canvas -------------------------------------------------
// Copies texels 1:1 (texelFetch, no filtering, no colour conversion) from a texture into a screen
// rectangle; src offset lets one region of a frame be shown elsewhere (side-by-side 1:1 crops).
// Values are written as they are: present a texture that already went through OutputPass.
export class Presenter {
  constructor(renderer, width, height) {
    this.renderer = renderer; this.W = width; this.H = height;
    this.mat = new THREE.ShaderMaterial({
      uniforms: { tSrc: { value: null }, uOffset: { value: new THREE.Vector2() },
        uSolid: { value: new THREE.Vector4() }, uUseSolid: { value: 0 }, uDither: { value: 1 } },
      vertexShader: "void main(){ gl_Position = vec4(position.xy, 0.0, 1.0); }",
      // + a static +-1 LSB triangular dither from an integer hash of the pixel, applied while the
      // values are still HalfFloat: the 8-bit canvas otherwise bands the dark floor gradients
      fragmentShader: "uniform sampler2D tSrc; uniform vec2 uOffset; uniform vec4 uSolid; uniform float uUseSolid; uniform float uDither;" +
        "void main(){ if (uUseSolid > 0.5) { gl_FragColor = uSolid; return; }" +
        " ivec2 p = ivec2(floor(gl_FragCoord.xy + uOffset)); vec3 c = texelFetch(tSrc, p, 0).rgb;" +
        " uvec2 q = uvec2(gl_FragCoord.xy); uint h = q.x * 1973u + q.y * 9277u + 26699u;" +
        " h ^= h >> 15; h *= 0x2c1b3c6du; h ^= h >> 12; h *= 0x297a2d39u; h ^= h >> 15;" +
        " float d = float(h & 65535u) / 65535.0 + float(h >> 16) / 65535.0 - 1.0;" +
        " gl_FragColor = vec4(c + uDither * d / 255.0, 1.0); }",
      depthTest: false, depthWrite: false, blending: THREE.NoBlending,
    });
    this.quad = new FullScreenQuad(this.mat);
  }
  _rect(x, y, w, h) {
    const r = this.renderer;
    r.setRenderTarget(null); r.setViewport(0, 0, this.W, this.H);
    r.setScissorTest(true); r.setScissor(x, y, w, h);
    this.quad.render(r); r.setScissorTest(false);
  }
  // x, y in GL pixels (y up). srcX/srcY: where in the texture this rect's first pixel comes from.
  region(tex, x, y, w, h, srcX = x, srcY = y) {
    this.mat.uniforms.uUseSolid.value = 0; this.mat.uniforms.tSrc.value = tex;
    this.mat.uniforms.uOffset.value.set(srcX - x, srcY - y);
    this._rect(x, y, w, h);
  }
  // a solid rectangle in display values (hex parsed directly, no colour management)
  solid(hex, x, y, w, h) {
    const c = parseInt(hex.replace("#", ""), 16);
    this.mat.uniforms.uUseSolid.value = 1;
    this.mat.uniforms.uSolid.value.set(((c >> 16) & 255) / 255, ((c >> 8) & 255) / 255, (c & 255) / 255, 1);
    this._rect(x, y, w, h);
  }
}

// ---- seek-safe glitch: DigitalGlitch driven by the frame index ---------------------------------
// A seeded 64x64 displacement map (GlitchPass builds it with MathUtils.randFloat = Math.random).
export function seededDispTexture(seed, size = 64) {
  const r = rng(seed), data = new Float32Array(size * size);
  for (let i = 0; i < data.length; i++) data[i] = r();
  const tex = new THREE.DataTexture(data, size, size, THREE.RedFormat, THREE.FloatType);
  tex.needsUpdate = true;
  return tex;
}
// Bursts placed once from a seed; every uniform for a frame is a hash of (seed, frame, k).
// Returns uniforms(frame) -> { byp, amount, angle, seed, seed_x, seed_y, distortion_x, distortion_y }.
export function glitchSchedule({ seed, firstFrame, lastFrame, bursts = 5, minLen = 2, maxLen = 6 }) {
  const r = rng(seed), span = lastFrame - firstFrame, list = [];
  for (let i = 0; i < bursts; i++) {
    const slot = span / bursts, start = Math.round(firstFrame + slot * (i + 0.15 + 0.6 * r()));
    list.push({ start, end: start + minLen + Math.floor(r() * (maxLen - minLen + 1)) });
  }
  const H = (frame, k) => hash01(frame + 7919 * k, seed);
  const uniforms = (frame) => {
    const b = list.find((x) => frame >= x.start && frame < x.end);
    const near = list.find((x) => frame >= x.start - 1 && frame < x.end + 1);   // a weak flicker either side
    if (b) return { byp: 0, amount: H(frame, 1) / 45, angle: (H(frame, 2) * 2 - 1) * Math.PI,
      seed: H(frame, 3), seed_x: H(frame, 4) * 2 - 1, seed_y: H(frame, 5) * 2 - 1,
      distortion_x: H(frame, 6), distortion_y: H(frame, 7) };
    if (near) return { byp: 0, amount: H(frame, 1) / 150, angle: (H(frame, 2) * 2 - 1) * Math.PI,
      seed: H(frame, 3), seed_x: (H(frame, 4) * 2 - 1) * 0.3, seed_y: (H(frame, 5) * 2 - 1) * 0.3,
      distortion_x: H(frame, 6), distortion_y: H(frame, 7) };
    return { byp: 1, amount: 0, angle: 0, seed: 0, seed_x: 0, seed_y: 0, distortion_x: 0, distortion_y: 0 };
  };
  return { list, uniforms };
}
