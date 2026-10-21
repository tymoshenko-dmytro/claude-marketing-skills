#!/usr/bin/env node
// captions.mjs - word-timed caption cues for a HyperFrames film, any language and direction.
// Ported from nanoclip-cutting-room scripts/captions.mjs (MIT) and fitted to our laws: cues
// break at a speaker change, >= 0.8 s of dead air, a seam (a new voice line or footage window)
// and a word cap; cues closer than 0.5 s are chained two frames apart; inside a run the split points are chosen so every cue passes video-check
// readcheck.mjs, which a fixed 4-word cut does not do at TTS speed (en1 below: 8 words in 1.8 s).
//
//   node captions.mjs <film.json> [--out <prefix>] [--max-words 4] [--band 0.70] [--ahead 0.55]
//                     [--size 56] [--no-highlight] [--fps 30] [--id captions] [--track 20]
//                     [--font "Family=assets/fonts/file.woff2"]...
//
// film.json (paths relative to it):
//   { "duration": 18.6,                       // film end - no cue outlives it (optional)
//     "lines": [
//       { "tag": "en1", "at": 0.50, "words": "audio/lines/en1.words.json", "speaker": "eric" },
//       { "tag": "ar1", "at": 2.80, "words": "audio/lines/ar1.words.json" },
//       { "tag": "talk", "at": 9.0, "whisper": "audio/talk.json", "in": 3.2, "out": 11.0 } ] }
//   words      gen_voice --words / --align output: {"words": [{"w","s","e"}]} on the take's clock,
//              or an inline array. `at` is where the take starts on the film clock.
//   whisper    mlx_whisper --word-timestamps True json (recorded speech); `in`/`out` pick a source
//              window, which lands at `at`.
//   speaker    defaults to the line's `voice`, then its tag. `dir` ("rtl"/"ltr") and `lang` override
//              detection (direction = the script most of the line's letters are in).
//
// Writes <prefix>.cues.json (the timing truth) and <prefix>.html - one block to paste inside the
// composition root: <style>, the caption layer (one .cap-cue per cue, dir per cue, one inline
// .cap-word span per word), and a <script> defining mountCaptions(tl). Call mountCaptions(tl)
// in the timeline script before registering tl. Colours, font, size and band height are CSS
// variables on #<id> (--cap-ink, --cap-scrim, --cap-hi, --cap-hi-ink, --cap-font, --cap-size,
// --cap-y): take them from the film being edited; override them AFTER the snippet or as
// `#root #<id> {...}` - an earlier rule of the same weight loses.
//
// Exit: 0 every cue holds long enough to read; 1 some cue cannot (listed); 2 bad input.
import { readFileSync, writeFileSync, existsSync } from 'node:fs';
import { dirname, resolve, basename } from 'node:path';
import { pathToFileURL } from 'node:url';

export const CUE_MAX_WORDS = 4;     // soft cap per cue (shorts convention); exceeded only to stay readable
export const CUE_HARD_WORDS = 10;   // never more than this in one cue (two rows at most)
export const CUE_GAP_S = 0.8;       // dead air that always starts a fresh cue
export const CUE_HOLD_S = 0.5;      // a cue lingers at least this long after its last word ends
export const CHAIN_S = 0.5;         // a cue that would end closer than this to the next one is chained to it:
                                    // exactly CHAIN_GAP_FRAMES of empty band between them (subtitle practice:
                                    // the blink tells the eye the text changed), and the next one pops in
export const CHAIN_GAP_FRAMES = 2;
export const CUE_MIN_WORD_S = 0.08; // a highlight never shorter than this
export const HI_BRIDGE_S = 0.25;    // a highlight runs on to the next word across a gap shorter than this
export const CUE_FADE_S = 0.12;     // cue fade-in
export const WORD_FADE_S = 0.08;    // a word going solid as it is said
// readcheck.mjs (video-check) and laws.md "Readable", replicated so the builder can choose for them
export const READ = { tail: 0.6, total: 1.8, perWord: 0.3, min: 1.0, step: 0.05 };

