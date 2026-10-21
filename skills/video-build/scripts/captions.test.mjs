// node --test captions.test.mjs
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { mkdtempSync, writeFileSync, readFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { spawnSync } from 'node:child_process';
import { fileURLToPath } from 'node:url';
import { buildCues, lineDir, lineWords, readNeed, snippet, CUE_MIN_WORD_S, CHAIN_GAP_FRAMES, CUE_FADE_S } from './captions.mjs';

const CLI = fileURLToPath(new URL('./captions.mjs', import.meta.url));
// words at a steady pace: n words, `per` seconds each, `gap` silence after punctuation
const say = (text, per = 0.3, start = 0, pause = 0) => {
  let t = start;
  return text.split(' ').map((w) => {
    const o = { w, s: +t.toFixed(3), e: +(t + per * 0.85).toFixed(3) };
    t += per + (/[,.،؟?]$/.test(w) ? pause : 0);
    return o;
  });
};

test('direction: the script most letters are in', () => {
  assert.equal(lineDir('ويمكنك متابعة القطار على Google Maps.'), 'rtl');
  assert.equal(lineDir('في القطار شبكة Wi-Fi مجانية'), 'rtl');
  assert.equal(lineDir('בבוקר היה קר, ואחר כך יצאה השמש.'), 'rtl');
  assert.equal(lineDir('Meet our colleague محمد from Cairo'), 'ltr');   // nanoclip's "any RTL run" said rtl
});

test('slow speech with pauses splits at punctuation into short cues', () => {
  const words = say('One, two three, four five six, seven eight.', 0.45, 0, 0.7);
  const { cues, warnings } = buildCues({ lines: [{ tag: 'a', at: 1, words }] });
  assert.deepEqual(warnings, []);
  assert.ok(cues.length >= 3);
  assert.ok(cues.every((c) => c.words.length <= 4), cues.map((c) => c.words.length).join());
  assert.ok(cues.every((c) => /[,.]$/.test(c.words.at(-1).text)), 'breaks land after punctuation');
  // with 0.5 s pauses "four five six," would be on screen 1.78 s (< 1.8 s): it is merged instead
  const tight = buildCues({ lines: [{ tag: 'a', at: 1, words: say('One, two three, four five six, seven eight.', 0.45, 0, 0.5) }] });
  assert.ok(tight.cues.every((c) => c.read.ok));
  assert.ok(tight.cues.some((c) => c.words.length > 4));
});

test('fast TTS speech: a 4-word cut would be unreadable, so the line stays one cue', () => {
  // 8 words in 1.8 s, next line 0.6 s later (the test film's en1)
  const { cues, warnings } = buildCues({ duration: 10, lines: [
    { tag: 'en1', at: 0.5, words: say('The morning train leaves the station at seven.', 0.225) },
    { tag: 'en2', at: 2.9, words: say('Some passengers read.', 0.3) }] });
  assert.deepEqual(warnings, []);
  assert.equal(cues[0].words.length, 8);
  assert.ok(cues.every((c) => c.read.ok));
});

test('hard breaks: a seam (new line) and >= 0.8 s of dead air; ends never cut the last word', () => {
  const w = [...say('alpha beta', 0.3, 0), ...say('gamma delta', 0.3, 1.6)];   // 0.85 s of air
  const { cues } = buildCues({ lines: [{ tag: 'x', at: 0, words: w }, { tag: 'y', at: 4, words: say('epsilon zeta', 0.3) }] });
  assert.deepEqual(cues.map((c) => c.words.map((x) => x.text).join(' ')), ['alpha beta', 'gamma delta', 'epsilon zeta']);
  for (const c of cues) assert.ok(c.end >= c.words.at(-1).end);
});

test('chained cues are two frames apart and pop in; a cue after silence fades in', () => {
  const { cues } = buildCues({ lines: [
    { tag: 'a', at: 0.5, words: say('one two three four', 0.4) },
    { tag: 'b', at: 2.6, words: say('five six seven eight', 0.4) },
    { tag: 'c', at: 9, words: say('nine ten', 0.4) }] }, '.', { fps: 30 });
  assert.equal(+(cues[1].start - cues[0].end).toFixed(3), +(CHAIN_GAP_FRAMES / 30).toFixed(3));
  assert.equal(cues[1].fade, 0);
  assert.equal(cues[2].fade, CUE_FADE_S);
});

test('highlights: at least 0.08 s, bridged across short gaps, inside the cue', () => {
  const words = [{ w: 'a.', s: 0, e: 0 }, { w: 'b', s: 0.1, e: 0.3 }, { w: 'c', s: 0.8, e: 1.0 }];
  const { cues } = buildCues({ lines: [{ tag: 'z', at: 2, words }] });
  const ws = cues.flatMap((c) => c.words);
  assert.ok(ws[0].hiEnd - ws[0].hiStart >= CUE_MIN_WORD_S - 1e-9);
  assert.equal(ws[1].hiEnd, 2.3, 'a 0.5 s gap is not bridged');
  for (const c of cues) for (const w of c.words) assert.ok(w.hiEnd <= c.end);
});

test('a line that follows too soon is reported, not hidden', () => {
  const { warnings } = buildCues({ lines: [
    { tag: 'a', at: 0, words: say('one two three four five six seven eight nine ten', 0.2) },
    { tag: 'b', at: 2.05, words: say('next', 0.3) }] });
  assert.ok(warnings.some((w) => w.includes('readable')), warnings.join('\n'));
});

test('whisper JSON: a source window is rebased onto the film clock', () => {
  const wj = { segments: [{ words: [{ word: ' before', start: 1, end: 1.3 }, { word: ' inside', start: 3.2, end: 3.5 },
                                    { word: ' too,', start: 3.6, end: 3.9 }, { word: ' after', start: 9.5, end: 9.8 }] }] };
  const ws = lineWords({ tag: 'rec', at: 10, whisper: wj, in: 3, out: 9 });
  assert.deepEqual(ws.map((w) => [w.text, w.start]), [['inside', 10.2], ['too,', 10.6]]);
});

test('readNeed mirrors readcheck: ghosted words make a caption, solid ones a line', () => {
  const ws = say('one two three four', 0.4).map((w) => ({ text: w.w, start: w.s, end: w.e }));
  assert.equal(readNeed(ws, 3, 0.55).caption, true);
  assert.equal(readNeed(ws, 3, 1).caption, false);
  assert.equal(readNeed(ws, 3, 1).need, 1.2);
});

test('snippet: inline word spans, dir per cue, punctuation outside the pill', () => {
  const built = buildCues({ lines: [{ tag: 'ar', at: 0.5, words: say('ويمكنك متابعة القطار على Google Maps.', 0.4) }] });
  const html = snippet(built, { fonts: [['Noto Sans Arabic', 'assets/fonts/a.woff2']] });
  assert.match(html, /dir="rtl"/);
  assert.match(html, /\.cap-word \{ display: inline;/);
  assert.doesNotMatch(html, /cap-word[^}]*inline-block/);
  assert.match(html, /<span class="cap-core t">Maps<\/span><span class="cap-p"[^>]*>\.<\/span>/);
  assert.match(html, /@font-face \{ font-family: "Noto Sans Arabic"; src: url\("assets\/fonts\/a\.woff2"\)/);
  assert.match(html, /window\.mountCaptions = function \(tl\)/);
});

test('CLI: writes cues.json and the snippet, exits 0 when every cue reads', () => {
  const dir = mkdtempSync(join(tmpdir(), 'caps-'));
  writeFileSync(join(dir, 'a.words.json'), JSON.stringify({ words: say('Hello there, friend.', 0.35) }));
  writeFileSync(join(dir, 'film.json'), JSON.stringify({ duration: 4, lines: [{ tag: 'a', at: 0.5, words: 'a.words.json' }] }));
  const r = spawnSync('node', [CLI, join(dir, 'film.json'), '--band', '0.7'], { encoding: 'utf8' });
  assert.equal(r.status, 0, r.stdout + r.stderr);
  const out = JSON.parse(readFileSync(join(dir, 'captions.cues.json'), 'utf8'));
  assert.equal(out.cues.length, 1);
  assert.match(readFileSync(join(dir, 'captions.html'), 'utf8'), /--cap-y: 70\.0%/);
});
