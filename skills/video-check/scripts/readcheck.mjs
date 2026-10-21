#!/usr/bin/env node
// Reading-time check for a HyperFrames composition: every line meant to be read must stay
// fully on screen long enough. Steps through the film, asks the page which text blocks are
// fully visible at each time, and measures each block's first continuous run.
//
//   node readcheck.mjs <project_dir> [--norm words|strict] [--per-word 0.3] [--min 1.0]
//                      [--step 0.05] [--min-font 24] [--json]
//
// Norms (laws.md "Readable"):
//   words  (default)  need = max(--min, words x --per-word). Our house norm, 0.3 s per word,
//                     for text the voice also says, or one short line on a clean card.
//   strict            need = max(1.5, letters / 15 + 1.5). From lemo-opuscar's readcheck
//                     (MIT). About twice as long for a 6-word line (3.5 s vs 1.8 s). Use it
//                     for text the voice does NOT say, films that autoplay muted (LinkedIn
//                     feed), numbers/URLs/names a viewer must remember, and non-native viewers.
//
// Captions revealed word by word with the voice (words appear slower than ~8 per second)
// are read while they are spoken, so they get the subtitle rule instead (lemo-opuscar
// DIRECTOR §7): after the last word the line stays >= 0.6 s, and >= 1.8 s on screen in all.
//
// What counts as a text block: the nearest block-level element around the text (word spans
// of a caption join their line). "Fully visible" = every word in it has effective opacity
// >= 0.9 and lies inside the frame and inside any overflow-clipping ancestor. A rolling
// number (digits change, words do not) stays one block. Text whose rendered size is under
// --min-font px (at 1080p; UI chrome, labels) is skipped; force a block in with
// data-read, out with data-noread.
// Not seen: clip-path / mask reveals and text drawn into images or canvas.
//
// Exit: 0 all long enough; 1 some too short or never fully visible; 2 could not check.
import { createRequire } from 'node:module';
import { createServer } from 'node:http';
import { readFileSync, existsSync, readdirSync, statSync, createReadStream } from 'node:fs';
import { join, resolve, extname } from 'node:path';
import { homedir } from 'node:os';
import { execFileSync } from 'node:child_process';

const args = process.argv.slice(2);
const opt = (k, d) => { const i = args.indexOf(k); return i >= 0 ? args[i + 1] : d; };
const VALUED = ['--norm', '--per-word', '--min', '--step', '--min-font'];
const dir = resolve(args.find((a, i) => !a.startsWith('--') && !VALUED.includes(args[i - 1])) ?? '.');
const NORM = opt('--norm', 'words'), PER_WORD = +opt('--per-word', 0.3), MIN = +opt('--min', 1.0);
const STEP = +opt('--step', 0.05), MIN_FONT = +opt('--min-font', 24), JSON_OUT = args.includes('--json');
const die = (m, code = 2) => { console.error('readcheck: ' + m); process.exit(code); };
if (!['words', 'strict'].includes(NORM)) die('--norm is words or strict');
const indexHtml = join(dir, 'index.html');
if (!existsSync(indexHtml)) die(`no index.html in ${dir}`);

// The HyperFrames CLI that npx already cached: its runtime script and its puppeteer-core.
function findHyperframes() {
  if (process.env.HF_PKG) return process.env.HF_PKG;
  const root = join(homedir(), '.npm', '_npx');
  const ver = v => v.split('.').map(Number).reduce((a, n) => a * 1e4 + n, 0);
  let best = null;
  for (const d of existsSync(root) ? readdirSync(root) : []) {
    const pkg = join(root, d, 'node_modules', 'hyperframes');
    try {
      const v = JSON.parse(readFileSync(join(pkg, 'package.json'), 'utf8')).version;
      if (existsSync(join(pkg, 'dist', 'hyperframe-runtime.js')) && (!best || ver(v) > ver(best.v))) best = { pkg, v };
    } catch {}
  }
  return best?.pkg ?? die('no cached hyperframes CLI; run `npx --yes hyperframes --version` once, or set HF_PKG');
}
function findChrome() {
  if (process.env.HF_CHROME) return process.env.HF_CHROME;
  try { return execFileSync('npx', ['--yes', 'hyperframes', 'browser', 'path'], { encoding: 'utf8' }).trim().split('\n').pop(); }
  catch { die('could not find the HyperFrames Chrome; run `npx hyperframes browser ensure` or set HF_CHROME'); }
}
const hfPkg = findHyperframes();
const puppeteer = (await import(createRequire(join(hfPkg, 'package.json')).resolve('puppeteer-core'))).default;
const runtime = readFileSync(join(hfPkg, 'dist', 'hyperframe-runtime.js'));