// Hebrew, Arabic, Syriac, Thaana, NKo, Samaritan, Mandaic, Arabic extended + presentation forms
const RTL_RE = /[֐-ࣿיִ-﷿ﹰ-﻿]/;
const SENTENCE_END = /[.!?…؟۔]["'»”)\]]*$/;
const CLAUSE_END = /[,;:،؛—–]["'»”)\]]*$/;
const r3 = (x) => Math.round(x * 1000) / 1000;

// Direction of a line: the script most of its letters are in. An Arabic line with a Latin brand
// is rtl; an English line with one Arabic name stays ltr (nanoclip's "any RTL run" would flip it).
export function lineDir(text) {
  let rtl = 0, ltr = 0;
  for (const ch of text) if (/\p{L}/u.test(ch)) RTL_RE.test(ch) ? rtl++ : ltr++;
  return rtl > ltr ? 'rtl' : 'ltr';
}

// Normalise one line of input to film-clock words: [{text, start, end}]
export function lineWords(line, baseDir = '.') {
  const at = +line.at || 0;
  if (line.whisper) {
    const d = typeof line.whisper === 'string' ? JSON.parse(readFileSync(resolve(baseDir, line.whisper), 'utf8')) : line.whisper;
    const lo = line.in ?? -Infinity, hi = line.out ?? Infinity, off = Number.isFinite(lo) ? lo : 0;
    return (d.segments ?? []).flatMap((s) => s.words ?? [])
      .filter((w) => w.start >= lo && w.start < hi && w.word.trim())
      .map((w) => ({ text: w.word.trim(), start: r3(at + w.start - off), end: r3(at + Math.min(w.end, hi) - off) }));
  }
  const src = typeof line.words === 'string' ? JSON.parse(readFileSync(resolve(baseDir, line.words), 'utf8')) : line.words;
  const arr = Array.isArray(src) ? src : src?.words;
  if (!Array.isArray(arr)) throw new Error(`line ${line.tag ?? '?'}: no words`);
  return arr.map((w) => ({ text: String(w.w ?? w.text ?? w.word).trim(), start: r3(at + +(w.s ?? w.start)), end: r3(at + +(w.e ?? w.end)) }))
    .filter((w) => w.text);
}

// What readcheck will measure for a cue of words ws on screen from ws[0].start until `end`.
// Words ahead are ghosted (ahead < 0.9) so readcheck sees the cue revealed with the voice and
// applies the subtitle rule; a cue solid from its first frame is a static line (0.3 s per word).
// readcheck counts what whitespace separates in the cue's text nodes, and the snippet puts a word's
// punctuation in its own span, so "awake." counts as two
const rcWords = (ws) => ws.reduce((n, w) => { const m = w.text.match(/^(\p{P}*)(.*?)(\p{P}*)$/u);
  return n + 1 + (m[2] && m[1] ? 1 : 0) + (m[2] && m[3] ? 1 : 0); }, 0);

export function readNeed(ws, end, ahead = 0.55) {
  const start = ws[0].start, last = ws.at(-1), n = rcWords(ws);
  const solid = ahead >= 0.9 ? start + CUE_FADE_S : Math.max(start + CUE_FADE_S, last.start + WORD_FADE_S);
  const reveal = solid - start, got = end - solid;
  const caption = ahead < 0.9 && reveal >= Math.max(0.5, n * 0.12);
  const need = caption ? Math.max(READ.tail, READ.total - reveal) : Math.max(READ.min, n * READ.perWord);
  return { caption, solid, need: r3(need), got: r3(got), ok: got + 1e-6 >= need + READ.step };
}

// End of a cue: hold after the last word and long enough to read, but give way to the next cue
// (chained, two frames apart) and the film end - and never before the last word itself is over.
function cueEnd(ws, nextStart, filmEnd, ahead, fps = 30) {
  const lastEnd = Math.max(ws.at(-1).end, ws.at(-1).start + CUE_MIN_WORD_S);
  const r = readNeed(ws, 0, ahead);
  const want = Math.max(lastEnd + CUE_HOLD_S, r.solid + r.need + READ.step + 0.02);
  let end = nextStart - want < CHAIN_S ? nextStart - CHAIN_GAP_FRAMES / fps : want;
  end = Math.max(end, Math.min(lastEnd, nextStart));   // not before the last word is over, never into the next cue
  return r3(Math.min(end, filmEnd));
}

// Split one run (no hard break inside) into cues: dynamic programming over split points.
// Cost: a cue readcheck would fail (dominant), words over the soft cap, a split that is not at
// punctuation, one-word cues. So a fast line becomes fewer, longer cues; a slow one, 3-4 words.
function splitRun(ws, nextRunStart, filmEnd, opt) {
  const n = ws.length, best = Array(n + 1).fill(Infinity), from = Array(n + 1).fill(-1);
  best[0] = 0;
  for (let j = 1; j <= n; j++) {
    for (let i = Math.max(0, j - opt.hardWords); i < j; i++) {
      if (best[i] === Infinity) continue;
      const cue = ws.slice(i, j);
      const next = j < n ? ws[j].start : nextRunStart;
      const end = cueEnd(cue, next, filmEnd, opt.ahead, opt.fps);
      const r = readNeed(cue, end, opt.ahead);
      let c = 1;
      if (!r.ok) c += 100 + 100 * (r.need - r.got);
      c += 3 * Math.max(0, cue.length - opt.maxWords);
      if (cue.length === 1 && n > 1) c += 2;
      if (j < n) c += SENTENCE_END.test(cue.at(-1).text) ? -0.5 : CLAUSE_END.test(cue.at(-1).text) ? 0 : 1;
      if (best[i] + c < best[j]) { best[j] = best[i] + c; from[j] = i; }
    }
  }
  const cuts = [];
  for (let j = n; j > 0; j = from[j]) cuts.unshift([from[j], j]);
  return cuts.map(([i, j]) => ws.slice(i, j));
}

export function buildCues(film, baseDir = '.', o = {}) {
  const opt = { maxWords: CUE_MAX_WORDS, hardWords: CUE_HARD_WORDS, ahead: 0.55, highlight: true, fps: 30, ...o };
  const filmEnd = film.duration ?? Infinity;
  // runs: hard breaks at a seam (each line), a speaker change (lines differ) and dead air
  const runs = [];
  [...film.lines].sort((a, b) => (+a.at || 0) - (+b.at || 0)).forEach((line, li) => {
    const ws = lineWords(line, baseDir);
    if (!ws.length) return;
    const text = ws.map((w) => w.text).join(' ');
    const meta = { line: line.tag ?? `l${li}`, speaker: line.speaker ?? line.voice ?? line.tag ?? `l${li}`,
                   dir: line.dir ?? lineDir(text), lang: line.lang };
    let run = null;
    for (const w of ws) {
      if (!run || w.start - run.words.at(-1).end >= CUE_GAP_S - 1e-9) runs.push(run = { ...meta, words: [] });
      run.words.push(w);
    }
  });
  const cues = [], warnings = [];
  runs.forEach((run, ri) => {
    const nextRun = runs[ri + 1]?.words[0].start ?? Infinity;
    for (const ws of splitRun(run.words, nextRun, filmEnd, opt)) {
      const k = cues.length;
      cues.push({ id: `cap-${k}`, line: run.line, speaker: run.speaker, dir: run.dir, ...(run.lang ? { lang: run.lang } : {}),
                  start: ws[0].start, end: 0, words: ws.map((w) => ({ ...w })) });
    }
  });
  cues.forEach((c, k) => {
    const next = cues[k + 1]?.start ?? Infinity;
    if (c.start < (cues[k - 1]?.end ?? -Infinity)) warnings.push(`${c.id}: starts before ${cues[k - 1].id} ends`);
    c.end = cueEnd(c.words, next, filmEnd, opt.ahead, opt.fps);
    c.fade = k && c.start - cues[k - 1].end < CHAIN_S ? 0 : CUE_FADE_S;   // a chained cue pops in
    c.words.forEach((w, i) => {
      const nw = c.words[i + 1];
      const floor = Math.max(w.end, w.start + CUE_MIN_WORD_S);
      w.hiStart = w.start;
      w.hiEnd = r3(Math.min(nw && nw.start - w.end < HI_BRIDGE_S ? Math.max(nw.start, w.start + CUE_MIN_WORD_S) : floor, c.end));
    });
    const r = readNeed(c.words, c.end, opt.ahead);
    c.read = { rule: r.caption ? 'caption' : 'line', need: r.need, got: r.got, ok: r.ok };
    if (!r.ok) warnings.push(`${c.id} "${c.words.map((w) => w.text).join(' ')}" readable ${r.got}s, needs ${r.need}s `
      + `(${r.caption ? 'after its last word' : 'on screen'}) - the next voice starts too soon; widen the gap or cut words`);
  });
  return { cues, warnings, opt };
}

const esc = (s) => s.replace(/[&<>"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' })[c]);

export function snippet({ cues, opt }, o = {}) {
  const id = o.id ?? 'captions', fps = o.fps ?? 30, band = o.band ?? 0.70, end = o.duration ?? Math.max(...cues.map((c) => c.end));
  const fonts = (o.fonts ?? []).map(([fam, url]) =>
    `@font-face { font-family: "${fam}"; src: url("${url}"); font-display: block; }`).join('\n  ');
  const stack = [...(o.fonts ?? []).map(([fam]) => `"${fam}"`), 'sans-serif'].join(', ');
  const css = `<style>
  ${fonts}
  #${id} { position: absolute; inset: 0; pointer-events: none;
    --cap-y: ${(band * 100).toFixed(1)}%; --cap-size: ${o.size ?? 56}px; --cap-font: ${stack};
    --cap-ink: #ffffff; --cap-scrim: rgba(12, 14, 18, 0.66); --cap-hi: #ffd84d; --cap-hi-ink: #111111;
    --cap-pill: 0.02em 0.1em 0.06em; --cap-pill-rtl: 0 0.1em 0.24em; }
  /* the band: its centre sits at --cap-y (laws: ~70% height, never over a face); cues share one cell.
     data-read on each cue: readcheck would otherwise fold a grid item of <= 3 words into the band */
  #${id} .cap-band { position: absolute; left: 5%; right: 5%; top: calc(var(--cap-y) - 20%); height: 40%;
    display: grid; place-items: center; }
  #${id} .cap-cue { grid-area: 1 / 1; opacity: 0; max-width: 100%; width: fit-content; text-align: center;
    font-family: var(--cap-font); font-size: var(--cap-size); font-weight: 600; line-height: 1.4;
    color: var(--cap-ink); background: var(--cap-scrim); padding: 0.14em 0.42em; border-radius: 0.28em;
    text-wrap: balance; letter-spacing: 0; text-transform: none; }
  /* Arabic needs more line height; letter-spacing would break the joins */
  #${id} .cap-cue[dir="rtl"] { line-height: 1.6; }
  /* words stay INLINE: inline spans share the cue's bidi paragraph, so a Latin name in an Arabic
     line sits where it belongs; inline-block spans each become a neutral box and runs of them
     reverse ("Google Maps" -> "Maps Google") */
  #${id} .cap-word { display: inline; opacity: ${opt.ahead}; }
  /* the highlight sits on the word without its punctuation: in an RTL line a final "." belongs at the
     far left, so a pill over "Maps." split into a stray second pill there */
  /* the pill is as tall as the FIRST face in --cap-font (Inter: 0.97em up, 0.24em down); dots under
     Arabic letters reach ~0.42em down and fell outside it, dark on dark - so RTL pills pad the bottom.
     An Arabic face first is no fix: Noto Sans Arabic's metrics made every pill 2.15em tall. New
     fonts: check a still - dots inside the pill, pill inside the scrim */
  #${id} .cap-core { padding: var(--cap-pill); border-radius: 0.2em; }
  #${id} .cap-cue[dir="rtl"] .cap-core { padding: var(--cap-pill-rtl); }
  /* no pill padding on the side where the word's own punctuation sits ("nine ," otherwise) */
  #${id} .cap-cue .cap-core.l { padding-inline-start: 0; }
  #${id} .cap-cue .cap-core.t { padding-inline-end: 0; }
  #${id} .cap-word[data-on="1"] .cap-core { background: var(--cap-hi); color: var(--cap-hi-ink); }
</style>`;
  const layer = `<div id="${id}" class="clip" data-start="0" data-duration="${r3(end)}" data-track-index="${o.track ?? 20}">
  <div class="cap-band">
${cues.map((c) => `    <div class="cap-cue" id="${id}-${c.id}" dir="${c.dir}"${c.lang ? ` lang="${c.lang}"` : ''} data-read data-layout-allow-overlap="true">`
    + c.words.map((w, i) => { const [, a, core, z] = w.text.match(/^(\p{P}*)(.*?)(\p{P}*)$/u);
        // own box: contrast is measured per box; the pill's edge touches it, which check calls occlusion
        const pn = (t) => (t ? `<span class="cap-p" data-layout-allow-occlusion="true">${esc(t)}</span>` : '');
        const cls = ['cap-core', core && a ? 'l' : '', core && z ? 't' : ''].filter(Boolean).join(' ');
        return `<span class="cap-word" data-i="${i}" data-on="0">${pn(a)}<span class="${cls}">${esc(core || w.text)}</span>${core ? pn(z) : ''}</span>`; })
      .join(' ') + '</div>').join('\n')}
  </div>
</div>`;
  const data = { id, fps, ahead: opt.ahead, highlight: opt.highlight, wordFade: WORD_FADE_S,
    cues: cues.map((c) => ({ id: `${id}-${c.id}`, s: c.start, e: c.end, f: c.fade, w: c.words.map((w) => [w.start, w.hiStart, w.hiEnd]) })) };
  const js = `<script>
  // captions.mjs: every change lands on the frame nearest its time (frame k shows from k/fps)
  window.mountCaptions = function (tl) {
    var C = ${JSON.stringify(data)};
    var q = function (t) { return Math.max(0.001, (Math.round(t * C.fps) - 0.5) / C.fps); };
    C.cues.forEach(function (c) {
      var el = document.getElementById(c.id), ws = el.querySelectorAll(".cap-word");
      // a cue after silence fades in during the c.f before its first word; a chained cue pops in
      if (c.f) tl.fromTo(el, { opacity: 0 }, { opacity: 1, duration: c.f, ease: "none", immediateRender: false }, q(c.s - c.f));
      else tl.set(el, { opacity: 1 }, q(c.s));
      tl.set(el, { opacity: 0 }, q(c.e));
      c.w.forEach(function (w, i) {
        // with the pill the word goes solid on its frame (a fade would dim the pill's first frame)
        if (C.ahead < 1 && C.highlight) tl.set(ws[i], { opacity: 1 }, q(w[0]));
        else if (C.ahead < 1) tl.fromTo(ws[i], { opacity: C.ahead }, { opacity: 1, duration: C.wordFade, ease: "none", immediateRender: false }, q(w[0]));
        if (C.highlight) { tl.set(ws[i], { attr: { "data-on": "1" } }, q(w[1])); tl.set(ws[i], { attr: { "data-on": "0" } }, q(w[2])); }
      });
    });
  };
</script>`;
  return `<!-- captions.mjs: paste inside the composition root; call mountCaptions(tl) before registering tl -->\n${css}\n${layer}\n${js}\n`;
}

if (process.argv[1] && import.meta.url === pathToFileURL(resolve(process.argv[1])).href) {
  const args = process.argv.slice(2);
  const flag = (k, d) => { const i = args.indexOf(`--${k}`); return i >= 0 ? args[i + 1] : d; };
  const VALUED = ['--out', '--max-words', '--band', '--ahead', '--fps', '--id', '--track', '--font', '--size'];
  const filmPath = args.find((a, i) => !a.startsWith('--') && !VALUED.includes(args[i - 1]));
  if (!filmPath || !existsSync(filmPath)) {
    console.error('usage: captions.mjs <film.json> [--out prefix] [--max-words 4] [--band 0.70] [--ahead 0.55] [--no-highlight] [--fps 30] [--font "Family=path"]');
    process.exit(2);
  }
  const film = JSON.parse(readFileSync(filmPath, 'utf8')), base = dirname(resolve(filmPath));
  const out = resolve(flag('out', resolve(base, 'captions')));
  const fonts = args.flatMap((a, i) => (a === '--font' ? [args[i + 1]] : [])).map((f) => {
    const [fam, p] = f.split('='); return [fam, p];   // written as given: relative to the composition
  });
  let built;
  try {
    built = buildCues(film, base, { maxWords: +flag('max-words', CUE_MAX_WORDS), ahead: +flag('ahead', 0.55),
                                    highlight: !args.includes('--no-highlight'), fps: +flag('fps', 30) });
  } catch (e) { console.error('captions: ' + e.message); process.exit(2); }
  const { cues, warnings, opt } = built;
  writeFileSync(out + '.cues.json', JSON.stringify({ band: +flag('band', 0.70), ...opt, cues, warnings }, null, 1) + '\n');
  writeFileSync(out + '.html', snippet(built, { id: flag('id', 'captions'), fps: +flag('fps', 30), band: +flag('band', 0.70),
                                                track: flag('track', 20), size: +flag('size', 56), duration: film.duration, fonts }));
  for (const c of cues)
    console.log(`${c.id.padEnd(7)} ${c.start.toFixed(2).padStart(6)}-${c.end.toFixed(2).padEnd(6)} ${c.dir} ${c.read.ok ? 'ok  ' : 'SHORT'} `
      + `${c.read.rule} ${c.read.got.toFixed(2)}/${c.read.need.toFixed(2)}s  ${c.words.map((w) => w.text).join(' ')}`);
  const rtl = cues.filter((c) => c.dir === 'rtl').length;
  console.log(`${cues.length} cues (${rtl} rtl) -> ${basename(out)}.cues.json, ${basename(out)}.html`);
  if (rtl && !fonts.length) console.log('rtl cues: pass --font for a face that covers the script (e.g. Noto Sans Arabic), or set --cap-font');
  for (const w of warnings) console.log('WARN ' + w);
  process.exit(warnings.length ? 1 : 0);
}
