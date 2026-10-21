// GPU ambient-occlusion baker (capability 4.7): runs ONCE in the build, writes one AO texture per
// receiver in that receiver's second UV set (uv1). Deterministic: a fixed Fibonacci set of
// directions, no Math.random, the same draws in the same order in every worker.
//
// For each direction w on the sphere: render the occluders' depth seen from w (orthographic,
// float target), then draw every receiver UNWRAPPED (gl_Position = uv1) and add
// visibility(w) * max(0, n.w) into R and max(0, n.w) into G of the receiver's target (additive),
// then resolve AO = R / G (+ a small blur). Dividing by the open sum cancels the rounding that a
// HalfFloat accumulator piles up over hundreds of additions (unnormalised it read 0.96 in the open).
//
//   const ao = bakeAO(renderer, { occluders: [vase, plinth], receivers: [{ mesh: floor, size: 1024 }, ...] });
//   material.aoMap = ao.get(floor); // texture.channel = 1 (uv1)
import * as THREE from "three";

const depthVS = `varying float vDepth;
void main() { vec4 mv = modelViewMatrix * vec4(position, 1.0); vDepth = -mv.z; gl_Position = projectionMatrix * mv; }`;
const depthFS = `varying float vDepth; void main() { gl_FragColor = vec4(vDepth, 0.0, 0.0, 1.0); }`;

const bakeVS = `
attribute vec2 uv1;
uniform mat4 uLightView, uLightProj;
uniform float uNormalOffset;
varying vec4 vLight; varying vec3 vN;
void main() {
  vec4 wp = modelMatrix * vec4(position, 1.0);
  vec3 wn = normalize(mat3(modelMatrix) * normal);
  wp.xyz += wn * uNormalOffset;                       // normal offset against self-occlusion acne
  vLight = uLightProj * uLightView * wp;
  vLight.w = -(uLightView * wp).z;                    // view depth along the bake direction
  vN = wn;
  gl_Position = vec4(uv1 * 2.0 - 1.0, 0.0, 1.0);      // unwrap: draw the surface in its uv1 layout
}`;
const bakeFS = `
uniform sampler2D uDepth;
uniform vec3 uDir;
uniform float uWeight, uBias;
varying vec4 vLight; varying vec3 vN;
void main() {
  float c = dot(normalize(vN), uDir);
  if (c <= 0.0) discard;
  vec2 st = vLight.xy * 0.5 + 0.5;                    // orthographic: clip xy is already NDC
  float occ = 0.0;
  if (st.x > 0.0 && st.x < 1.0 && st.y > 0.0 && st.y < 1.0) {
    float d = texture2D(uDepth, st).r;
    occ = (d > 0.0 && vLight.w - d > uBias) ? 1.0 : 0.0;
  }
  gl_FragColor = vec4((1.0 - occ) * c * uWeight, c * uWeight, 0.0, 1.0);   // R visible, G open: AO = R / G
}`;

// N directions spread evenly over the sphere (golden-angle spiral), no randomness
export function fibonacciSphere(n) {
  const out = [], ga = Math.PI * (3 - Math.sqrt(5));
  for (let i = 0; i < n; i++) {
    const y = 1 - (2 * (i + 0.5)) / n, r = Math.sqrt(1 - y * y), a = ga * i;
    out.push(new THREE.Vector3(Math.cos(a) * r, y, Math.sin(a) * r));
  }
  return out;
}

