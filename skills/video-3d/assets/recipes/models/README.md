# Models, animation and baked simulations

Proven in a test film (the models reel: 46.5 s: decoders, skinned clones, mixer blends,
procedural bones, morph targets, baked rigid bodies, cloth VAT, flock, Flow ribbon, surface points; 1,395/1,395
frames identical across worker counts AND 0 mismatches in the shuffled/reverse seek test).

## Files

- `rig.js` - `makeRig()`, `pose(rig, layers)` (absolute clip times and weights + `mixer.update(0)`, undo list),
  `setMorphs()`, `aimBone()`, `headAxis()`, `lookAt()`. Generalised from the film (no materials or scale baked
  in); checked in Node: 0 mismatches over 60 shuffled and reversed seeks, while a rest-pose reset gives 15.
- `baked-playback.js` - `rigidAt(sim, meshes, t)` (lerp + slerp between baked frames, hidden before spawn);
  `buildVat(meta, bin)`, `vatMesh(vat, material)` (colour AND shadow-depth materials patched, never culled),
  `vatAt(vat, t)`. Checked in Node against the models reel's bake files. The file formats it reads are in
  its header comment.

The bakes are Node scripts you write for your own stage layout (they do not ship). They write the formats in
the `baked-playback.js` header. What the models reel's bakes used and cost:

- rigid bodies: Rapier (`@dimforge/rapier3d-compat` 0.19.3), fixed dt 1/240, 8 substeps per film frame,
  34 bodies in 0.2 s;
- cloth: own PBD, 41 x 41 grid, Uint16 quantised to the bbox, 10-13 s;
- flock: boids, 160 birds, 1 s;
- model compression: gltf-transform Draco/meshopt + `ktx2-encoder` (WASM - no native toktx).

Flock playback is yours to write next to `rigidAt()`: velocity and bank from neighbouring baked frames,
wingbeat in the vertex shader from t. Surface points on a skinned mesh: `capabilities.md` 2.11.

## Use

```js
const gltf = await new GLTFLoader().setDRACOLoader(draco).setMeshoptDecoder(MeshoptDecoder).loadAsync("assets/hero.glb");
const hero = makeRig(gltf.scene, gltf.animations, { scale: 0.4 });          // skinned meshes: frustumCulled = false
// per frame, everything from t:
const w = seg(t, 3.0, 3.6);
pose(hero, [{ clip: "Walking", time: t, weight: 1 - w }, { clip: "Jump", time: t - 3.0, weight: w, once: true }]);
setMorphs(hero, { Surprised: seg(t, 4, 4.4) });                             // after pose(): clips carry morph tracks
lookAt(hero, axis, orbAt(t), 1);                                            // recorded for undo before the next pose()
rigidAt(SIM, bodies, t - T.dropStart);
vatAt(CLOTH, t - T.clothStart);
```

## Traps (models reel)

- The mixer writes only CHANGED values, LoopOnce + `setTime` disables actions past the end - both handled
  by `pose()`; `mixer.setTime(t)` alone is fine only for looping clips at fixed weights.
- An exception in the hf-seek handler is silent (the canvas keeps the previous frame while DOM labels move):
  wrap `renderAt` in try/catch, log, clear to magenta.
- GLTFLoader sanitises node names ("UpperArm.R" -> `UpperArmR`). `KTX2Loader.parse` transfers the
  ArrayBuffer to its worker - read `byteLength` first. Decoders only in the build.
- `MeshSurfaceSampler` weights faces by LOCAL area (hands with a x100 node scale got no points): split the
  budget by world area; keep face + barycentrics (`_sampleFaceIndex()` is private in r181) and skin per frame.
- Flow: `spineOffset` defaults to 161 (set 0), `pathOffset` is a 0..1 fraction from t, closed curves only,
  the shadow pass draws the straight mesh, `frustumCulled = false`.
- Cloth: draw colliders a little smaller than their bake shapes (a 5 cm grid cuts chords through a 20 cm
  ball) and round sharp corners. Bake files carry no timings (byte-identical rebakes). Node tools in a
  non-ASCII path: `fileURLToPath`, not `new URL(...).pathname`.
- KTX2 on the GPU path: ETC1S -> ETC2, UASTC -> ASTC 4x4; the saving is GPU memory, not download size.