// Serve the project the way the CLI does: the page with the runtime injected at <head> start.
const html = readFileSync(indexHtml, 'utf8');
const page0 = /<head[^>]*>/i.test(html) ? html.replace(/<head[^>]*>/i, m => m + '<script src="/__hf_runtime.js"></script>')
                                        : '<script src="/__hf_runtime.js"></script>' + html;
const W = +(html.match(/data-width="(\d+)"/)?.[1] ?? 1920), H = +(html.match(/data-height="(\d+)"/)?.[1] ?? 1080);
const MIME = { '.html': 'text/html', '.js': 'text/javascript', '.mjs': 'text/javascript', '.css': 'text/css', '.json': 'application/json',
  '.png': 'image/png', '.jpg': 'image/jpeg', '.jpeg': 'image/jpeg', '.svg': 'image/svg+xml', '.webp': 'image/webp', '.gif': 'image/gif',
  '.woff': 'font/woff', '.woff2': 'font/woff2', '.ttf': 'font/ttf', '.otf': 'font/otf', '.mp4': 'video/mp4', '.webm': 'video/webm',
  '.wav': 'audio/wav', '.mp3': 'audio/mpeg', '.ogg': 'audio/ogg' };
const server = createServer((req, res) => {
  const p = decodeURIComponent(new URL(req.url, 'http://x').pathname);
  if (p === '/' || p === '/index.html') { res.writeHead(200, { 'Content-Type': 'text/html' }); return res.end(page0); }
  if (p === '/__hf_runtime.js') { res.writeHead(200, { 'Content-Type': 'text/javascript' }); return res.end(runtime); }
  const f = join(dir, p);
  if (!f.startsWith(dir) || !existsSync(f) || !statSync(f).isFile()) { res.writeHead(404); return res.end(); }
  res.writeHead(200, { 'Content-Type': MIME[extname(f).toLowerCase()] ?? 'application/octet-stream' });
  createReadStream(f).pipe(res);
});
await new Promise(r => server.listen(0, '127.0.0.1', r));

