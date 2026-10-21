// video-3d look passes (from the styles reel) - reusable look passes for an EffectComposer (three 0.181.2).
// Every pass here is seek-safe: no clock, no Math.random, nothing carried between frames; stepped
// effects (flicker, boil) take an integer step computed on the CPU from the frame index.
//
// Film pixels vs target pixels: the film composer runs at pixel ratio 2 (edges supersampled). A pass
// that works on a pixel grid (dither, CRT mask, paper grain, hatching) computes its grid in FILM
// pixels: fp = floor(gl_FragCoord.xy / uPR), uPR = target width / 1920 (1 when it renders to the
// screen, 2 inside a supersampled target), and samples its input at film-pixel centres - in a 2x
// target that one bilinear tap is the exact 2x2 box average. So the same pass gives the same grid
// whether it is the last pass (to the canvas) or feeds a wipe (into a 2x target).
import * as THREE from "three";
import { Pass, FullScreenQuad } from "three/addons/postprocessing/Pass.js";

export const FILM = new THREE.Vector2(1920, 1080);

// "#rrggbb" -> display-space vec3, NOT colour-managed (a THREE.Color would be converted to linear)
export function hex3(hex) {
  const h = hex.replace("#", "").trim();
  const n = parseInt(h.length === 3 ? h.split("").map((c) => c + c).join("") : h, 16);
  return new THREE.Vector3(((n >> 16) & 255) / 255, ((n >> 8) & 255) / 255, (n & 255) / 255);
}

// ---- GLSL shared by the passes ----
export const GLSL_COMMON = /* glsl */`
  uniform sampler2D tDiffuse;   // the previous pass (unused by the wipe quad)
  uniform float uPR;            // target px per film px
  uniform vec2 uFilm;           // 1920, 1080
  vec2 filmPx() { return floor(gl_FragCoord.xy / uPR); }               // integer film pixel (origin bottom-left)
  vec2 filmUv(vec2 fp) { return (fp + 0.5) / uFilm; }                 // centre of a film pixel in uv
  float luma(vec3 c) { return dot(c, vec3(0.2126, 0.7152, 0.0722)); }
  // integer hash (pcg): decisions that must match across machines
  uint pcg(uint v) { uint s = v * 747796405u + 2891336453u; uint w = ((s >> ((s >> 28u) + 4u)) ^ s) * 277803737u; return (w >> 22u) ^ w; }
  float hash3(uint x, uint y, uint k) { return float(pcg(x * 73856093u ^ pcg(y * 19349663u ^ pcg(k + 0x9e3779b9u)))) / 4294967295.0; }
  float vnoise(vec2 x, uint k) {            // value noise on an integer lattice (x >= 0)
    vec2 i = floor(x), f = fract(x); f = f * f * (3.0 - 2.0 * f);
    uint ix = uint(i.x), iy = uint(i.y);
    return mix(mix(hash3(ix, iy, k), hash3(ix + 1u, iy, k), f.x), mix(hash3(ix, iy + 1u, k), hash3(ix + 1u, iy + 1u, k), f.x), f.y);
  }
  // Bayer thresholds by bit interleaving (0..1, cell centred)
  float bayer4(ivec2 p) { int x = p.x & 3, y = p.y & 3, a = x ^ y;
    return (float(((a & 1) << 3) | ((x & 1) << 2) | (a & 2) | ((x & 2) >> 1)) + 0.5) / 16.0; }
  float bayer8(ivec2 p) { int x = p.x & 7, y = p.y & 7, a = x ^ y;
    return (float(((a & 1) << 5) | ((x & 1) << 4) | ((a & 2) << 2) | ((x & 2) << 1) | ((a & 4) >> 1) | ((x & 4) >> 2)) + 0.5) / 64.0; }
`;
const VERT = /* glsl */`varying vec2 vUv; void main() { vUv = uv; gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0); }`;

