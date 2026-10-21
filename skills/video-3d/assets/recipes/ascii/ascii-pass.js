// ascii-pass.js - ASCII cinema for three.js films in HyperFrames (video-3d skill, recipe "ascii").
//
// A post-process that turns any rendered picture into a fixed grid of monospace glyphs:
//   1. cells pass  : the input is box-averaged per cell into a cols x rows target (exact area
//                    average: one bilinear fetch per 2x2 pixels), so a glyph reflects the whole
//                    cell, not one sample - this is what keeps glyphs from shimmering.
//   2. glyph pass  : per output pixel - cell luminance -> levels -> a coverage-sorted glyph ramp
//                    (soft crossfade only near a step), optional edge glyphs (| / - \) from a
//                    Sobel on the cell grid, ink from a 3-stop palette or from the scene's own hue,
//                    a shape mask that the field "forms" (a big word or logo), and text cells that
//                    decode into readable words. Glyphs come from an atlas drawn ONCE at build time.
//
// It is an EffectComposer Pass. Put it after OutputPass: it reads display-referred (sRGB) values
// and writes palette colours as given (hex in = pixel out; the shader has no colour-space chunk).
// Everything it shows is a function of the uniforms you set from t; nothing is carried between
// frames. Integer hashing (uint) for scrambles, so GPU and software renders pick the same glyphs.
//
// Usage (see the skill's assets/recipes/ascii/README.md):
//   const atlas = await buildGlyphAtlas({ family: "AsciiMono", url: "assets/fonts/Mono.ttf", fontPx: 20, cell: [12, 24] });
//   const ascii = new AsciiPass({ atlas, size: [1920, 1080], palette: {...} });
//   composer.addPass(new RenderPass(scene, camera)); composer.addPass(new OutputPass()); composer.addPass(ascii);
//   ascii.setText([{ row: 30, col: 20, text: "hello" }]); ascii.setMask(canvas);
//   in renderAt(t): ascii.setTime(t, frame); ascii.uniforms.uQuiet.value = ...; composer.render(0);
import * as THREE from "three";
import { Pass, FullScreenQuad } from "three/addons/postprocessing/Pass.js";

export const PRINTABLE = Array.from({ length: 95 }, (_, i) => String.fromCharCode(32 + i)).join("");
// Luminance ramps. buildRamp() orders the candidates by their MEASURED ink in this font and keeps
// `levels` of them. CLASSIC (symbols only) reads as picture; DENSE (letters too) reads as text-noise.
export const RAMP_CLASSIC = " .:-=+*#%@";
export const RAMP_DENSE = " .'`,:;-_~^\"!|il/\\()=+<>?*7tfjrxnvczuoasYJCLUZ0OQ#%&8B@MWm$";

// ---------------------------------------------------------------- glyph atlas (build time)
// Draws every glyph into a cell of exactly the output cell size, so the shader copies texels 1:1
// (no filtering, no shimmer). CPU canvas (willReadFrequently) - the same raster in every worker.
export async function buildGlyphAtlas({
  family, url, weight = "400", fontPx = 20, cell = [12, 24], chars = PRINTABLE, perRow = 16,
} = {}) {
  if (url) {
    const face = new FontFace(family, `url(${url})`, { weight: "100 900" });
    await face.load();                       // a CSS @font-face alone is not enough for canvas text
    document.fonts.add(face);
  }
  const font = `${weight} ${fontPx}px "${family}"`;
  await document.fonts.load(font);
  if (!document.fonts.check(font)) throw new Error(`ascii: font not ready: ${font}`);

  const [cw, ch] = cell;
  const rows = Math.ceil(chars.length / perRow);
  const canvas = document.createElement("canvas");
  canvas.width = perRow * cw; canvas.height = rows * ch;
  const ctx = canvas.getContext("2d", { willReadFrequently: true });
  ctx.fillStyle = "#000"; ctx.fillRect(0, 0, canvas.width, canvas.height);
  ctx.fillStyle = "#fff"; ctx.font = font; ctx.textAlign = "center"; ctx.textBaseline = "alphabetic";
  const m = ctx.measureText("Hg");
  const asc = m.fontBoundingBoxAscent, desc = m.fontBoundingBoxDescent;
  const base = Math.round((ch - (asc + desc)) / 2 + asc);
  const adv = ctx.measureText("M").width;
  for (let i = 0; i < chars.length; i++) {
    const x = (i % perRow) * cw + cw / 2, y = Math.floor(i / perRow) * ch + base;
    ctx.fillText(chars[i], x, y);
  }
  // measured ink per glyph (0..1) - the ramp is sorted by this, not by eye
  const data = ctx.getImageData(0, 0, canvas.width, canvas.height).data;
  const coverage = new Float32Array(chars.length);
  for (let i = 0; i < chars.length; i++) {
    const x0 = (i % perRow) * cw, y0 = Math.floor(i / perRow) * ch;
    let s = 0;
    for (let y = 0; y < ch; y++) for (let x = 0; x < cw; x++) s += data[((y0 + y) * canvas.width + x0 + x) * 4];
    coverage[i] = s / (255 * cw * ch);
  }
  const texture = new THREE.CanvasTexture(canvas);
  texture.flipY = false;                      // texel row 0 = top of the canvas
  texture.minFilter = texture.magFilter = THREE.NearestFilter;
  texture.generateMipmaps = false;
  texture.colorSpace = THREE.NoColorSpace;    // data, not colour
  texture.needsUpdate = true;
  const index = new Map([...chars].map((c, i) => [c, i]));
  return { texture, canvas, chars, index, coverage, perRow, rows, cell: [cw, ch], fontPx, advance: adv };
}

