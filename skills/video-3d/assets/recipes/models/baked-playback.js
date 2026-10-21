// video-3d: play back simulations baked at build time (from the models reel's scene module:
// bodiesAt, the VAT block, clothAt). The page never steps an engine; it reads the frame for t.
//
// Rigid bodies - sim JSON (written by a Node bake you write, with a fixed dt - see the models README):
//   { fps, frames, bodies: [{ spawn, ... }], tracks: [[x,y,z,qx,qy,qz,qw, ... one 7-tuple per frame], ...] }
// Cloth / soft bodies - a vertex animation texture (VAT, written by your own Node bake):
//   cloth-vat.bin = Uint16 xyz per vertex per frame, quantised to the bounding box
//   cloth-vat.json = { fps, frames, grid, lo: [x,y,z], hi: [x,y,z] }   (a grid x grid sheet)
// Bake files must not contain timings (a rebake must be byte-identical).
import * as THREE from "three";

const lerp = (a, b, k) => a + (b - a) * k;
const _q1 = new THREE.Quaternion(), _q2 = new THREE.Quaternion();

// frame position for local time t: integer neighbours + mix, clamped to the bake
function frameAt(fps, frames, t) {
  const f = Math.max(0, Math.min(frames - 1, t * fps));
  const i0 = Math.min(frames - 1, Math.floor(f + 1e-6)), i1 = Math.min(frames - 1, i0 + 1);
  return { f, i0, i1, a: i1 > i0 ? f - i0 : 0 };
}

// Set every mesh from the baked tracks at local time t (lerp positions, slerp rotations between the
// neighbouring film frames); a body is hidden before its spawn frame.
export function rigidAt(sim, meshes, t) {
  const { f, i0, i1, a } = frameAt(sim.fps, sim.frames, t);
  meshes.forEach((m, i) => {
    const tr = sim.tracks[i], o0 = i0 * 7, o1 = i1 * 7;
    m.visible = i0 >= (sim.bodies[i].spawn ?? 0);
    m.position.set(lerp(tr[o0], tr[o1], a), lerp(tr[o0 + 1], tr[o1 + 1], a), lerp(tr[o0 + 2], tr[o1 + 2], a));
    _q1.set(tr[o0 + 3], tr[o0 + 4], tr[o0 + 5], tr[o0 + 6]).normalize();
    _q2.set(tr[o1 + 3], tr[o1 + 4], tr[o1 + 5], tr[o1 + 6]).normalize();
    m.quaternion.slerpQuaternions(_q1, _q2, a);
  });
  return f;
}

// VAT: decode the quantised bake into a float texture (rows = frames, texels = vertices), build the
// grid geometry (aVid = vertex id) and the uniforms. Patch BOTH the colour material and a
// MeshDepthMaterial (customDepthMaterial) so the shadow moves with the cloth.
export function buildVat(meta, bin) {
  const N = meta.grid, NV = N * N, NF = meta.frames, q = new Uint16Array(bin), lo = meta.lo, hi = meta.hi;
  const vat = new Float32Array(NV * NF * 4), centroid = new Float32Array(NF * 3);
  for (let f = 0; f < NF; f++) for (let v = 0; v < NV; v++) {
    const s = (f * NV + v) * 3, d = (f * NV + v) * 4;
    for (let k = 0; k < 3; k++) { const x = lo[k] + (q[s + k] / 65535) * (hi[k] - lo[k]); vat[d + k] = x; centroid[f * 3 + k] += x / NV; }
    vat[d + 3] = 1;
  }
  const texture = new THREE.DataTexture(vat, NV, NF, THREE.RGBAFormat, THREE.FloatType);
  texture.minFilter = texture.magFilter = THREE.NearestFilter; texture.generateMipmaps = false; texture.needsUpdate = true;
  const geometry = new THREE.BufferGeometry(), vid = new Float32Array(NV), uv = new Float32Array(NV * 2), pos = new Float32Array(NV * 3), idx = [];
  for (let j = 0; j < N; j++) for (let i = 0; i < N; i++) {
    const id = j * N + i; vid[id] = id; uv[id * 2] = i / (N - 1); uv[id * 2 + 1] = j / (N - 1);
    pos.set(vat.subarray(id * 4, id * 4 + 3), id * 3);                     // frame 0 (the shader replaces it)
    if (i < N - 1 && j < N - 1) idx.push(id, id + 1, id + N, id + 1, id + N + 1, id + N);
  }
  geometry.setAttribute("position", new THREE.BufferAttribute(pos, 3));
  geometry.setAttribute("aVid", new THREE.BufferAttribute(vid, 1));
  geometry.setAttribute("uv", new THREE.BufferAttribute(uv, 2));
  geometry.setIndex(idx);
  const uniforms = { uVat: { value: texture }, uF0: { value: 0 }, uF1: { value: 0 }, uMixF: { value: 0 }, uGrid: { value: N } };
  return { texture, geometry, uniforms, centroid, meta };
}