// A ShaderMaterial-backed pass that knows its film-pixel ratio. Subclasses fill uniforms.
export class FilmPixelPass extends Pass {
  constructor(fragmentShader, uniforms, defines = {}) {
    super();
    this.uniforms = { tDiffuse: { value: null }, uPR: { value: 1 }, uFilm: { value: FILM.clone() }, ...uniforms };
    this.material = new THREE.ShaderMaterial({ uniforms: this.uniforms, defines, vertexShader: VERT,
      fragmentShader: GLSL_COMMON + fragmentShader, depthTest: false, depthWrite: false });
    this._quad = new FullScreenQuad(this.material);
  }
  draw(renderer, writeBuffer) {
    const target = this.renderToScreen ? null : writeBuffer;
    this.uniforms.uPR.value = target ? target.width / FILM.x : 1;   // the canvas is 1920 wide at renderer pixel ratio 1
    renderer.setRenderTarget(target);
    if (target && this.clear) renderer.clear();
    this._quad.render(renderer);
  }
  render(renderer, writeBuffer, readBuffer) { this.uniforms.tDiffuse.value = readBuffer.texture; this.draw(renderer, writeBuffer); }
  dispose() { this.material.dispose(); this._quad.dispose(); }
}

// ---- 6.2 inverted hull inside a composer -------------------------------------------------------
// OutlineEffect is written to wrap renderer.render(); in a composer, render the scene into the
// read buffer ourselves (with a clear) and then call effect.renderOutline(). Do NOT call
// effect.render(): it sets renderer.autoClear = effect.autoClear, which is undefined - with no
// scene.background nothing is cleared and the previous frame's colour and depth survive.
export class HullRenderPass extends Pass {
  constructor(scene, camera, effect) { super(); this.scene = scene; this.camera = camera; this.effect = effect; this.needsSwap = false; }
  render(renderer, writeBuffer, readBuffer) {
    const keep = renderer.autoClear; renderer.autoClear = true;
    renderer.setRenderTarget(this.renderToScreen ? null : readBuffer);
    renderer.clear();
    renderer.render(this.scene, this.camera);
    this.effect.renderOutline(this.scene, this.camera);
    renderer.autoClear = keep;
  }
}

// ---- 6.2 Sobel composite: ink where SobelOperatorShader found an edge, over a saved colour ----
export class SobelInkPass extends FilmPixelPass {
  constructor({ tColor, ink, lo = 0.18, hi = 0.45 }) {
    super(/* glsl */`
      uniform sampler2D tColor; uniform vec3 uInk; uniform vec2 uEdge; varying vec2 vUv;
      void main() {
        vec3 col = texture2D(tColor, vUv).rgb;
        float g = texture2D(tDiffuse, vUv).r;                 // Sobel magnitude
        gl_FragColor = vec4(mix(col, uInk, smoothstep(uEdge.x, uEdge.y, g)), 1.0);
      }`, { tColor: { value: tColor }, uInk: { value: hex3(ink) }, uEdge: { value: new THREE.Vector2(lo, hi) } });
  }
}

// ---- 6.4 ordered dither: 1-bit (two inks) or limited palette (two nearest of N) ----------------
export class DitherPass extends FilmPixelPass {
  // mode "1bit": Bayer 8x8 between ink0 and ink1 on luma (levels lo/hi/gamma)
  // mode "palette": Bayer 4x4 between the two nearest palette colours (display RGB)
  constructor({ mode = "1bit", dot = 2, inks = ["#000000", "#ffffff"], palette = [], levels = [0, 1, 1] }) {
    const pal = palette.map(hex3);
    super(/* glsl */`
      uniform float uDot; uniform vec3 uInk0, uInk1; uniform vec3 uLv;
      #if PAL_N > 0
      uniform vec3 uPal[PAL_N];
      #endif
      varying vec2 vUv;
      vec3 dotColour(vec2 d) {                                // exact box average over the dot's film pixels
        vec3 s = vec3(0.0); int n = int(uDot);
        for (int y = 0; y < 4; y++) for (int x = 0; x < 4; x++) {
          if (x >= n || y >= n) continue;
          s += texture2D(tDiffuse, filmUv(d * uDot + vec2(x, y))).rgb;
        }
        return s / (uDot * uDot);
      }
      void main() {
        vec2 d = floor(filmPx() / uDot);                      // the dot this pixel belongs to (fixed to the frame)
        vec3 c = dotColour(d);
      #if PAL_N > 0
        int i1 = 0, i2 = 0; float d1 = 1e9, d2 = 1e9;
        for (int i = 0; i < PAL_N; i++) { vec3 e = c - uPal[i]; float q = dot(e, e);
          if (q < d1) { d2 = d1; i2 = i1; d1 = q; i1 = i; } else if (q < d2) { d2 = q; i2 = i; } }
        vec3 a = uPal[i1], b = uPal[i2], ab = b - a;
        float k = clamp(dot(c - a, ab) / max(dot(ab, ab), 1e-6), 0.0, 1.0);
        gl_FragColor = vec4(k > bayer4(ivec2(d)) ? b : a, 1.0);
      #else
        float l = pow(clamp((luma(c) - uLv.x) / (uLv.y - uLv.x), 0.0, 1.0), uLv.z);
        gl_FragColor = vec4(l > bayer8(ivec2(d)) ? uInk1 : uInk0, 1.0);
      #endif
      }`, { uDot: { value: dot }, uInk0: { value: hex3(inks[0]) }, uInk1: { value: hex3(inks[1]) },
        uLv: { value: new THREE.Vector3(...levels) }, ...(pal.length ? { uPal: { value: pal } } : {}) },
    { PAL_N: mode === "palette" ? pal.length : 0 });
    if (dot > 4 || 1920 % dot || 1080 % dot) throw new Error(`dither dot ${dot} must be <= 4 and divide 1920 x 1080`);
  }
}