// Pick `levels` glyphs whose measured ink is closest to evenly spaced targets.
export function buildRamp(atlas, { candidates = RAMP_CLASSIC, levels = 10 } = {}) {
  const list = [...new Set(candidates)].filter((c) => atlas.index.has(c))
    .map((c) => ({ c, i: atlas.index.get(c), cov: atlas.coverage[atlas.index.get(c)] }))
    .sort((a, b) => a.cov - b.cov || a.c.localeCompare(b.c));
  const lo = list[0].cov, hi = list[list.length - 1].cov, out = [], n = Math.min(levels, list.length);
  for (let k = 0; k < n; k++) {
    const target = lo + ((hi - lo) * k) / Math.max(1, n - 1);
    let best = null;
    for (const g of list) if (!out.includes(g) && (!best || Math.abs(g.cov - target) < Math.abs(best.cov - target))) best = g;
    out.push(best);
  }
  out.sort((a, b) => a.cov - b.cov);
  return out;                                  // [{ c, i, cov }], darkest first (a space if offered)
}

const indexTexture = (indices) => {
  const n = Math.max(1, indices.length), d = new Uint8Array(n * 4);
  indices.forEach((v, k) => { d[k * 4] = v; });
  const t = new THREE.DataTexture(d, n, 1, THREE.RGBAFormat, THREE.UnsignedByteType);
  t.minFilter = t.magFilter = THREE.NearestFilter; t.needsUpdate = true; return t;
};

// hex "#rrggbb" -> raw sRGB triple. Do NOT use new THREE.Color(hex) for these: with colour
// management on, it converts to linear and the glyph colours come out wrong.
export const hex3 = (h) => { const n = parseInt(String(h).trim().replace("#", ""), 16); return new THREE.Vector3(((n >> 16) & 255) / 255, ((n >> 8) & 255) / 255, (n & 255) / 255); };

function rng(seed) { let a = seed >>> 0; return () => { a = (a + 0x6d2b79f5) >>> 0; let t = a;
  t = Math.imul(t ^ (t >>> 15), t | 1); t ^= t + Math.imul(t ^ (t >>> 7), t | 61); return ((t ^ (t >>> 14)) >>> 0) / 4294967296; }; }

