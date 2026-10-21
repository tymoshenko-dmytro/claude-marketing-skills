// video-3d scene skeleton. Everything on screen is a pure function of t (HyperFrames seeks
// frames out of order in parallel workers). Replace the demo object in build() and the camera
// path in cameraAt(); keep the structure. Rules: video-3d/references/contract.md.
import * as THREE from "three";
import { RoomEnvironment } from "three/addons/environments/RoomEnvironment.js";

try {
  const W = 1920, H = 1080, SS = 2, FOV = 24;                 // SS: supersample edges (particles: 1)
  const T = { orbitA: 0.3, orbitB: 2.6, END: 4.0 };          // every time the film uses, in one place
  const SEED = 7;

  // ---- math (same as video-moves camera-kit.js) ----
  const clamp01 = (x) => Math.max(0, Math.min(1, x)), lerp = (a, b, k) => a + (b - a) * k;
  const ease = (x) => (x < 0.5 ? 4 * x * x * x : 1 - Math.pow(-2 * x + 2, 3) / 2);
  const seg = (t, a, b, fn = ease) => fn(clamp01((t - a) / (b - a)));
  const logLerp = (a, b, k) => Math.exp(lerp(Math.log(a), Math.log(b), k));
  const rad = (d) => (d * Math.PI) / 180;
  function rng(seed) { let a = seed >>> 0; return () => { a = (a + 0x6d2b79f5) >>> 0; let t = a;
    t = Math.imul(t ^ (t >>> 15), t | 1); t ^= t + Math.imul(t ^ (t >>> 7), t | 61); return ((t ^ (t >>> 14)) >>> 0) / 4294967296; }; }

  // ---- renderer: fixed buffer, supersampled, transparent over the CSS ground ----
  const renderer = new THREE.WebGLRenderer({ canvas: document.getElementById("gl"),
    antialias: true, alpha: true, preserveDrawingBuffer: true });
  renderer.setPixelRatio(SS); renderer.setSize(W, H, false); renderer.setClearColor(0x000000, 0);
  renderer.toneMapping = THREE.NeutralToneMapping;           // lit objects: then MEASURE hero colours
  // flat colours instead: THREE.ColorManagement.enabled = false; renderer.outputColorSpace = THREE.LinearSRGBColorSpace;

  const scene = new THREE.Scene();
  const camera = new THREE.PerspectiveCamera(FOV, W / H, 0.1, 200);
  const pmrem = new THREE.PMREMGenerator(renderer);
  scene.environment = pmrem.fromScene(new RoomEnvironment(), 0.04).texture;
  scene.environmentIntensity = 0.55;

  // ---- build once (await fonts, textures, data, models here - never at seek time) ----
  async function build() {
    const r = rng(SEED);
    const shape = new THREE.Shape();                         // demo: a rounded slab; use the film's SVG
    const w = 2.2, h = 1.4, rr = 0.25;
    shape.moveTo(-w / 2 + rr, -h / 2); shape.lineTo(w / 2 - rr, -h / 2); shape.quadraticCurveTo(w / 2, -h / 2, w / 2, -h / 2 + rr);
    shape.lineTo(w / 2, h / 2 - rr); shape.quadraticCurveTo(w / 2, h / 2, w / 2 - rr, h / 2);
    shape.lineTo(-w / 2 + rr, h / 2); shape.quadraticCurveTo(-w / 2, h / 2, -w / 2, h / 2 - rr);
    shape.lineTo(-w / 2, -h / 2 + rr); shape.quadraticCurveTo(-w / 2, -h / 2, -w / 2 + rr, -h / 2);
    const geo = new THREE.ExtrudeGeometry(shape, { depth: 0.18, bevelEnabled: true, bevelSize: 0.04,
      bevelThickness: 0.04, bevelOffset: -0.04, bevelSegments: 6, curveSegments: 24 });
    geo.center();
    const mat = new THREE.MeshPhysicalMaterial({ color: new THREE.Color().setHSL(0.6 + 0.02 * r(), 0.6, 0.55),
      roughness: 0.32, clearcoat: 0.6, clearcoatRoughness: 0.25 });
    scene.add(new THREE.Mesh(geo, mat));
  }

  // ---- time: camera in real time; world state set absolutely from t ----
  function cameraAt(t) {
    const k = seg(t, T.orbitA, T.orbitB);
    const az = rad(lerp(-35, 0, k)), el = rad(lerp(18, 6, k));
    const dist = logLerp(4.2, 6.0, k);                       // distances on a log curve
    camera.position.set(dist * Math.sin(az) * Math.cos(el), dist * Math.sin(el), dist * Math.cos(az) * Math.cos(el));
    camera.lookAt(0, 0, 0); camera.updateMatrixWorld();
  }
  let ready = false;
  const info = (window.__info = { errors: [] });
  function renderAt(t) {
    if (!ready) return;
    // an exception in the hf-seek handler fails nothing: the canvas would keep the PREVIOUS frame while DOM
    // labels move on. Log it and clear to magenta, so blank_check.py and the seek-order test see it.
    try {
      cameraAt(t);
      // uniforms, visibility, label positions: all written from t here, never incremented
      renderer.render(scene, camera);
    } catch (err) {
      info.errors.push(`t=${t}: ${(err && err.stack) || err}`); console.error(err);
      renderer.setClearColor(0xff00ff, 1); renderer.clear(); renderer.setClearColor(0x000000, 0);
    }
  }

  window.addEventListener("hf-seek", (e) => renderAt(e.detail.time));
  build().then(() => {
    renderer.compile(scene, camera);
    ready = true;
    renderAt(window.__hfThreeTime || 0);                    // the runtime will not re-seek to the same t
    window.__sceneReady();
  }).catch((err) => { console.error(err); window.__sceneFail(err); });
} catch (err) { console.error(err); window.__sceneFail && window.__sceneFail(err); }