// ---- 6.5 CRT: curvature, scanlines, aperture-grille mask, vignette, stepped flicker, roll ----------
export class CrtPass extends FilmPixelPass {
  constructor({ curvature = 0.045, scanPeriod = 6, scanDepth = 0.75, maskDepth = 0.16, triad = 6, vignette = 0.32, black = 0.018 } = {}) {
    super(/* glsl */`
      uniform float uCurv, uScanP, uScanD, uMaskD, uTriad, uVig, uBlack, uFlick, uRoll;
      varying vec2 vUv;
      void main() {
        vec2 fp = filmPx() + 0.5;
        vec2 c = fp / uFilm * 2.0 - 1.0;
        c *= 1.0 + uCurv * (c.yx * c.yx);                     // barrel: the glass bulges
        c *= 1.0 - 0.5 * uCurv;                               // pull back in so most of the picture stays on the glass
        vec2 uv = c * 0.5 + 0.5;
        vec2 q = abs(c) - (1.0 - 0.06);                       // rounded-corner screen edge, feathered ~1.5 film px
        float glass = 1.0 - smoothstep(-0.002, 0.002, length(max(q, 0.0)) - 0.06);
        float px = 1.0 / uFilm.x;
        vec3 col = vec3(texture2D(tDiffuse, uv + vec2(0.6 * px, 0.0)).r,  // slight convergence error
                        texture2D(tDiffuse, uv).g,
                        texture2D(tDiffuse, uv - vec2(0.6 * px, 0.0)).b);
        float L = luma(col);
        // scanlines follow the curved glass: a Gaussian beam per line, wider when bright
        float y = uv.y * uFilm.y / uScanP, dy = fract(y) - 0.5;
        float w = mix(0.17, 0.36, clamp(L, 0.0, 1.0));
        float beam = exp(-dy * dy / (2.0 * w * w));
        col *= mix(1.0 - uScanD, 1.0, beam) / mix(1.0 - uScanD, 1.0, 0.6);
        // aperture grille fixed to the screen: R, G, B stripes uTriad/3 film px wide
        float m = mod(fp.x - 0.5, uTriad) / uTriad;
        vec3 tri = m < 1.0 / 3.0 ? vec3(1.0, 0.0, 0.0) : (m < 2.0 / 3.0 ? vec3(0.0, 1.0, 0.0) : vec3(0.0, 0.0, 1.0));
        col *= mix(vec3(1.0), tri * 3.0, uMaskD);                  // stripes average to 1: no brightness loss
        col = max(col, vec3(uBlack));                         // phosphor never quite black
        float v = 16.0 * uv.x * uv.y * (1.0 - uv.x) * (1.0 - uv.y);
        col *= pow(clamp(v, 0.0, 1.0), uVig);
        float r = fract(uv.y - uRoll) - 0.5;                  // a faint rolling bar (position from t)
        col *= uFlick * (1.0 + 0.045 * exp(-r * r * 40.0));
        gl_FragColor = vec4(col * glass, 1.0);
      }`, { uCurv: { value: curvature }, uScanP: { value: scanPeriod }, uScanD: { value: scanDepth }, uMaskD: { value: maskDepth },
        uTriad: { value: triad }, uVig: { value: vignette }, uBlack: { value: black }, uFlick: { value: 1 }, uRoll: { value: 0 } });
  }
}

