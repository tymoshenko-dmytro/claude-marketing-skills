#!/usr/bin/env node
// video-3d seek-order test (generalised from the models reel's seek-order and probe tools).
// Serves a film folder, opens it in HyperFrames' own chrome-headless-shell on the GPU path, waits for the
// build hold, then seeks by dispatching `hf-seek` (awaiting e.detail.waitUntil) and hashes each frame:
// first in order, then in a seeded shuffled order, then in reverse. Any state carried from one seek to the
// next shows up as a mismatch. Worker-count renders cannot see it: every worker seeks in order inside its
// chunk, so a carried-state bug renders identically with 1 or 4 workers (the models reel: 226 of 484
// frames wrong when shuffled, all three CLI renders identical).
//
//   node seek-order-test.mjs <film dir> [--page index.html] [--fps 30] [--step 3] [--cuts 4.5,8.5,...]
//        [--capture screenshot|canvas] [--canvas "#gl"] [--seed 12345] [--soft] [--timeout 180000]
//        [--chrome <path>] [--out report.json]
//
// --cuts      section/cut times (s): frames cut-1, cut, cut+1 are added to the every-`--step` sample
// --capture   screenshot (default: the page as captured, DOM labels included; works for WebGPU canvases)
//             or canvas (canvas.toDataURL: faster; WebGL with preserveDrawingBuffer only)
// --soft      SwiftShader instead of the GPU (compare like with like - never mix backends)
// Also reports: a rejected or missing build hold, page errors, window.__info.errors (renderAt try/catch
// logs), and blank frames (every sampled frame hashes the same).
// The HyperFrames runtime is NOT loaded: the page's own hf-seek handlers run; GSAP timelines and
// sub-compositions mounted by the runtime are not exercised (test those with worker renders).
// Needs puppeteer-core: a local install, or the copy inside the hyperframes npx cache (found automatically).
import http from "node:http";
import fs from "node:fs";
import path from "node:path";
import os from "node:os";
import { createHash } from "node:crypto";
import { pathToFileURL } from "node:url";

const argv = process.argv.slice(2), opt = { _: [] };
for (let i = 0; i < argv.length; i++) {
  if (argv[i].startsWith("--")) opt[argv[i].slice(2)] = argv[i + 1] && !argv[i + 1].startsWith("--") ? argv[++i] : true;
  else opt._.push(argv[i]);
}
if (!opt._[0]) { console.error("usage: node seek-order-test.mjs <film dir> [--fps 30] [--step 3] [--cuts a,b,...] [--capture screenshot|canvas]"); process.exit(2); }
const ROOT = path.resolve(opt._[0]), PAGE = opt.page || "index.html";
const FPS = Number(opt.fps || 30), STEP = Math.max(1, Number(opt.step || 3)), TIMEOUT = Number(opt.timeout || 180000);
const CAPTURE = opt.capture || "screenshot", CANVAS = opt.canvas || "canvas", SEED = Number(opt.seed || 12345);

async function loadPuppeteer() {
  try { return (await import("puppeteer-core")).default; } catch {}
  const npx = path.join(os.homedir(), ".npm/_npx");
  const cands = fs.existsSync(npx) ? fs.readdirSync(npx).map((d) => path.join(npx, d, "node_modules/puppeteer-core"))
    .filter((p) => fs.existsSync(path.join(p, "package.json"))).sort((a, b) => fs.statSync(b).mtimeMs - fs.statSync(a).mtimeMs) : [];
  if (!cands.length) throw new Error("puppeteer-core not found: npm i -D puppeteer-core (or run any `npx hyperframes` once)");
  return (await import(pathToFileURL(path.join(cands[0], "lib/puppeteer/puppeteer-core.js")).href)).default;
}
function findChrome() {
  if (opt.chrome) return opt.chrome;
  const base = path.join(os.homedir(), ".cache/hyperframes/chrome/chrome-headless-shell");
  const vers = fs.existsSync(base) ? fs.readdirSync(base).sort() : [];
  for (const v of vers.reverse()) for (const sub of fs.readdirSync(path.join(base, v))) {
    const exe = path.join(base, v, sub, "chrome-headless-shell");
    if (fs.existsSync(exe)) return exe;
  }
  throw new Error("chrome-headless-shell not found under ~/.cache/hyperframes - run `npx hyperframes browser` or pass --chrome");
}

const MIME = { ".html": "text/html", ".js": "text/javascript", ".mjs": "text/javascript", ".json": "application/json", ".css": "text/css",
  ".png": "image/png", ".jpg": "image/jpeg", ".webp": "image/webp", ".svg": "image/svg+xml", ".ttf": "font/ttf", ".otf": "font/otf",
  ".woff2": "font/woff2", ".glb": "model/gltf-binary", ".gltf": "model/gltf+json", ".bin": "application/octet-stream", ".ktx2": "image/ktx2",
  ".hdr": "application/octet-stream", ".exr": "application/octet-stream", ".cube": "text/plain", ".mp4": "video/mp4", ".webm": "video/webm", ".mov": "video/quicktime" };
const server = http.createServer((req, res) => {
  const p = path.join(ROOT, decodeURIComponent(new URL(req.url, "http://x").pathname));
  if (!p.startsWith(ROOT) || !fs.existsSync(p) || fs.statSync(p).isDirectory()) { res.writeHead(404); res.end(); return; }
  res.writeHead(200, { "content-type": MIME[path.extname(p).toLowerCase()] || "application/octet-stream" });
  fs.createReadStream(p).pipe(res);
});
await new Promise((r) => server.listen(0, "127.0.0.1", r));