// ---------------------------------------------------------------- the pass
export class AsciiPass extends Pass {
  constructor({
    atlas, size = [1920, 1080], ramp = null, levels = 10, subsamples = null,
    palette = { ground: "#000000", ink: ["#303030", "#909090", "#ffffff"], text: "#ffffff", mask: "#ffffff" },
    scrambleChars = "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789#%&*+=<>/\\?",
  }) {
    super();
    const [W, H] = size, [cw, ch] = atlas.cell;
    if (W % cw || H % ch) throw new Error(`ascii: cell ${cw}x${ch} must divide ${W}x${H} exactly (no partial cells, no grid jitter)`);
    this.atlas = atlas; this.W = W; this.H = H;
    this.cols = W / cw; this.rows = H / ch;
    this.ramp = ramp || buildRamp(atlas, { levels });

    // 1. cells pass: exact box average, one bilinear fetch per 2x2 pixels
    this.rtCells = new THREE.WebGLRenderTarget(this.cols, this.rows, {
      type: THREE.HalfFloatType, minFilter: THREE.NearestFilter, magFilter: THREE.NearestFilter,
      depthBuffer: false, generateMipmaps: false });
    this.cellsMat = new THREE.ShaderMaterial({
      // exact box filter by default (cell/2 bilinear taps per axis); [1, 1] = centre sample only (shimmers)
      defines: { SUBX: subsamples ? subsamples[0] : Math.max(1, Math.floor(cw / 2)), SUBY: subsamples ? subsamples[1] : Math.max(1, Math.floor(ch / 2)) },
      uniforms: { tSrc: { value: null }, uRes: { value: new THREE.Vector2(W, H) }, uCell: { value: new THREE.Vector2(cw, ch) } },
      vertexShader: /* glsl */`varying vec2 vUv; void main(){ vUv = uv; gl_Position = vec4(position.xy, 0.0, 1.0); }`,
      fragmentShader: /* glsl */`
        uniform sampler2D tSrc; uniform vec2 uRes, uCell;
        void main() {
          vec2 org = floor(gl_FragCoord.xy) * uCell;           // bottom-left pixel of this cell
          vec2 st = uCell / vec2(float(SUBX), float(SUBY));
          vec3 acc = vec3(0.0);
          for (int j = 0; j < SUBY; j++) for (int i = 0; i < SUBX; i++)
            acc += texture2D(tSrc, (org + (vec2(float(i), float(j)) + 0.5) * st) / uRes).rgb;
          acc /= float(SUBX * SUBY);
          gl_FragColor = vec4(acc, dot(acc, vec3(0.2126, 0.7152, 0.0722)));
        }`,
      depthTest: false, depthWrite: false,
    });
    this.cellsQuad = new FullScreenQuad(this.cellsMat);

    // cell layers built on the CPU: text (char, reveal key, quiet zone) and mask (coverage, key)
    this.textData = new Uint8Array(this.cols * this.rows * 4);
    for (let k = 0; k < this.cols * this.rows; k++) this.textData[k * 4] = 255;   // 255 = no text
    this.tText = new THREE.DataTexture(this.textData, this.cols, this.rows, THREE.RGBAFormat, THREE.UnsignedByteType);
    this.maskData = new Uint8Array(this.cols * this.rows * 4);
    this.tMask = new THREE.DataTexture(this.maskData, this.cols, this.rows, THREE.RGBAFormat, THREE.UnsignedByteType);
    for (const t of [this.tText, this.tMask]) { t.minFilter = t.magFilter = THREE.NearestFilter; t.needsUpdate = true; }

    const idx = (c) => atlas.index.get(c) ?? 0;
    const P = palette;
    this.uniforms = {
      tCells: { value: this.rtCells.texture }, tAtlas: { value: atlas.texture },
      tRamp: { value: indexTexture(this.ramp.map((g) => g.i)) }, uRampN: { value: this.ramp.length },
      tScr: { value: indexTexture([...scrambleChars].map(idx)) }, uScrN: { value: scrambleChars.length },
      tText: { value: this.tText }, tMask: { value: this.tMask },
      uCell: { value: new THREE.Vector2(cw, ch) }, uGrid: { value: new THREE.Vector2(this.cols, this.rows) },
      uAtlasPerRow: { value: atlas.perRow },
      // levels: x black point, y white point, z gamma, w crossfade band (0 = hard switch)
      uLevels: { value: new THREE.Vector4(0.02, 0.85, 0.9, 0.25) },
      uGround: { value: hex3(P.ground) },
      uInk0: { value: hex3(P.ink[0]) }, uInk1: { value: hex3(P.ink[1]) }, uInk2: { value: hex3(P.ink[2]) },
      uTextInk: { value: hex3(P.text) }, uMaskInk: { value: hex3(P.mask ?? P.text) },
      uSceneColor: { value: 0.0 },        // 0: palette ink; 1: saturated cells take the scene's hue
      uBackLight: { value: 0.0 },         // tint the cell ground with the scene colour (0..0.3)
      uEdges: { value: 0.0 }, uEdgeTh: { value: new THREE.Vector2(0.10, 0.22) },
      uEdgeGlyphs: { value: new THREE.Vector4(idx("|"), idx("/"), idx("-"), idx("\\")) },
      uTime: { value: 0 }, uStep: { value: 0 },            // uStep: scramble step, integer, from the frame
      uTextT: { value: new THREE.Vector2(1e9, 1.0) },      // x: decode start (s), y: spread over keys (s)
      uScramble: { value: 0.45 },                          // s of scrambling before a cell settles
      uTextOut: { value: 1e9 },                            // s: text gone (keyed the same way)
      uQuiet: { value: 0.0 },                              // 0..1: dim the scene under quiet cells
      uMask: { value: new THREE.Vector2(0.0, 0.12) },      // x: formation 0..1 (keyed), y: soft width
      uMaskLevel: { value: 1.0 },                          // luminance the mask shape takes
    };
    this.material = new THREE.ShaderMaterial({
      uniforms: this.uniforms,
      vertexShader: /* glsl */`varying vec2 vUv; void main(){ vUv = uv; gl_Position = vec4(position.xy, 0.0, 1.0); }`,
      fragmentShader: /* glsl */`
        precision highp float; precision highp int;
        uniform sampler2D tCells, tAtlas, tRamp, tScr, tText, tMask;
        uniform float uRampN, uScrN, uAtlasPerRow, uSceneColor, uBackLight, uEdges, uTime, uStep;
        uniform float uScramble, uTextOut, uQuiet, uMaskLevel;
        uniform vec2 uCell, uGrid, uEdgeTh, uTextT, uMask;
        uniform vec4 uLevels, uEdgeGlyphs;
        uniform vec3 uGround, uInk0, uInk1, uInk2, uTextInk, uMaskInk;

        uint pcg(uint v) { uint s = v * 747796405u + 2891336453u; uint w = ((s >> ((s >> 28u) + 4u)) ^ s) * 277803737u; return (w >> 22u) ^ w; }
        float hash3(ivec3 p) { return float(pcg(uint(p.x) + pcg(uint(p.y) + pcg(uint(p.z))))) / 4294967295.0; }

        float lumAt(ivec2 c) { c = clamp(c, ivec2(0), ivec2(uGrid) - 1); return texelFetch(tCells, c, 0).a; }
        float levels(float y) {
          float l = clamp((y - uLevels.x) / max(1e-4, uLevels.y - uLevels.x), 0.0, 1.0);
          return pow(l, uLevels.z);
        }
        // glyph coverage at a pixel inside the cell; atlas rows run top-down
        float glyph(float gi, vec2 inCell) {
          float col = mod(gi, uAtlasPerRow), row = floor(gi / uAtlasPerRow);
          ivec2 p = ivec2(int(col * uCell.x + floor(inCell.x)), int(row * uCell.y + (uCell.y - 1.0 - floor(inCell.y))));
          return texelFetch(tAtlas, p, 0).r;
        }
        float rampGlyph(float k) { return floor(texelFetch(tRamp, ivec2(int(k), 0), 0).r * 255.0 + 0.5); }

        void main() {
          ivec2 cell = ivec2(floor(gl_FragCoord.xy / uCell));
          vec2 inCell = gl_FragCoord.xy - vec2(cell) * uCell;
          ivec2 top = ivec2(cell.x, int(uGrid.y) - 1 - cell.y);       // CPU layers are written top-down
          vec4 c = texelFetch(tCells, cell, 0);
          vec4 tx = floor(texelFetch(tText, top, 0) * 255.0 + 0.5);
          vec4 mk = texelFetch(tMask, top, 0);

          float l = levels(c.a);
          l *= 1.0 - uQuiet * tx.b / 255.0;                              // quiet zone: a soft clearing

          // the field forms a shape: cell by cell (seeded key), then it holds
          float form = smoothstep(mk.g - uMask.y, mk.g + uMask.y, uMask.x * (1.0 + 2.0 * uMask.y) - uMask.y);
          float mcov = mk.r * form;
          l = mix(l, uMaskLevel * mk.r, step(0.004, mk.r) * form);

          // luminance -> glyph: hard pick, crossfade only inside a narrow band around each step
          float f = l * (uRampN - 1.0), i0 = floor(f), fr = f - i0;
          float w = uLevels.w > 0.0 ? smoothstep(0.5 - 0.5 * uLevels.w, 0.5 + 0.5 * uLevels.w, fr) : step(0.5, fr);
          float cov = mix(glyph(rampGlyph(i0), inCell), glyph(rampGlyph(min(i0 + 1.0, uRampN - 1.0)), inCell), w);

          // edge glyphs from a Sobel on the cell grid (cell-scale contours, stable in motion)
          if (uEdges > 0.0) {
            float a = lumAt(cell + ivec2(-1, 1)), b = lumAt(cell + ivec2(0, 1)), d = lumAt(cell + ivec2(1, 1));
            float e = lumAt(cell + ivec2(-1, 0)), g = lumAt(cell + ivec2(1, 0));
            float h = lumAt(cell + ivec2(-1, -1)), k = lumAt(cell + ivec2(0, -1)), m = lumAt(cell + ivec2(1, -1));
            float gx = (d + 2.0 * g + m) - (a + 2.0 * e + h);
            float gy = (a + 2.0 * b + d) - (h + 2.0 * k + m);
            float mag = length(vec2(gx, gy)) * 0.25;
            float ew = smoothstep(uEdgeTh.x, uEdgeTh.y, mag) * uEdges * (1.0 - step(0.004, mcov));
            if (ew > 0.0) {
              // gradient direction in SCREEN space: cells are not square, so scale by the cell size
              float ang = mod(atan(gy / uCell.y, gx / uCell.x) + 3.14159265 / 8.0, 3.14159265);
              int bin = int(floor(ang / (3.14159265 / 4.0)));                      // 0: |  1: \\  2: -  3: /
              float gi = bin == 0 ? uEdgeGlyphs.x : bin == 1 ? uEdgeGlyphs.w : bin == 2 ? uEdgeGlyphs.z : uEdgeGlyphs.y;
              cov = mix(cov, glyph(gi, inCell), ew);
              l = max(l, 0.55 * ew);
            }
          }

          // ink: palette by luminance, or the scene's own hue where the scene is saturated
          vec3 pal = l < 0.5 ? mix(uInk0, uInk1, l * 2.0) : mix(uInk1, uInk2, l * 2.0 - 1.0);
          float mx = max(max(c.r, c.g), c.b), mn = min(min(c.r, c.g), c.b);
          float sat = mx > 1e-4 ? (mx - mn) / mx : 0.0;
          vec3 hue = mx > 1e-4 ? c.rgb / mx : vec3(1.0);
          vec3 ink = mix(pal, hue * mix(0.5, 1.0, l), uSceneColor * smoothstep(0.2, 0.55, sat));
          ink = mix(ink, uMaskInk, smoothstep(0.0, 0.5, mcov));
          vec3 ground = uGround + c.rgb * uBackLight;

          // text cells: scramble, then settle on the character; a seeded key orders the cells
          if (tx.r < 254.5) {
            float t0 = uTextT.x + tx.g / 255.0 * uTextT.y, t1 = uTextOut + tx.g / 255.0 * uTextT.y;
            if (uTime >= t0 && uTime < t1) {
              float gi = tx.r;
              if (uTime < t0 + uScramble) {
                float h = hash3(ivec3(cell, int(uStep)));
                gi = floor(texelFetch(tScr, ivec2(min(int(h * uScrN), int(uScrN) - 1), 0), 0).r * 255.0 + 0.5);
              }
              cov = glyph(gi, inCell);
              ink = uTextInk;
            }
          }
          gl_FragColor = vec4(mix(ground, ink, cov), 1.0);
        }`,
      depthTest: false, depthWrite: false,
    });
    this.quad = new FullScreenQuad(this.material);
  }