// ---- 6.7 ink and paper ----------------------------------------------------------------------
// Renders the scene's normals + depth into its own target, finds creases (normals) and silhouettes
// (Laplacian of 1/z, zero on planes), draws them in ink with a boil stepped from the frame, puts three
// tones (paper, wash or accent wash, hatched shade) from the input colour on a static paper.
export function makePaperTexture(seed, w = 960, h = 540) {
  // CPU, once, seeded: soft fibre clouds; per-pixel grain is added in the shader from an integer hash
  let a = seed >>> 0;
  const rnd = () => { a = (a + 0x6d2b79f5) >>> 0; let t = a; t = Math.imul(t ^ (t >>> 15), t | 1);
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61); return ((t ^ (t >>> 14)) >>> 0) / 4294967296; };
  const G = 64, lat = new Float32Array((G + 1) * (G + 1) * 4).map(() => rnd());
  const at = (o, i, j) => lat[o * (G + 1) * (G + 1) + (j % (G + 1)) * (G + 1) + (i % (G + 1))];
  const noise = (o, x, y) => { const i = Math.floor(x), j = Math.floor(y), u = x - i, v = y - j, su = u * u * (3 - 2 * u), sv = v * v * (3 - 2 * v);
    return (at(o, i, j) * (1 - su) + at(o, i + 1, j) * su) * (1 - sv) + (at(o, i, j + 1) * (1 - su) + at(o, i + 1, j + 1) * su) * sv; };
  const data = new Uint8Array(w * h * 4);
  for (let y = 0; y < h; y++) for (let x = 0; x < w; x++) {
    const cloud = 0.55 * noise(0, x / 60, y / 60) + 0.3 * noise(1, x / 21, y / 21) + 0.15 * noise(2, x / 7, y / 7);
    const fibre = noise(3, x / 2.5, y / 11);                       // short vertical-ish fibres
    const v = 1 - 0.06 * cloud - 0.02 * Math.max(0, fibre - 0.55) * 2.2;
    const k = (y * w + x) * 4; data[k] = data[k + 1] = data[k + 2] = Math.round(255 * v); data[k + 3] = 255;
  }
  const tex = new THREE.DataTexture(data, w, h, THREE.RGBAFormat, THREE.UnsignedByteType);
  tex.minFilter = tex.magFilter = THREE.LinearFilter; tex.generateMipmaps = false; tex.needsUpdate = true;
  return tex;
}

