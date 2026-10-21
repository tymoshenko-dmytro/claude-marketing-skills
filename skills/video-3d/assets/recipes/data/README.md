# Data in 3D - maps, bars, networks, terrain from data, audio, GPU state

Proven in a test film (the data reel: 41 s, 8 sections; `--workers 1` and `--workers 4` byte-identical
MP4s). That film kept one module per capability in `assets/sections/` - a layout worth copying; the
section modules themselves do not ship, so the sections below say what to build.

## Files

- `build-map.mjs` - TopoJSON countries -> `window.MAP_DATA` (regions with polygons and holes, context,
  borders, graticule), generalised from the data reel's tool (any crop, `--regions`, `--values`). With that
  film's flags it reproduced its map data exactly.
- `gpgpu.js` - `makeSim()` (GPUComputationRenderer with a seeded initial state and a real `reset()`),
  `replayAt()` (way a), `bakeLayers()` into a `WebGLArrayRenderTarget` (way b), `readLayer()` +
  `differingFloats()` for the build-time bit check. Extracted from the data reel's GPGPU section (the film's
  version was rendered; this one is syntax-checked).

## Map (12.3) in the page

- Ground (ocean, graticule, context countries, every border) drawn ONCE into a 4096 px `CanvasTexture`.
- Each region: one `ExtrudeGeometry` of all its polygons and holes -> `rotateX(-PI/2)` ->
  `toCreasedNormals(geo, 40 deg)`; height = `scale.y` from t; colour from the value, mixed in sRGB to match a
  CSS legend. ~8% of the map width is the tallest extrusion that still reads as a map.
- Borders on the TOPS: a white-on-black border mask (7 px at 4096) sampled from the map-plane position,
  only where the normal points up; all regions share one program:
  ```js
  mat.onBeforeCompile = (sh) => { Object.assign(sh.uniforms, { uBorders, uMapBox });
    sh.vertexShader = sh.vertexShader.replace("#include <common>", "#include <common>\nvarying vec2 vMapP; varying float vUp;")
      .replace("#include <begin_vertex>", "#include <begin_vertex>\nvMapP = vec2(position.x, -position.z); vUp = normal.y;");
    sh.fragmentShader = sh.fragmentShader.replace("#include <common>", "#include <common>\nvarying vec2 vMapP; varying float vUp; uniform sampler2D uBorders; uniform vec4 uMapBox;")
      .replace("#include <color_fragment>", `#include <color_fragment>
        { vec2 uv = (vMapP - uMapBox.xy) / uMapBox.zw; float b = texture2D(uBorders, uv).r * smoothstep(0.6, 0.9, vUp);
          diffuseColor.rgb *= 1.0 - 0.62 * b; }`); };
  mat.customProgramCacheKey = () => "map-borders";
  ```
- A lit map plane on an unlit apron shows its rectangle: the apron takes the same lit material.

## Bars, networks, terrain, audio, shards, BatchedMesh

- Bars: `setMatrixAt` scale-y on a box translated to stand on y = 0, `setColorAt` once; the growth
  wave starts BEFORE the section (`t0 = -0.5 + ...`) so the first frame is not a flat grid. DOM labels fade by
  the fraction of 5 rays from the camera to the anchor that no other bar blocks (no popping).
- Network: `forceSimulation(nodes).randomSource(rng(SEED)).stop()` on the same line (it starts
  a d3-timer on construction), then `sim.tick(400)`; edges are unit cylinders placed with `setMatrixAt`,
  drawn on in BFS order with an accent head.
- Terrain (features from an offline Python script you write - numpy STFT): a log-frequency spectrogram
  (4096-point STFT, magnitude interpolated at bin centres - narrow bins otherwise repeat one FFT bin as
  stairs) as heights on a 2x denser plane, tapered to 0 at the edges; contour width in pixels:
  `(0.5 - abs(fract(u) - 0.5)) / fwidth(u)`.
- Audio (the same offline script, written to a JS data file the page imports): 24 bands per 10 ms, each
  normalised to its own 8th-99th percentile, attack/release run offline; onsets from spectral flux refined
  to the attack (steepest rise of a 2 ms log-energy envelope, -20..+50 ms): 13/15 beats within 30 ms,
  median 7 ms. Waterfall row r = the spectrum at `(floor(s / dt) - r) * dt` - the past as a pure function
  of t.
- Shards: 8,000 instanced lit octahedra, closed-form motion, `setMatrixAt` per frame - cheap.
- BatchedMesh: every geometry indexed or none (`setIndex([...Array(n).keys()])` on a
  non-indexed polyhedron); `setVisibleAt` + `setMatrixAt` from t; 1 draw call (also on SwiftShader).

## GPU state (7.6) - which way

| | (a) replay per seek | (b) bake into array layers |
|---|---|---|
| cost | 0.039 ms x steps-per-frame x frame, per seek (up to ~1M particles the same) | one pass in every worker's build (~0.1-0.3 s) |
| limit | ~1-2 min of sim per shot (start it at the shot) | frames x particles x 16 B per worker <= ~0.5 GB |
| SwiftShader | ~4.9 ms per step at 36k particles: unusable | 42x slower bake, usable once |

Both are bit-identical on one GPU (checked in the build: 0 differing floats). GPU and SwiftShader drift apart
on a chaotic sim (0% bit-equal after 500 steps) - pin the backend or bake on the CPU (section 8).
Never put measured times on screen: a caption with `performance.now()` differed per worker.
