# ASCII cinema - wiring the pass into the skeleton

Status: proven in a test film (the ASCII film: 11 s, 160 x 45 cells, 4-worker and 1-worker renders
identical; its measurements are below). Files here:

- `ascii-pass.js` - `buildGlyphAtlas()`, `buildRamp()`, `RAMP_CLASSIC` / `RAMP_DENSE`, `hex3()`,
  `AsciiPass` (an EffectComposer `Pass`: cells pass + glyph pass, edge glyphs, scene hue, shape mask,
  decoding text cells, feathered quiet zones). WebGL2 only (GLSL 3: `texelFetch`, `uint`).
- `ascii_shimmer.py` - per-cell QA on a PNG sequence: cells changing, A-B-A blips, temporal jitter.

## 1. Copy

```
<film>/assets/ascii-pass.js          <- this folder
<film>/assets/fonts/<Mono>.ttf       <- a monospace font file
```

Pick the cell from the font: the cell width is the font's advance at `fontPx` (JetBrains Mono at
20 px = 12 px), the height a line (24 px). The cell MUST divide the frame (1920 x 1080: 8/10/12/15/16/
20/24/30/40 wide x 12/18/20/24/27/30/36/40/45/54/60 tall) - the pass throws otherwise.
12 x 24 = 160 x 45 cells (fine, a 20 px caption still reads); 16 x 27 or 24 x 36 for a bolder look.

## 2. Skeleton changes (`assets/scene.js`)

```js
import { EffectComposer } from "three/addons/postprocessing/EffectComposer.js";
import { RenderPass } from "three/addons/postprocessing/RenderPass.js";
import { OutputPass } from "three/addons/postprocessing/OutputPass.js";
import { AsciiPass, buildGlyphAtlas, buildRamp } from "./ascii-pass.js";

renderer.setPixelRatio(1);                 // the glyph pass copies atlas texels 1:1 - no supersampling
renderer.toneMapping = THREE.ACESFilmicToneMapping;   // applied by OutputPass, not by the renderer

// in build(), after the scene:
const atlas = await buildGlyphAtlas({ family: "FilmMono", url: "assets/fonts/Mono.ttf", weight: "500", fontPx: 20, cell: [12, 24] });
const css = getComputedStyle(document.documentElement), tok = (n) => css.getPropertyValue(n).trim();
ascii = new AsciiPass({ atlas, ramp: buildRamp(atlas), size: [1920, 1080], palette: {
  ground: tok("--film-ground"), ink: [tok("--film-ink-0"), tok("--film-ink-1"), tok("--film-ink-2")],
  text: tok("--film-text"), mask: tok("--film-mask") } });      // the film's colours, never a brand default
const U = ascii.uniforms;
U.uLevels.value.set(0.05, 0.62, 1.0, 0.25);     // black, white, gamma, crossfade band - set from MEASURED cells
U.uSceneColor.value = 1;                         // saturated objects keep their hue; greys use the palette
U.uEdges.value = 1;                              // | / - \ on contours (Sobel on the cell grid)

// optional: a shape the field forms (any white-on-black canvas the size of the frame)
const box = ascii.setMask(maskCanvas, { seed: 7, quiet: 2, feather: 6 });
// optional: words in text cells (row/col from the top-left), decoding left to right
ascii.setText([{ row: box.y1 + 3, col: 10, text: "the line", quiet: 1, feather: 3 }], { seed: 9 });
U.uTextT.value.set(T.capA, 0.8); U.uScramble.value = 0.4;

composer = new EffectComposer(renderer);
composer.setPixelRatio(1); composer.setSize(1920, 1080);
composer.addPass(new RenderPass(scene, camera));
// (optional display-independent passes here, e.g. UnrealBloomPass)
composer.addPass(new OutputPass());              // tone map + sRGB; the ASCII pass reads display values
composer.addPass(ascii);                         // last: writes the palette exactly

// in renderAt(t) - every value from t:
const frame = Math.round(t * FPS);
ascii.setTime(t, frame);                         // scramble steps are integers from the frame
U.uMask.value.x = seg(t, T.wordA, T.wordB, (x) => x);   // 0..1 formation
U.uQuiet.value = 0.85 * seg(t, T.wordA, T.wordB);       // clearing behind words
composer.render(0);                              // 0: no clock delta reaches any pass
```

## 3. Light the scene for glyphs

Deep blacks matter more than detail. Read the cell luminance before judging a frame:

```js
const buf = new Uint16Array(ascii.cols * ascii.rows * 4);
renderer.readRenderTargetPixels(ascii.rtCells, 0, 0, ascii.cols, ascii.rows, buf);   // HalfFloat
// luma = THREE.DataUtils.fromHalfFloat(buf[i * 4 + 3]); aim: 2% ~0.04, median ~0.3, 98% ~0.6-0.8
```

Then set `uLevels` black/white from those quantiles. A scene lit like a normal film (median 0.6)
fills every cell with a dense glyph and reads as a texture of letters. Flat lit surfaces become one
glyph: give them structure (contour lines, texture, raking light). Saturated colour only on what
should keep its hue.

## 4. Motion

Glyphs cannot motion-blur: content crossing more than about one cell per frame strobes. Keep
foreground parallax moderate (raise the camera, shorten the rail), and let the hold be a slow push.

## 5. QA

`npx hyperframes render --format png-sequence -o <dir>` then
`python3 ascii_shimmer.py <dir> --cell 12x24 --spans <move>,<hold>`. Reference numbers from the
test film: hold blips 0.12% and jitter 1.03; fly-through blips 1.2% and jitter 2.25. Look at 1:1 crops of
two consecutive frames in the fastest move, and at the smallest text.