export class InkPaperPass extends FilmPixelPass {
  // rig: { show: [a shadow-casting DirectionalLight, normally invisible], hide: [the film's other lights] }
  // tones: [wash below this light, hatch below this light, crosshatch below this scene luma (inside hatch)]
  constructor(scene, camera, { paper, ink, wash, shade, accent, rig, tones = [0.42, 0.2, 0.2], seed = 11, line = 1.25, boilPx = 1.1 }) {
    super(/* glsl */`
      #include <packing>
      uniform sampler2D tNormal, tDepth, tLight, tPaper;
      uniform vec2 uNF; uniform float uStep, uLine, uBoil;
      uniform vec3 uPaper, uInk, uWash, uShade, uAccent; uniform vec3 uTones;
      varying vec2 vUv;
      float invZ(vec2 fp) { float z = texture2D(tDepth, fp / uFilm).r; return -1.0 / perspectiveDepthToViewZ(z, uNF.x, uNF.y); }
      vec3 nrm(vec2 fp) { return texture2D(tNormal, fp / uFilm).xyz * 2.0 - 1.0; }
      void main() {
        vec2 fp = filmPx() + 0.5;
        uint st = uint(uStep);
        // boil: the line is drawn from positions displaced by a noise field that changes every step
        vec2 disp = (vec2(vnoise(fp * 0.018, st * 2u + 1u), vnoise(fp * 0.018 + 37.0, st * 2u + 2u)) - 0.5) * 2.0 * uBoil;
        vec2 p = fp + disp;
        float r = uLine * (0.75 + 0.5 * vnoise(fp * 0.04, st + 101u));      // pressure varies along the line
        float z0 = invZ(p), zl = invZ(p - vec2(r, 0)), zr = invZ(p + vec2(r, 0)), zd = invZ(p - vec2(0, r)), zu = invZ(p + vec2(0, r));
        float lap = abs(zl + zr + zd + zu - 4.0 * z0) / max(z0, 1e-4);           // zero on any plane
        vec3 n0 = nrm(p);
        float crease = max(max(1.0 - dot(n0, nrm(p - vec2(r, 0))), 1.0 - dot(n0, nrm(p + vec2(r, 0)))),
                           max(1.0 - dot(n0, nrm(p - vec2(0, r))), 1.0 - dot(n0, nrm(p + vec2(0, r)))));
        float edge = max(smoothstep(0.012, 0.03, lap), smoothstep(0.08, 0.2, crease));
        // tones: shading from the key light alone (N.L x shadow), local colour from the scene render
        vec2 pw = fp + 0.6 * disp;                                                 // the wash edge wobbles with the boil
        float Lt = texture2D(tLight, pw / uFilm).r;
        vec3 c = texture2D(tDiffuse, pw / uFilm).rgb;
        float Lc = luma(c), mx = max(c.r, max(c.g, c.b));
        float acc = smoothstep(0.12, 0.22, mx - min(c.r, min(c.g, c.b)));          // chroma, not saturation: dark greys have high saturation
        float inWash = 1.0 - smoothstep(uTones.x - 0.03, uTones.x + 0.03, Lt);
        float inShade = 1.0 - smoothstep(uTones.y - 0.02, uTones.y + 0.02, Lt);
        float inDeep = inShade * (1.0 - smoothstep(uTones.z - 0.02, uTones.z + 0.02, Lc));
        vec3 washC = mix(uWash, uAccent, acc);
        vec3 col = mix(uPaper, uPaper * washC, max(inWash, 0.55 * acc));
        // hatching fixed to the paper: 45 degrees in shade, crossed where the scene is darkest
        float h1 = abs(fract((fp.x + fp.y) / 7.0) - 0.5) * 7.0;
        float h2 = abs(fract((fp.x - fp.y) / 7.0) - 0.5) * 7.0;
        float hatch = max(inShade * (1.0 - smoothstep(0.55, 1.35, h1)), inDeep * (1.0 - smoothstep(0.5, 1.25, h2)));
        col = mix(col, uShade, 0.8 * hatch);
        // paper: fibre clouds from the texture + per-pixel grain from an integer hash (both fixed to the frame)
        float grain = hash3(uint(fp.x), uint(fp.y), 7u) - 0.5;
        col *= texture2D(tPaper, fp / uFilm).r * (1.0 + 0.035 * grain);
        col = mix(col, uInk, 0.92 * edge);
        gl_FragColor = vec4(col, 1.0);
      }`, {
      tNormal: { value: null }, tDepth: { value: null }, tLight: { value: null }, tPaper: { value: makePaperTexture(seed) },
      uNF: { value: new THREE.Vector2(camera.near, camera.far) }, uStep: { value: 0 }, uLine: { value: line }, uBoil: { value: boilPx },
      uPaper: { value: hex3(paper) }, uInk: { value: hex3(ink) }, uWash: { value: hex3(wash) }, uShade: { value: hex3(shade) },
      uAccent: { value: hex3(accent) }, uTones: { value: new THREE.Vector3(...tones) } });
    this.scene = scene; this.camera = camera; this.rig = rig;
    this.normalMat = new THREE.MeshNormalMaterial();
    this.lightMat = new THREE.MeshLambertMaterial({ color: 0xffffff });      // white: the render IS the light
    this.rt = new THREE.WebGLRenderTarget(1, 1, { type: THREE.HalfFloatType, minFilter: THREE.NearestFilter, magFilter: THREE.NearestFilter });
    this.rt.depthTexture = new THREE.DepthTexture(1, 1);
    this.rt.depthTexture.minFilter = this.rt.depthTexture.magFilter = THREE.NearestFilter;
    this.rtLight = new THREE.WebGLRenderTarget(1, 1, { type: THREE.UnsignedByteType });
  }
  setSize(w, h) { this.rt.setSize(w, h); this.rtLight.setSize(w, h); }
  renderOverride(renderer, target, material) {
    const { scene, camera } = this;
    const keepOverride = scene.overrideMaterial;
    scene.overrideMaterial = material;
    renderer.setRenderTarget(target); renderer.clear(); renderer.render(scene, camera);
    scene.overrideMaterial = keepOverride;
  }
  render(renderer, writeBuffer, readBuffer) {
    const { scene, camera, rig } = this;
    const keepClear = renderer.getClearColor(new THREE.Color()), keepAlpha = renderer.getClearAlpha();
    // 1. normals + depth (no shadows needed)
    const keepShadow = renderer.shadowMap.enabled; renderer.shadowMap.enabled = false;
    renderer.setClearColor(0x8080ff, 1); this.renderOverride(renderer, this.rt, this.normalMat);
    renderer.shadowMap.enabled = keepShadow;
    // 2. light: white Lambert lit by the rig's light alone (with its shadow); every other light hidden
    const keepEnv = scene.environment; scene.environment = null;
    for (const l of rig.hide) l.visible = false; for (const l of rig.show) l.visible = true;
    renderer.setClearColor(0x000000, 1); this.renderOverride(renderer, this.rtLight, this.lightMat);
    for (const l of rig.hide) l.visible = true; for (const l of rig.show) l.visible = false;
    scene.environment = keepEnv; renderer.setClearColor(keepClear, keepAlpha);
    const U = this.uniforms;
    U.tNormal.value = this.rt.texture; U.tDepth.value = this.rt.depthTexture; U.tLight.value = this.rtLight.texture;
    U.uNF.value.set(camera.near, camera.far);
    super.render(renderer, writeBuffer, readBuffer);
  }
}