  // Time for the text decode and the scramble. frame = Math.round(t * fps); the scramble step is an
  // integer computed here on the CPU, so a cell's random glyph never depends on float rounding.
  setTime(t, frame, { scrambleHz = 15, fps = 30 } = {}) {
    this.uniforms.uTime.value = t;
    this.uniforms.uStep.value = Math.floor((frame * scrambleHz) / fps);
  }

  // A quiet zone dims the scene behind words so they read: full inside the box + pad, then a soft
  // falloff over `feather` cells (measured in pixels, so it is round, not stretched by the cell).
  quiet(x0, y0, x1, y1, { pad = 1, feather = 4 } = {}) {
    const [cw, ch] = this.atlas.cell, d = this.textData;
    for (let y = 0; y < this.rows; y++) for (let x = 0; x < this.cols; x++) {
      const dx = Math.max(0, x0 - pad - x, x - x1 - pad) * cw, dy = Math.max(0, y0 - pad - y, y - y1 - pad) * ch;
      const k = 1 - Math.min(1, Math.hypot(dx, dy) / Math.max(1, feather * cw));
      const v = Math.round(255 * k * k * (3 - 2 * k)), o = (y * this.cols + x) * 4 + 2;
      if (v > d[o]) d[o] = v;
    }
    this.tText.needsUpdate = true;
  }