const gpu = opt.soft
  ? ["--use-gl=angle", "--use-angle=swiftshader", "--enable-unsafe-swiftshader", "--disable-gpu-compositing"]
  : ["--use-gl=angle", "--use-angle=" + (process.platform === "darwin" ? "metal" : "default"), "--enable-gpu-rasterization", "--enable-unsafe-webgpu"];
const puppeteer = await loadPuppeteer();
const browser = await puppeteer.launch({ executablePath: findChrome(), headless: "shell", protocolTimeout: TIMEOUT + 60000,
  args: ["--no-sandbox", "--enable-webgl", "--ignore-gpu-blocklist", "--force-device-scale-factor=1", "--force-color-profile=srgb",
    "--window-size=1920,1080", "--hide-scrollbars", "--font-render-hinting=none", "--disable-background-timer-throttling",
    "--disable-renderer-backgrounding", "--disable-backgrounding-occluded-windows", ...gpu] });
let code = 0;
try {
  const page = await browser.newPage();
  await page.setViewport({ width: 1920, height: 1080, deviceScaleFactor: 1 });
  const pageErrors = [];
  page.on("pageerror", (e) => pageErrors.push(e.message));
  page.on("console", (m) => { if (m.type() === "error") pageErrors.push(m.text()); });
  const t0 = Date.now();
  await page.goto(`http://127.0.0.1:${server.address().port}/${PAGE}`, { waitUntil: "load", timeout: TIMEOUT });
  const hold = await page.evaluate(async (ms) => {
    const holds = Object.values((window.__hf && window.__hf.buildReady) || {});
    if (!holds.length) return "NO BUILD HOLD";
    const to = new Promise((_, rej) => setTimeout(() => rej(new Error("timeout")), ms));
    try { await Promise.race([Promise.all(holds), to]); return "ready"; } catch (e) { return "REJECTED: " + ((e && e.message) || e); }
  }, TIMEOUT);
  console.log(`build hold: ${hold} (${Date.now() - t0} ms)`);
  if (hold !== "ready") { code = 2; throw new Error("the build hold did not resolve - the CLI would render a BLANK film and exit 0"); }
  const dur = Number(opt.duration || await page.evaluate(() => document.querySelector("[data-composition-id]")?.getAttribute("data-duration")));
  if (!dur) throw new Error("no data-duration on the root - pass --duration");
  const N = Math.round(dur * FPS), frames = new Set();
  for (let f = 0; f < N; f += STEP) frames.add(f);
  for (const c of String(opt.cuts || "").split(",").filter(Boolean)) { const f = Math.round(Number(c) * FPS); for (const d of [-1, 0, 1]) if (f + d >= 0 && f + d < N) frames.add(f + d); }
  const list = [...frames].sort((a, b) => a - b);

  const grab = async (f) => {
    const url = await page.evaluate(async (t, mode, sel) => {
      const ps = [];
      window.dispatchEvent(new CustomEvent("hf-seek", { detail: { time: t, waitUntil: (p) => ps.push(p) } }));
      await Promise.all(ps);
      if (mode === "canvas") return document.querySelector(sel).toDataURL("image/png");
      await new Promise((r) => requestAnimationFrame(() => requestAnimationFrame(r)));
      return null;
    }, f / FPS, CAPTURE, CANVAS);
    const bytes = url ? url : await page.screenshot({ type: "png", clip: { x: 0, y: 0, width: 1920, height: 1080 } });
    return createHash("md5").update(bytes).digest("hex");
  };
  const ref = new Map();
  for (const f of list) ref.set(f, await grab(f));
  let s = SEED >>> 0; const rnd = () => ((s = (Math.imul(s, 1103515245) + 12345) >>> 0) / 4294967296);
  const shuffled = [...list]; for (let i = shuffled.length - 1; i > 0; i--) { const j = Math.floor(rnd() * (i + 1)); [shuffled[i], shuffled[j]] = [shuffled[j], shuffled[i]]; }
  const bad = [], back = [];
  for (const f of shuffled) if ((await grab(f)) !== ref.get(f)) bad.push(f);
  for (const f of [...list].reverse()) if ((await grab(f)) !== ref.get(f)) back.push(f);
  const distinct = new Set(ref.values()).size;
  const infoErrors = await page.evaluate(() => (window.__info && window.__info.errors) || []);
  const report = { film: ROOT, frames: list.length, fps: FPS, duration: dur, capture: CAPTURE, backend: opt.soft ? "swiftshader" : "gpu",
    shuffledMismatches: bad.length, reverseMismatches: back.length, firstShuffled: bad.slice(0, 20), firstReverse: back.slice(0, 20),
    distinctFrames: distinct, renderAtErrors: infoErrors.slice(0, 10), pageErrors: pageErrors.slice(0, 10) };
  console.log(`frames ${list.length} | shuffled mismatches ${bad.length} ${JSON.stringify(bad.slice(0, 12))} | reverse mismatches ${back.length} ${JSON.stringify(back.slice(0, 12))}`);
  console.log(`distinct frames ${distinct}${distinct <= 1 ? "  <- BLANK OR FROZEN OUTPUT" : ""} | renderAt errors ${infoErrors.length} | page errors ${pageErrors.length}`);
  if (opt.out) fs.writeFileSync(path.resolve(opt.out), JSON.stringify(report, null, 1));
  if (bad.length || back.length || distinct <= 1 || infoErrors.length) code = 1;
} catch (err) {
  console.error(String((err && err.message) || err)); if (!code) code = 2;
} finally { await browser.close(); server.close(); }
process.exit(code);
