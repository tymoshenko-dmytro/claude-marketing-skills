# Rendered looks - toon, outlines, print, dither, CRT, ink and paper, a wipe between looks

Proven in a test film (the styles reel: 44 s, 11 looks over one still life and one camera move; 4-worker
and 1-worker PNG sequences identical, 1,320/1,320 frames; shimmer numbers in QA below).
`looks.js` here is that film's look module with its base class renamed `FilmPixelPass` (three also ships
a `FilmPass` - grain) and exported together with `GLSL_COMMON`.

## The film-pixel rule

The composer runs at pixel ratio 2 (edges supersampled). Every grid pass works in FILM pixels:
`fp = floor(gl_FragCoord.xy / uPR)`, `uPR = target width / 1920` (1 to the screen, 2 into a 2x target),
sampling at film-pixel centres (one bilinear tap in a 2x target = the exact 2x2 box). `FilmPixelPass` sets
`uPR` itself. Stock passes count TARGET pixels - fix them as in the table.

## Chains (all after `OutputPass` unless noted; `composer.render(0)`; colours = the film's tokens via `hex3()`)

| Look | Chain | Set from t / frame |
|---|---|---|
| toon + hull outline | `MeshToonMaterial` (3-step `RedFormat` gradient map, `NearestFilter`) -> `HullRenderPass(scene, camera, new OutlineEffect(renderer, {...}))` -> `OutputPass` | - |
| toon + OutlinePass | `RenderPass` -> `OutlinePass` (`pulsePeriod = 0`) -> `OutputPass` | `edgeStrength` |
| toon + Sobel ink | `RenderPass` -> `OutputPass` -> `SavePass` -> `ShaderPass(LuminosityShader)` -> `ShaderPass(SobelOperatorShader)` (`sobel.setSize = () => {}`, `resolution` = (1920, 1080): it starts at (0, 0) and is also the tap spacing) -> `SobelInkPass({ tColor: save.renderTarget.texture, ink })` | - |
| halftone (CMY on paper) | `RenderPass` -> `OutputPass` -> `InvertPass(tint, levels, true)` -> `HalftonePass` (`halftone.setSize = () => {}`, `uniforms.width/height` = 1920 x 1080: grid in film px) -> `InvertPass(paper)` | - |
| dot screen | `RenderPass` -> `OutputPass` -> `DotScreenPass` with `scale = 2 * PI / (period * 2)` at pixel ratio 2 | - |
| 1-bit dither | `DitherPass({ mode: "1bit", dot: 2, inks, levels })` | - |
| palette dither | `DitherPass({ mode: "palette", dot: 3, palette: [8 hexes] })` | - |
| CRT | `RenderPass` -> `UnrealBloomPass` -> `OutputPass` -> `CrtPass()` | `uFlick = 1 + 0.03 * (hash01(frame) - 0.5)` (`hash01`: `../post/post-kit.js`), `uRoll = (u * 0.23) % 1` |
| pixel art | `RenderPixelatedPass(pixelSize = film px * 2, ...)` (replaces RenderPass) -> `OutputPass` | set `normalEdgeStrength` / `depthEdgeStrength` AFTER construction |
| ink and paper | `RenderPass` -> `OutputPass` -> `InkPaperPass(scene, camera, { paper, ink, wash, shade, accent, rig: { show: [keyOnlyLight], hide: [otherLights] } })` | `uStep = Math.floor(frame / 3)` (boil at 10 fps) |
| look switch | render look A with `renderToScreen = false`, copy its read buffer to a 2x target (`ShaderPass(CopyShader)`), render look B, `WipeQuad` mixes them | `uEdge` from t |

One composer, one prebuilt pass list per look swapped into `composer.passes` each frame (the styles reel
used a `chain()` / `runChain()` pair); render every look once in the build (light toggles change program
keys).

## Traps (measured in the styles reel)

- `OutlineEffect.render()` never clears (`renderer.autoClear = this.autoClear`, undefined): with a null
  `scene.background` the frame depends on what the buffer held before (seek order). `HullRenderPass` clears,
  renders, then calls `effect.renderOutline()`. Hull width is in NDC: ~4 px horizontal, ~2.3 px vertical.
- `OutlinePass` is additive (only brightens, no dark ink) and its edge stays ~2 film px at any
  `edgeThickness` (edges found at half resolution).
- `HalftonePass` is RGB light on black with a dot area ~ pi * v^2.25 of a cell: mid-tones print dark and an
  orange printed red until `InvertPass(..., dotGain = true)` fed it `(ink / pi)^(1 / 2.25)`. Lift only
  near-neutral pixels (a lifted cool grey printed blue).
- `RenderPixelatedPass` options use `||` (0 becomes the default). It crawls under a perspective orbit (3.4% of
  art pixels change per frame in a hold, one in ten as A-B-A); texel snapping only works for ortho/pan moves.
- Hatching from luminance hatches a whole dark studio: tones come from a key-light-only render (white Lambert
  override, the key at intensity pi, every other light and the environment off). Detect the accent by chroma
  (max - min), not saturation - dark greys have high saturation.
- A coarse lathe profile (14 points) shows facets in toon bands - spline it (120 points).
- Toon bands keep exact colours (46% of the lit band in three values); tone mapping still shifts the token.

## QA

`python3 ../ascii/ascii_shimmer.py <section pngs> --cell WxH` and `python3 ../qa/look_shimmer.py <dir>
--cell WxH` (exact per-cell bytes, A-B-A blips, revisits). For hard-threshold looks (dither, pixel art, toon
bands) jitter sits at 2.0 for any clean step - judge them by blips. Hold blips measured: 1-bit 0.001%,
palette 0.011%, halftone 0.063%, pixel art 0.32% (exact; the crawl). CRT and ink exceed jitter 2 on purpose.
Bitrate at CRF 10: dither, halftone and the CRT mask are the expensive sections (whole film 10.3 Mbit/s).
