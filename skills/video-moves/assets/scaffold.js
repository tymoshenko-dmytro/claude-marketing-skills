// video-moves scaffold - paste after camera-kit.js in the composition's inline <script>.
// The build script defines before it:
//   const SCENES = [{ id, start, dur, story?, cut?, lead?, tail? }, ...];   // from scenes.json
//   const END = <total seconds>;
//   const ENV = [0..1, ...];   // optional: a recording's RMS per 20 ms, for the voice scope
// Each scene is a clip <div id="<id>" class="clip scene" data-start data-duration
// data-track-index="0" data-layout-allow-overlap>, optionally with a .label inside.
// Optional: <div id="dip" class="clip" data-start="0" data-duration="END" data-track-index="1">.
// The IMPL entries below are placeholders: replace the numbers with the film's own
// material (world coordinates of ITS subjects). A minimal worked example that builds and
// renders with this file as it is: references/rigs.md, section 0.

const W = 1920, H = 1080, C = CK;
const $ = (r, q) => r.querySelector(q);
const $$ = (r, q) => Array.from(r.querySelectorAll(q));
// "" (inherit), never "visible": an explicit visible beats the runtime's hidden clip and
// leaks the element into every later scene.
const show = (el, on) => { el.style.visibility = on ? "" : "hidden"; };
const storyOf = (sc) => C.makeStoryTime(C.piecewiseRate(sc.story.segs), { until: sc.dur + 0.1, s0: sc.story.s0 });
const IMPL = {};

// Colours come from the --mv-* tokens (moves.css), set per film from its own palette.
const token = (name, fallback) => getComputedStyle(document.documentElement).getPropertyValue(name).trim() || fallback;

// Voice scope: the recording's envelope scrolling on STORY time (300 px per story second).
function scopeOf(r, { pxPerSec = 300, bin = 0.02, color = token("--mv-accent-2", "#0F766E"), head = token("--mv-accent", "#2F6FED") } = {}) {
  const cv = $(r, ".scope canvas"), g = cv.getContext("2d"), Wc = cv.width, Hc = cv.height, hx = Wc - 30;
  return (s) => {
    g.clearRect(0, 0, Wc, Hc); g.fillStyle = color;
    for (let i = 0; i < ENV.length; i++) {
      const x = hx - (s - i * bin) * pxPerSec;
      if (x < 0 || x > hx) continue;
      const h = Math.max(3, ENV[i] * (Hc - 8));
      g.fillRect(Math.round(x), Math.round((Hc - h) / 2), 4, Math.round(h));
    }
    g.fillStyle = head; g.fillRect(hx + 2, 0, 3, Hc);
  };
}

// ---------------- examples - replace with the film's scenes ----------------
// 2D lens move (pan): the world point at frame centre travels; no parallax.
// FROM / TO = world coordinates of the film's first and second subject.
const FROM = [600, 540], TO = [1300, 540], ZOOM = 1.5;
IMPL.pan = (r) => { const L = $(r, ".lens"); return { frame(u) {
  const k = C.seg(u, 0.45, 2.25);                         // starts 0.45 s after the cut
  C.lens2d(L, { cx: C.lerp(FROM[0], TO[0], k), cy: C.lerp(FROM[1], TO[1], k), zoom: ZOOM });
} }; };
// 3D dolly: camera distance P -> P_end on a log curve (subject at z=0, props in front,
// background behind - see moves.md 03)
const P = 1880, P_END = 1100;
IMPL.dolly = (r) => { const Wd = $(r, ".world"); return { frame(u) {
  const k = C.seg(u, 0.4, 2.5);
  C.pose3d(Wd, { z: P - C.logLerp(P, P_END, k) });
} }; };
// story time (slow motion): words, scope and readout follow s; the camera stays still
IMPL.slowmo = (r, sc) => { const T = storyOf(sc), ws = C.collectWords(r), scope = scopeOf(r), ro = $(r, ".readout");
  return { frame(u) {
  const s = T.story(u);
  C.riseWords(ws, s); scope(s);
  ro.textContent = "×" + T.rate(u).toFixed(2).replace(".", ",");
} }; };
// hard cut between two layers (smash, match, J, L)
IMPL.cut = (r, sc) => { const A = $(r, ".A"), B = $(r, ".B"); return { frame(u) {
  show(A, u < sc.cut); show(B, u >= sc.cut);
} }; };

// ---------------- the loop ----------------
function labelFrame(lab, u, dur) {   // in 0.28 s from 0.10 s, out 0.16 s before the end
  const a = C.seg(u, 0.10, 0.38, C.easeOut), b = C.seg(u, dur - 0.22, dur - 0.06, C.easeIn);
  lab.style.opacity = (a * (1 - b)).toFixed(3);
  lab.style.transform = `translateY(${((1 - a) * 24 + b * 12).toFixed(1)}px)`;
}
for (const sc of SCENES) {
  sc.root = document.getElementById(sc.id);
  const make = IMPL[sc.impl || sc.id];
  sc.run = make ? make(sc.root, sc) : null;
  sc.label = sc.root.querySelector(".label");
}
const LAST = SCENES[SCENES.length - 1];
const DIP = document.getElementById("dip"), DIP_T = 0.1;          // 3 frames out, 3 in
const BOUNDS = SCENES.slice(1).map((sc) => sc.start);
function render(t) {
  if (DIP) {
    let d = 0;
    for (const b of BOUNDS) d = Math.max(d, 1 - Math.abs(t - b + 0.0001) / DIP_T);
    DIP.style.opacity = C.clamp01(d).toFixed(3);
  }
  for (const sc of SCENES) {
    if ((t >= sc.start - 1e-6 && t < sc.start + sc.dur) || (sc === LAST && t >= sc.start)) {
      const u = Math.min(sc.dur, t - sc.start);
      if (sc.run) sc.run.frame(u);
      if (sc.label) labelFrame(sc.label, u, sc.dur);
    }
  }
}
render(0);
const clockState = { t: 0 };
const tl = gsap.timeline({ paused: true });
tl.to(clockState, { t: END, duration: END, ease: "none", onUpdate: () => render(clockState.t) }, 0);
window.__timelines = window.__timelines || {};
window.__timelines["main"] = tl;