export function bakeAO(renderer, { occluders, receivers, directions = 256, depthSize = 1024,
  center = new THREE.Vector3(), radius = 3, normalOffset = 0.006, bias = 0.004, blur = 1 }) {
  const dirs = fibonacciSphere(directions);
  const depthRT = new THREE.WebGLRenderTarget(depthSize, depthSize, { type: THREE.FloatType,
    minFilter: THREE.NearestFilter, magFilter: THREE.NearestFilter, depthBuffer: true });
  const depthMat = new THREE.ShaderMaterial({ vertexShader: depthVS, fragmentShader: depthFS, side: THREE.DoubleSide });
  const bakeMat = new THREE.ShaderMaterial({ vertexShader: bakeVS, fragmentShader: bakeFS, side: THREE.DoubleSide,
    depthTest: false, depthWrite: false, blending: THREE.CustomBlending,
    blendEquation: THREE.AddEquation, blendSrc: THREE.OneFactor, blendDst: THREE.OneFactor,
    uniforms: { uDepth: { value: depthRT.texture }, uDir: { value: new THREE.Vector3() }, uWeight: { value: 4 / directions },
      uBias: { value: bias }, uNormalOffset: { value: normalOffset },
      uLightView: { value: new THREE.Matrix4() }, uLightProj: { value: new THREE.Matrix4() } } });

  const cam = new THREE.OrthographicCamera(-radius, radius, radius, -radius, 0.01, radius * 4);
  const occScene = new THREE.Scene(), recScene = new THREE.Scene();
  occScene.overrideMaterial = depthMat; recScene.overrideMaterial = bakeMat;
  const proxies = (list, scene) => list.map((m) => { m.updateMatrixWorld(true);
    const p = new THREE.Mesh(m.geometry); p.matrixAutoUpdate = false; p.matrix.copy(m.matrixWorld);
    p.matrixWorld.copy(m.matrixWorld); p.frustumCulled = false; scene.add(p); return p; });
  proxies(occluders, occScene);

  const targets = new Map();
  const recs = receivers.map(({ mesh, size = 512 }) => {
    const rt = new THREE.WebGLRenderTarget(size, size, { type: THREE.HalfFloatType, depthBuffer: false,
      minFilter: THREE.LinearFilter, magFilter: THREE.LinearFilter, generateMipmaps: false });
    targets.set(mesh, rt);
    const s = new THREE.Scene(); s.overrideMaterial = bakeMat; proxies([mesh], s);
    return { mesh, rt, scene: s };
  });

  const prev = { rt: renderer.getRenderTarget(), auto: renderer.autoClear, cc: new THREE.Color(), ca: renderer.getClearAlpha() };
  renderer.getClearColor(prev.cc);
  for (const r of recs) { renderer.setRenderTarget(r.rt); renderer.setClearColor(0x000000, 0); renderer.clear(); }
  renderer.autoClear = false;
  const up = new THREE.Vector3();
  for (const w of dirs) {
    up.set(0, 1, 0); if (Math.abs(w.y) > 0.99) up.set(1, 0, 0);
    cam.position.copy(center).addScaledVector(w, radius * 2); cam.up.copy(up); cam.lookAt(center);
    cam.updateMatrixWorld(); cam.updateProjectionMatrix();
    renderer.setRenderTarget(depthRT); renderer.setClearColor(0x000000, 0); renderer.clear();
    renderer.render(occScene, cam);
    bakeMat.uniforms.uDir.value.copy(w);
    bakeMat.uniforms.uLightView.value.copy(cam.matrixWorldInverse);
    bakeMat.uniforms.uLightProj.value.copy(cam.projectionMatrix);
    for (const r of recs) { renderer.setRenderTarget(r.rt); renderer.render(r.scene, cam); }
  }
  renderer.autoClear = prev.auto;

  // resolve R / G, with a small separable box blur in uv1 space (hides the direction count on hard contacts)
  for (const r of recs) blurInPlace(renderer, r.rt, blur);

  renderer.setRenderTarget(prev.rt); renderer.setClearColor(prev.cc, prev.ca);
  depthRT.dispose(); depthMat.dispose(); bakeMat.dispose();
  for (const r of recs) { r.rt.texture.channel = 1; r.rt.texture.wrapS = THREE.RepeatWrapping; r.rt.texture.wrapT = THREE.ClampToEdgeWrapping; }
  return { get: (mesh) => targets.get(mesh).texture, targets, directions: dirs.length };
}

function blurInPlace(renderer, rt, radius) {
  const tmp = rt.clone();
  const mat = new THREE.ShaderMaterial({ depthTest: false, depthWrite: false,
    uniforms: { uTex: { value: null }, uStep: { value: new THREE.Vector2() }, uR: { value: radius }, uResolve: { value: 0 } },
    vertexShader: `varying vec2 vUv; void main() { vUv = uv; gl_Position = vec4(position.xy, 0.0, 1.0); }`,
    fragmentShader: `uniform sampler2D uTex; uniform vec2 uStep; uniform float uR; varying vec2 vUv;
      uniform float uResolve;
      void main() { vec3 s = vec3(0.0); float n = 0.0;
        for (float i = -4.0; i <= 4.0; i += 1.0) { if (abs(i) > uR) continue; s += texture2D(uTex, vUv + uStep * i).rgb; n += 1.0; }
        s /= n;
        gl_FragColor = uResolve > 0.5 ? vec4(vec3(s.g > 1e-4 ? s.r / s.g : 1.0), 1.0) : vec4(s, 1.0); }` });
  const quad = new THREE.Mesh(new THREE.PlaneGeometry(2, 2), mat); quad.frustumCulled = false;
  const sc = new THREE.Scene(); sc.add(quad); const cam = new THREE.Camera();
  const w = rt.width, h = rt.height;
  mat.uniforms.uTex.value = rt.texture; mat.uniforms.uStep.value.set(1 / w, 0);
  renderer.setRenderTarget(tmp); renderer.render(sc, cam);
  mat.uniforms.uTex.value = tmp.texture; mat.uniforms.uStep.value.set(0, 1 / h); mat.uniforms.uResolve.value = 1;
  renderer.setRenderTarget(rt); renderer.render(sc, cam);
  tmp.dispose(); mat.dispose(); quad.geometry.dispose();
}