const browser = await puppeteer.launch({ headless: true, executablePath: findChrome(), args: ['--hide-scrollbars', '--mute-audio'] });
let result;
try {
  const page = await browser.newPage();
  await page.setViewport({ width: W, height: H, deviceScaleFactor: 1 });
  const errors = [];
  page.on('pageerror', e => errors.push(String(e)));
  await page.goto(`http://127.0.0.1:${server.address().port}/`, { waitUntil: 'domcontentloaded', timeout: 60000 });
  await page.waitForFunction(() => window.__renderReady === true, { timeout: 30000 }).catch(() => {});
  await page.evaluate(() => document.fonts.ready);
  const dur = await page.evaluate(() => {
    const d = window.__player?.getDuration?.();
    return Number.isFinite(d) && d > 0 ? d : parseFloat(document.querySelector('[data-composition-id][data-duration]')?.dataset.duration ?? '0');
  });
  if (!(dur > 0)) die('composition duration unknown' + (errors.length ? ' - page errors: ' + errors.join(' | ') : ''));

  // Installed once in the page: seek + list the text blocks fully visible right now.
  await page.evaluate((MIN_FONT_PX) => {
    const ids = new WeakMap(); let next = 0;
    const INLINE = /^(inline|inline-block|contents)$/;
    const leafy = el => [...el.children].every(c => INLINE.test(getComputedStyle(c).display));
    const blockOf = el => {
      let b = el;
      for (;;) {
        const p = b.parentElement;
        if (!p || p.hasAttribute('data-composition-id')) return b;
        if (b.hasAttribute('data-read')) return b;
        const d = getComputedStyle(b).display, pd = getComputedStyle(p).display;
        // word spans: inline, or flex/grid items that are single short leaves
        if (INLINE.test(d) || (/flex|grid/.test(pd) && leafy(b) && b.textContent.trim().split(/\s+/).length <= 3
                               && [...p.children].every(leafy))) { b = p; continue; }
        return b;
      }
    };
    const effOpacity = el => { let o = 1; for (let e = el; e; e = e.parentElement) { const cs = getComputedStyle(e);
      if (cs.display === 'none' || cs.visibility === 'hidden') return 0; o *= +cs.opacity; } return o; };
    const inside = (el, r) => {
      if (r.width < 1 || r.height < 1) return false;
      if (r.left < -1 || r.top < -1 || r.right > innerWidth + 1 || r.bottom > innerHeight + 1) return false;
      for (let e = el.parentElement; e && e !== document.body; e = e.parentElement) {
        const cs = getComputedStyle(e);
        if (/(hidden|clip|scroll|auto)/.test(cs.overflowX + cs.overflowY)) {
          const c = e.getBoundingClientRect();
          if (r.left < c.left - 1 || r.top < c.top - 1 || r.right > c.right + 1 || r.bottom > c.bottom + 1) return false;
        }
      }
      return true;
    };
    window.__rc = (t) => {
      const p = window.__player;
      if (p?.renderSeek) p.renderSeek(t, { exact: true }); else if (p?.seek) p.seek(t);
      else for (const tl of Object.values(window.__timelines ?? {})) { tl.pause?.(); tl.seek?.(t); }
      window.gsap?.ticker?.tick?.();
      const root = document.querySelector('[data-composition-id]') ?? document.body;
      const blocks = new Map();
      const walk = document.createTreeWalker(root, NodeFilter.SHOW_TEXT);
      for (let n; (n = walk.nextNode());) {
        if (!n.nodeValue.trim()) continue;
        const el = n.parentElement;
        if (!el || el.closest('script,style,[data-noread]')) continue;
        const b = blockOf(el);
        let s = blocks.get(b);
        if (!s) blocks.set(b, s = { ok: true, seen: false, font: 0, n: 0, nOk: 0, parts: [] });
        const cs = getComputedStyle(el), r = el.getBoundingClientRect();
        const scale = el.offsetHeight > 0 ? r.height / el.offsetHeight : 1;
        s.font = Math.max(s.font, parseFloat(cs.fontSize) * scale);
        const op = effOpacity(el);
        if (op > 0.02 && r.width > 0) s.seen = true;
        s.n++; s.parts.push(n.nodeValue);
        if (op >= 0.9 && inside(el, r)) s.nOk++; else s.ok = false;
      }
      const out = [];
      for (const [b, s] of blocks) {
        if (!s.seen) continue;
        if (!ids.has(b)) ids.set(b, next++);
        const text = s.parts.join(' ').replace(/\s+/g, ' ').trim();   // only the text that belongs to this block
        out.push({ id: ids.get(b), text, ok: s.ok, part: s.nOk > 0 && !s.ok, font: s.font, forced: b.hasAttribute('data-read') });
      }
      return out;
    };
  }, MIN_FONT * H / 1080);

  const pieces = new Map(), skipped = new Map();
  for (let t = 0; t <= dur + 1e-9; t += STEP) {
    const vis = await page.evaluate(t => window.__rc(t), t);
    const now = new Set();
    for (const b of vis) {
      if (!b.forced && b.font < MIN_FONT * H / 1080) { skipped.set(b.text.slice(0, 40), Math.round(b.font)); continue; }
      const key = b.id + '\u0000' + b.text.replace(/\d+([.,]\d+)?/g, '#');    // a rolling number stays one piece
      let p = pieces.get(key);
      if (!p) pieces.set(key, p = { text: b.text, t0: null, tPart: null, run: 0, done: false, firstSeen: t, font: Math.round(b.font) });
      if (b.part && p.t0 === null && p.tPart === null) p.tPart = t;
      if (b.ok && !p.done) { if (p.t0 === null) p.t0 = t; p.run = t - p.t0 + STEP; now.add(key); p.text = b.text; }
    }
    for (const [k, p] of pieces) if (p.t0 !== null && !now.has(k)) p.done = true;
  }
  const need = text => {
    if (NORM === 'strict') return Math.max(1.5, text.replace(/\s/g, '').length / 15 + 1.5);
    return Math.max(MIN, text.split(/\s+/).filter(Boolean).length * PER_WORD);
  };
  const words = text => text.split(/\s+/).filter(Boolean).length;
  result = [...pieces.values()].map(p => {
    const got = Math.min(p.run, dur - (p.t0 ?? 0)), toEnd = p.t0 !== null && p.t0 + p.run >= dur - STEP;
    const reveal = p.t0 !== null && p.tPart !== null ? p.t0 - p.tPart : 0;
    const caption = reveal >= Math.max(0.5, words(p.text) * 0.12);    // revealed with the voice
    let verdict, n;
    if (p.t0 === null) { verdict = 'NEVER'; n = need(p.text); }
    else if (caption) { n = 0.6; verdict = got + 1e-6 >= 0.6 && reveal + got + 1e-6 >= 1.8 ? 'OK' : 'SHORT'; }
    else { n = need(p.text); verdict = got + 1e-6 >= n ? 'OK' : 'SHORT'; }
    return { verdict, kind: caption ? 'caption' : 'line', at: +(p.t0 ?? p.firstSeen).toFixed(2), revealFrom: caption ? +p.tPart.toFixed(2) : null,
             need: +n.toFixed(2), got: +got.toFixed(2), toEnd, font: p.font, text: p.text };
  }).sort((a, b) => a.at - b.at);
  if (!result.length) die('no readable text found (lower --min-font, or mark blocks with data-read)');
  if (errors.length) console.error('page errors: ' + errors.join(' | '));
  if (JSON_OUT) console.log(JSON.stringify({ norm: NORM, perWord: PER_WORD, duration: dur, skippedSmall: skipped.size, blocks: result }, null, 1));
  else {
    console.log(`readcheck ${dir}  ${dur}s  norm=${NORM}${NORM === 'words' ? ` (${PER_WORD} s/word, min ${MIN} s)` : ''}  step ${STEP}s`);
    for (const r of result)
      console.log(`${r.verdict.padEnd(5)} ${r.at.toFixed(2).padStart(6)}s  ${r.kind === 'caption' ? 'tail' : 'need'} ${r.need.toFixed(2)}s  got ${r.verdict === 'NEVER' ? '  -  ' : r.got.toFixed(2) + 's'}${r.toEnd ? ' (to film end)' : ''}`
        + `  ${String(r.font).padStart(3)}px  ${r.kind === 'caption' ? `[caption from ${r.revealFrom.toFixed(2)}s] ` : ''}${JSON.stringify(r.text.slice(0, 70))}`);
    console.log(`${result.filter(r => r.verdict !== 'OK').length} of ${result.length} blocks fail; ${skipped.size} small text blocks skipped (< ${MIN_FONT}px)`);
    // Small text is not timed, but a number or claim in it is still unreadable on a phone (a launch film: the 2.6 s / 6.8 s pills at 19 px).
    if (skipped.size) console.log('small (check at phone width - a number or claim here must be enlarged): '
      + [...skipped].slice(0, 12).map(([t, f]) => `${JSON.stringify(t)} ${f}px`).join(', ') + (skipped.size > 12 ? ', ...' : ''));
  }
} finally {
  await browser.close(); server.close();
}
process.exit(result.some(r => r.verdict !== 'OK') ? 1 : 0);