const VAT_HEAD = `uniform sampler2D uVat; uniform int uF0; uniform int uF1; uniform float uMixF; uniform int uGrid; attribute float aVid;
  vec3 vatAt(int id) { return mix(texelFetch(uVat, ivec2(id, uF0), 0).xyz, texelFetch(uVat, ivec2(id, uF1), 0).xyz, uMixF); }`;
const VAT_POS = `vec3 transformed = vatAt(int(aVid + 0.5));`;
const VAT_NRM = `int vId = int(aVid + 0.5), gi = vId % uGrid, gj = vId / uGrid;
  vec3 dpx = vatAt(gj * uGrid + min(gi + 1, uGrid - 1)) - vatAt(gj * uGrid + max(gi - 1, 0));
  vec3 dpy = vatAt(min(gj + 1, uGrid - 1) * uGrid + gi) - vatAt(max(gj - 1, 0) * uGrid + gi);
  vec3 objectNormal = normalize(cross(dpx, dpy));`;

// material.onBeforeCompile = vatPatch(vat.uniforms, true); depthMaterial.onBeforeCompile = vatPatch(vat.uniforms, false)
export const vatPatch = (uniforms, withNormal) => (sh) => {
  Object.assign(sh.uniforms, uniforms);
  sh.vertexShader = sh.vertexShader.replace("#include <common>", "#include <common>\n" + VAT_HEAD).replace("#include <begin_vertex>", VAT_POS);
  if (withNormal) sh.vertexShader = sh.vertexShader.replace("#include <beginnormal_vertex>", VAT_NRM);
};

// A ready mesh: colour material + shadow depth material, both patched; never frustum-culled (the
// geometry's bounds are frame 0's, the shader moves every vertex).
export function vatMesh(vat, material) {
  material.onBeforeCompile = vatPatch(vat.uniforms, true);
  const depth = new THREE.MeshDepthMaterial({ depthPacking: THREE.RGBADepthPacking, side: material.side });
  depth.onBeforeCompile = vatPatch(vat.uniforms, false);
  const mesh = new THREE.Mesh(vat.geometry, material);
  mesh.customDepthMaterial = depth; mesh.castShadow = mesh.receiveShadow = true; mesh.frustumCulled = false;
  return mesh;
}

// Per frame: pick the two baked rows for local time t; returns the cloth's centroid (camera targets).
export function vatAt(vat, t) {
  const { f, i0, i1, a } = frameAt(vat.meta.fps, vat.meta.frames, t), c = vat.centroid;
  vat.uniforms.uF0.value = i0; vat.uniforms.uF1.value = i1; vat.uniforms.uMixF.value = a;
  return { frame: f, centre: new THREE.Vector3(lerp(c[i0 * 3], c[i1 * 3], a), lerp(c[i0 * 3 + 1], c[i1 * 3 + 1], a), lerp(c[i0 * 3 + 2], c[i1 * 3 + 2], a)) };
}