  // lines: [{ row, col, text, quiet: pad cells (default 1, false = none), feather, order: "ltr" | "random" }]
  // row/col are cells from the top-left. Keys spread 0..1 over the cells of each line.
  setText(lines, { seed = 1, jitter = 0.25 } = {}) {
    const d = this.textData, r = rng(seed), cells = [];
    for (const L of lines) {
      if (L.quiet !== false) this.quiet(L.col, L.row, L.col + L.text.length - 1, L.row, { pad: L.quiet ?? 1, feather: L.feather ?? 3 });
      [...L.text].forEach((ch, k) => {
        const x = L.col + k, y = L.row;
        if (x < 0 || x >= this.cols || y < 0 || y >= this.rows || ch === " ") return;
        const gi = this.atlas.index.get(ch);
        if (gi == null) throw new Error(`ascii: "${ch}" is not in the atlas`);
        cells.push({ o: (y * this.cols + x) * 4, gi, key: L.order === "random" ? r() : k / Math.max(1, L.text.length - 1) * (1 - jitter) + r() * jitter });
      });
    }
    for (const c of cells) { d[c.o] = c.gi; d[c.o + 1] = Math.round(Math.min(1, Math.max(0, c.key)) * 255); }
    this.tText.needsUpdate = true;
  }

  // A shape for the field to form: any canvas the size of the frame (a big word, a logo), white on
  // black. Box-averaged to cells here, on the CPU, once. Keys: left-to-right with seeded jitter.
  setMask(canvas, { seed = 2, jitter = 0.35, quiet = 0, feather = 4 } = {}) {
    const [cw, ch] = this.atlas.cell, W = canvas.width, Hc = canvas.height;
    if (W !== this.W || Hc !== this.H) throw new Error("ascii: mask canvas must match the frame size");
    const px = canvas.getContext("2d", { willReadFrequently: true }).getImageData(0, 0, W, Hc).data;
    const r = rng(seed), d = this.maskData;
    let x0 = this.cols, x1 = -1, y0 = this.rows, y1 = -1;
    for (let y = 0; y < this.rows; y++) for (let x = 0; x < this.cols; x++) {
      let s = 0;
      for (let j = 0; j < ch; j++) for (let i = 0; i < cw; i++) s += px[((y * ch + j) * W + x * cw + i) * 4];
      const cov = s / (255 * cw * ch);
      d[(y * this.cols + x) * 4] = Math.round(cov * 255);
      if (cov > 0.02) { x0 = Math.min(x0, x); x1 = Math.max(x1, x); y0 = Math.min(y0, y); y1 = Math.max(y1, y); }
    }
    // keys across the shape's own width: it forms left to right over the whole uMask.x window
    for (let y = 0; y < this.rows; y++) for (let x = 0; x < this.cols; x++) {
      const kx = x1 > x0 ? Math.min(1, Math.max(0, (x - x0) / (x1 - x0))) : 0;
      d[(y * this.cols + x) * 4 + 1] = Math.round(Math.min(1, kx * (1 - jitter) + r() * jitter) * 255);
    }
    if (quiet > 0 && x1 >= 0) this.quiet(x0, y0, x1, y1, { pad: quiet, feather });
    this.tMask.needsUpdate = true;
    return { x0, x1, y0, y1 };
  }

  render(renderer, writeBuffer, readBuffer) {
    this.cellsMat.uniforms.tSrc.value = readBuffer.texture;
    renderer.setRenderTarget(this.rtCells);
    this.cellsQuad.render(renderer);
    renderer.setRenderTarget(this.renderToScreen ? null : writeBuffer);
    this.quad.render(renderer);
  }

  setSize() { /* fixed grid: the film's size never changes */ }
  dispose() { this.rtCells.dispose(); this.cellsMat.dispose(); this.material.dispose(); this.cellsQuad.dispose(); this.quad.dispose(); }
}