// ---- 6.3 helper: invert (x tint) - around HalftonePass it turns RGB light dots into CMY ink on paper ----
export class InvertPass extends FilmPixelPass {
  // levels [lo, hi, gamma] lift the near-neutral pixels to a neutral grey (a print wants a lighter ground than
  // the film, and a lifted cool grey turns blue); chromatic pixels (the accent) pass unchanged, so their hue holds
  // dotGain: HalftoneShader draws a dot of radius v^1.125 x grid step, so the inked area is ~pi * v^2.25 of
  // the cell (mid-tones print dark, orange prints red); feed it (ink / pi)^(1 / 2.25) so area ~= ink
  constructor(tint = "#ffffff", levels = [0, 1, 1], dotGain = false) {
    super(/* glsl */`uniform vec3 uTint, uLv; uniform float uGain; varying vec2 vUv;
      void main() {
        vec3 c = texture2D(tDiffuse, vUv).rgb; float L = luma(c);
        float f = pow(clamp((L - uLv.x) / (uLv.y - uLv.x), 0.0, 1.0), uLv.z);
        float chroma = max(c.r, max(c.g, c.b)) - min(c.r, min(c.g, c.b));
        c = mix(vec3(f), c, smoothstep(0.1, 0.25, chroma));
        vec3 ink = 1.0 - c;
        if (uGain > 0.5) ink = min(vec3(1.0), pow(ink / 3.14159265, vec3(1.0 / 2.25)));
        gl_FragColor = vec4(ink * uTint, 1.0);
      }`, { uTint: { value: hex3(tint) }, uLv: { value: new THREE.Vector3(...levels) }, uGain: { value: dotGain ? 1 : 0 } });
  }
}

// ---- the look switch: two looks mixed by a moving diagonal mask, drawn to the screen ----------
export class WipeQuad {
  constructor({ line }) {
    this.uniforms = { tA: { value: null }, tB: { value: null }, uPR: { value: 1 }, uFilm: { value: FILM.clone() },
      uEdge: { value: 0 }, uLine: { value: hex3(line) } };
    this.material = new THREE.ShaderMaterial({ uniforms: this.uniforms, vertexShader: VERT, depthTest: false, depthWrite: false,
      fragmentShader: GLSL_COMMON + /* glsl */`
        uniform sampler2D tA, tB; uniform float uEdge; uniform vec3 uLine; varying vec2 vUv;
        void main() {
          vec2 fp = filmPx() + 0.5;
          float s = (fp.x + 0.42 * (uFilm.y - fp.y)) / (uFilm.x + 0.42 * uFilm.y);   // 0 top-left .. 1 bottom-right, slanted
          float px = 1.0 / (uFilm.x + 0.42 * uFilm.y);
          float d = (s - uEdge) / px;                                                // film px from the edge
          vec3 a = texture2D(tA, filmUv(fp - 0.5)).rgb, b = texture2D(tB, filmUv(fp - 0.5)).rgb;
          vec3 col = mix(b, a, smoothstep(-1.0, 1.0, d));                             // B behind the edge, A ahead
          col = mix(col, uLine, 1.0 - smoothstep(1.0, 2.2, abs(d)));                  // a 3 px accent line on the edge
          gl_FragColor = vec4(col, 1.0);
        }` });
    this._quad = new FullScreenQuad(this.material);
  }
  render(renderer) { renderer.setRenderTarget(null); this._quad.render(renderer); }
}
