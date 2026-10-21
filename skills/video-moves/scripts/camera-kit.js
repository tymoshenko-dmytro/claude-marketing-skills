// camera-kit.js - camera and editing grammar for HyperFrames films (DOM + CSS 3D).
//
// The math follows the "24 camera and editing moves" guide (see THIRD_PARTY_NOTICES.md).
// The math (curves, log zoom, seeded noise, story time, whip, wipe, J/L cuts) is ported
// from the guide's camera-kit.js. The guide drives Three.js; the rigs here drive DOM
// layers instead:
//   - a 2D lens   : one wrapper, transform-origin 0 0 - pan, tilt, zoom, roll, shake, whip
//   - a 3D world  : a static-perspective stage + a preserve-3d world - dolly, orbit,
//                   crane, tracking, FPV, dolly zoom (perspective is the focal length)
//
// Every frame is a pure function of time. A single linear driver tween on the paused
// GSAP timeline calls render(t); nothing reads the clock, Math.random or the layout.
(function (root) {
  "use strict";

  // ---------- math ----------
  const TAU = Math.PI * 2;
  const clamp01 = (x) => Math.max(0, Math.min(1, x));
  const lerp = (a, b, k) => a + (b - a) * k;
  const ease = (x) => (x < 0.5 ? 4 * x * x * x : 1 - Math.pow(-2 * x + 2, 3) / 2); // in-out cubic: camera moves
  const easeOut = (x) => 1 - Math.pow(1 - clamp01(x), 3);                          // hits: crash zoom, whip landing
  const easeIn = (x) => Math.pow(clamp01(x), 3);
  const linear = (x) => clamp01(x);
  const smooth = (a, b, x) => { const k = clamp01((x - a) / (b - a)); return k * k * (3 - 2 * k); };
  const seg = (t, a, b, fn = ease) => fn(clamp01((t - a) / (b - a)));              // 0..1 progress on [a, b]
  // Zoom, crane and long dollies interpolate the LOG of the size: a linear scale tween
  // reads as braking towards the end, because perceived speed is d(log s)/dt.
  const logLerp = (a, b, k) => Math.exp(lerp(Math.log(a), Math.log(b), k));
  const rad = (d) => (d * Math.PI) / 180;
  const deg = (r) => (r * 180) / Math.PI;
  // focal length (mm, 35 mm-ish) -> vertical field of view; 24 mm gives 32 degrees
  const fovOf = (mm, k = 6.9) => deg(2 * Math.atan(k / mm));
  // CSS perspective (px) that gives that field of view on a frame of height H
  const perspOf = (mm, H = 1080) => H / 2 / Math.tan(rad(fovOf(mm)) / 2);
  // screen pixels per degree of camera rotation (small angles)
  const pxPerDeg = (vfov = 32, H = 1080) => H / vfov;
  // scale that keeps a rolled frame covering the screen (no empty corners)
  const rollCover = (d, W = 1920, H = 1080) => {
    const a = Math.abs(rad(d));
    return Math.max(Math.cos(a) + (W / H) * Math.sin(a), Math.cos(a) + (H / W) * Math.sin(a));
  };
  function rng(seed) { // mulberry32: the only randomness allowed in a frame
    let a = seed >>> 0;
    return () => {
      a = (a + 0x6d2b79f5) >>> 0; let t = a;
      t = Math.imul(t ^ (t >>> 15), t | 1); t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
      return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
    };
  }
  // Sum of sines. Frequencies that are integer multiples of 1/loop make a seamless loop.
  const sines = (t, loop, list) => list.reduce((s, [a, m, p]) => s + a * Math.sin((TAU / loop) * m * t + p), 0);

  // ---------- handheld (degrees) ----------
  // The guide's amplitudes: about half a degree of yaw/pitch/roll, low frequencies only.
  // A fresh random offset per frame reads as digital jitter, not as hands.
  function handheld(t, { loop = 4.7, amp = 1 } = {}) {
    return {
      yaw: sines(t, loop, [[0.55, 3, 1.4], [0.25, 8, 0.1]]) * amp,
      pitch: sines(t, loop, [[0.45, 4, 0.7], [0.2, 9, 2.2]]) * amp,
      roll: sines(t, loop, [[0.6, 2, 0.3], [0.25, 7, 1.9]]) * amp,
    };
  }
  // A hit (smash cut): seeded noise held for 1/fps-step frames, decaying.
  function shake(t, { seed = 7, step = 1 / 12, amp = 8, decay = 1.0 } = {}) {
    const r = rng(seed + Math.floor(t / step) * 31);
    const k = Math.max(0, 1 - t / decay);
    return { dx: (r() * 2 - 1) * amp * k, dy: (r() * 2 - 1) * amp * k, roll: (r() * 2 - 1) * 0.6 * k };
  }

  // ---------- story time: slow motion, speed ramp, freeze frame ----------
  // segments in order: { until, rate } holds a rate, { until, to } eases to a new rate,
  // the last one has no until. Everything in the world (words, voice, particles) lives
  // in story time s = story(u); the camera and the cut live in real time u.
  function piecewiseRate(segments) {
    return (u) => {
      let prevEnd = 0, prevRate = segments[0].rate ?? 1;
      for (const s of segments) {
        const end = s.until ?? Infinity;
        if (u < end) return s.to != null ? lerp(prevRate, s.to, smooth(prevEnd, end, u)) : s.rate;
        prevRate = s.to ?? s.rate; prevEnd = end;
      }
      return prevRate;
    };
  }
  function makeStoryTime(rate, { until = 30, dt = 0.002, s0 = 0 } = {}) {
    const n = Math.ceil(until / dt), acc = new Float64Array(n + 1);
    for (let i = 1; i <= n; i++) acc[i] = acc[i - 1] + rate((i - 0.5) * dt) * dt;
    const story = (u) => {
      const f = Math.max(0, Math.min(n, u / dt)), i = Math.floor(f);
      return s0 + acc[i] + (acc[Math.min(n, i + 1)] - acc[i]) * (f - i);
    };
    const real = (s) => { // real time at which the story reaches s
      let lo = 0, hi = n; const x = s - s0;
      while (lo < hi) { const m = (lo + hi) >> 1; if (acc[m] < x) lo = m + 1; else hi = m; }
      return lo * dt;
    };
    return { story, real, rate };
  }

  // ---------- transitions ----------
  const jumpIndex = (t, count, step) => Math.max(0, Math.min(count - 1, Math.floor(t / step)));
  // Whip pan: out with acceleration, swap sides at the midpoint, in with deceleration.
  // Blur follows angular speed; ~8% of the frame width at the peak.
  function whip(u, { start = 0.2, dur = 0.6, angle = 40, blur = 150 } = {}) {
    const half = dur / 2;
    if (u < start) return { side: "from", yaw: 0, hblur: 0 };
    if (u < start + half) { const k = Math.pow((u - start) / half, 2); return { side: "from", yaw: -angle * k, hblur: blur * k }; }
    if (u < start + dur) { const k = 1 - Math.pow(1 - (u - start - half) / half, 2); return { side: "to", yaw: angle * (1 - k), hblur: blur * (1 - k) }; }
    return { side: "to", yaw: 0, hblur: 0 };
  }
  const dissolve = (u, { start = 1.0, dur = 1.2 } = {}) => seg(u, start, start + dur);
  const wipeX = (u, width, { start = 1.0, dur = 1.1 } = {}) => seg(u, start, start + dur) * width;
  const jCut = (cut, lead = 0.45) => ({ audioStart: cut - lead }); // sound of B before the picture
  const lCut = (cut, tail = 0.4) => ({ audioEnd: cut + tail });     // sound of A after the picture

  // ---------- DOM rigs ----------
  // 2D lens. The wrapper holds a world laid out in px; (cx, cy) is the world point at
  // the centre of the frame. Needs transform-origin: 0 0 on the element.
  function lens2d(el, { cx = 960, cy = 540, zoom = 1, roll = 0, dx = 0, dy = 0, W = 1920, H = 1080 } = {}) {
    el.style.transform =
      `translate(${(W / 2 + dx).toFixed(2)}px,${(H / 2 + dy).toFixed(2)}px) rotate(${roll.toFixed(3)}deg) ` +
      `scale(${zoom.toFixed(5)}) translate(${(-cx).toFixed(2)}px,${(-cy).toFixed(2)}px)`;
  }
  // 3D world pose. Translate is composed OUTSIDE the rotations, so x/y/z stay screen
  // axes at any tilt (upstream 3d-camera-flight rule). Camera in = world z up.
  function pose3d(el, { x = 0, y = 0, z = 0, rx = 0, ry = 0, rz = 0 } = {}) {
    el.style.transform =
      `translate3d(${x.toFixed(2)}px,${y.toFixed(2)}px,${z.toFixed(2)}px) ` +
      `rotateX(${rx.toFixed(3)}deg) rotateY(${ry.toFixed(3)}deg) rotateZ(${rz.toFixed(3)}deg)`;
  }
  // Word-by-word reveal in story time; each timed .w carries data-t (seconds).
  // Words that are simply on screen carry class "on" and no data-t.
  function collectWords(scope) {
    return Array.from(scope.querySelectorAll(".w[data-t]")).map((e) => ({ e, t: parseFloat(e.dataset.t) }));
  }
  function revealWords(list, s, fade = 0.14) {
    for (const w of list) w.e.style.opacity = clamp01((s - w.t) / fade).toFixed(3);
  }

  // Story-time reveal with a rise: a word floats up into place over `rise` story seconds.
  // At x0.25 it visibly floats; in a freeze it hangs mid-rise. Needs .w as inline-block.
  function riseWords(list, s, rise = 0.32, dist = 26) {
    for (const w of list) {
      const k = clamp01((s - w.t) / rise), e = 1 - Math.pow(1 - k, 3);
      w.e.style.opacity = clamp01((s - w.t) / (rise * 0.6)).toFixed(3);
      w.e.style.transform = `translateY(${((1 - e) * dist).toFixed(2)}px)`;
    }
  }

  root.CK = {
    TAU, clamp01, lerp, ease, easeOut, easeIn, linear, smooth, seg, logLerp, rad, deg,
    fovOf, perspOf, pxPerDeg, rollCover, rng, sines, handheld, shake,
    piecewiseRate, makeStoryTime, jumpIndex, whip, dissolve, wipeX, jCut, lCut,
    lens2d, pose3d, collectWords, revealWords, riseWords,
  };
})(window);
