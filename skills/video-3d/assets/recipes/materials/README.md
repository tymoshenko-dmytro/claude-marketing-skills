# Turned objects and baked ambient occlusion

Proven in a test film (the materials reel: 50.5 s, 14 sections: physical materials, toon, matcap, shadow
types, ShadowMesh, RectAreaLight, HDRI, baked AO, sky + lens flare + light probe; 1,515/1,515 frames
identical across auto, 4 and 1 workers). Files here are that film's, unchanged.

## lathe.js

- `vaseProfile({ wall, base, samples })` - a vessel with real wall thickness: outer wall up, a round lip, the
  inner wall down, a filleted inner floor; ordered so LatheGeometry's normals face out of the material.
  The base is slightly concave (axis 0.012 up) so only the foot ring touches a plinth (no z-fighting).
- `plinthProfile()`, `radiusAt(points, y)`.
- `turned(points, segments)` - `LatheGeometry` + a second UV set `uv1` by ARC LENGTH (the bake target for
  aoMap/lightMap; the default uv crowds texels into the lip) + `userData.indicesPerSegment`.
  Turn it into existence from t: `geo.setDrawRange(0, Math.round(segments * k) * geo.userData.indicesPerSegment)`.
- Toon looks show the profile's facets: spline it densely (the styles reel used 120 points).

## ao-bake.js

`bakeAO(renderer, { occluders, receivers: [{ mesh, size }], directions = 256, center, radius })` runs ONCE in
the build: per Fibonacci-sphere direction an orthographic float depth map of the occluders, then each receiver
drawn unwrapped (`gl_Position = uv1`) adding visible*cos to R and cos to G of a HalfFloat target; AO = R / G
(the open sum cancels the ~4% a HalfFloat accumulator loses over ~400 adds) + a 1-texel blur. 384 directions,
three receivers (512 + 2 x 1024) ~0.3 s. Use: `material.aoMap = ao.get(mesh)` (channel 1 = uv1), and
`aoMapIntensity` from t if the AO should fade in. The same baker with directions in a cone round a key light
would bake a lightMap (not built).

## Snippets from the materials reel worth lifting

```js
// shadow type switch: r181 does NOT recompile materials when shadowMap.type changes
function setShadowType(type) { renderer.shadowMap.type = type;
  if (last !== type) { for (const m of allMaterials) m.needsUpdate = true; last = type; } }
// ShadowMesh projects onto n.p = +constant (the opposite sign of THREE.Plane): a floor at height h is
shadowMesh.update(new THREE.Plane(new THREE.Vector3(0, 1, 0), +h), lightPos4);
// HDRI sun from the pixels: HDRLoader row 0 is the image TOP and three samples it as up
const u = (x + 0.5) / w, v = (y + 0.5) / h, phi = (u - 0.5) * 2 * Math.PI, th = (0.5 - v) * Math.PI;
sunDir.set(Math.cos(th) * Math.cos(phi), Math.sin(th), Math.cos(th) * Math.sin(phi));
```

- Glass (`transmission`) casts a solid black shadow: `castShadow = false` on transmissive meshes. 7.2 ms per
  frame, the costliest material.
- `RectAreaLight` has no clearcoat or sheen term: the bar reflects in the base layer only (glossy base,
  roughness ~0.1, no clearcoat). Show the light itself as an unlit tube.
- Light probes: `LightProbeGenerator.fromCubeRenderTarget` is async - bake SH at keys along the light path in
  the build (13 keys) and lerp the coefficients by t.
- Matcap rendered in the build (a lit physical sphere, ortho camera, HalfFloat target) was the most
  colour-stable material (ΔE2000 1.5 to the albedo).
- Fog colour = `scene.background` gives an infinite floor (fog runs after tone mapping, in output space).
