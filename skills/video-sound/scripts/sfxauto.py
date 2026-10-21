#!/usr/bin/env python3
"""Resolve "auto" gains and pitches in a mix timeline, before mix.py.

    sfxauto.py timeline.json timeline.resolved.json [--duck fg bg] [--depth 7] [--merge 1.0] [--key "C major"]
    mix.py timeline.resolved.json out.wav --duck fg bg

Adapted from github.com/Bodila51/opus-sound-layer scripts/mix.py @52ac266 (MIT, (c) 2026
Bodila51): the per-band gain solver and its caps. Our changes follow video-studio laws.md:

  "gain": "auto" on an effect
    The bed is the music (ducked per passage, with any stop_before) plus the voice, at their
    timeline gains. In the effect's active window (10 ms before its peak until it falls 20 dB,
    40-150 ms), in seven octave bands 125 Hz-16 kHz, only bands carrying >= 10% of the
    effect's energy count. Support effects ("hero" absent) are lifted 3.5 dB over the bed in
    their easiest band; "hero": true effects 5 dB in their main band. Caps: the 2-8 kHz lift
    stays under 6 dB (hero 9; a hero whose body is under 2 kHz is exempt), and the effect's peak
    under the local bed peak +6 dB (hero +8; floor -26 dBFS). Then each sound/weight group is
    held within +-2 dB of its median, and a non-hero within 0.15 s of the previous peak x0.6.
    OURS: an effect whose peak falls inside a voice passage is set as texture only - its main
    band 24 dB under the bed - and reported ("move it to a gap to be heard"), because nothing
    that should be heard goes over a voice.
  "pitch": "auto" on a tonal effect
    The effect's note (sidecar `note`, or the strongest spectral line above 80 Hz standing 8x
    over its neighbourhood) is moved by at most +-3 semitones onto the music's tonic or fifth,
    else another scale tone. The key: --key, the timeline's "key", or the bed's catalogue entry
    ($VIDEO_LIBRARY/catalog/music.json, from tools/music_key.py) when its confidence is >= 0.05.
    No clear note or no clear key = pitch 0, reported.

Run with the library venv (numpy, scipy): $VIDEO_LIBRARY/tools/.venv/bin/python sfxauto.py ...
(make it with library.py venv). File paths resolve like mix.py's (~ and $VIDEO_LIBRARY).
Prints a table; the resolved timeline carries an "auto" note per event (band, reason) that
mix.py ignores.
"""
import argparse, importlib.util, json, math, os, pathlib, subprocess, sys
import numpy as np
from scipy import signal

SR = 48000
BANDS = [(125, 250), (250, 500), (500, 1000), (1000, 2000), (2000, 4000), (4000, 8000), (8000, 16000)]
LIB = pathlib.Path(os.path.expanduser(os.environ.get("VIDEO_LIBRARY") or "~/.local/share/marketing-agent-kit/video-library"))
NAMES = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]
_spec = importlib.util.spec_from_file_location("mixmod", pathlib.Path(__file__).with_name("mix.py"))
mix = importlib.util.module_from_spec(_spec); _spec.loader.exec_module(mix)


def db(v): return 20 * np.log10(v + 1e-12)
def undb(d): return 10 ** (d / 20)


def load(path):
    raw = subprocess.run(["ffmpeg", "-v", "error", "-i", mix.resolve(path), "-ac", "1", "-ar", str(SR), "-f", "f32le", "-"],
                         capture_output=True, check=True).stdout
    return np.frombuffer(raw, np.float32).astype(np.float64)


def varispeed(x, r):
    if r == 1.0: return x
    n = int(len(x) / r)
    return np.interp(np.arange(n) * r, np.arange(len(x)), x)


def band_rms(x, lo, hi):
    lo = max(20.0, lo); hi = min(SR / 2 - 100, hi)
    if len(x) < 64 or hi <= lo * 1.05: return 0.0
    return float(np.sqrt(np.mean(signal.sosfilt(signal.butter(4, [lo, hi], "bandpass", fs=SR, output="sos"), x) ** 2)))


def bands(x): return np.array([band_rms(x, lo, hi) for lo, hi in BANDS])


def active_window(xs, pk):
    n = max(1, int(0.005 * SR)); seg = xs[pk: pk + int(0.3 * SR)]
    env = np.sqrt(np.convolve(seg * seg, np.ones(n) / n, mode="same"))
    below = [i for i in np.where(env < env.max() * 0.1)[0] if i > np.argmax(env)] if len(env) else []
    d = np.clip((below[0] if below else len(env)) / SR, 0.04, 0.15)
    return max(0, pk - int(0.01 * SR)), pk + int(d * SR)


def note_of(path, x):
    side = pathlib.Path(mix.resolve(path)).with_suffix(".json")
    if side.exists():
        n = json.loads(side.read_text()).get("note")
        if n is not None: return float(n)
    s = np.abs(np.fft.rfft(x[: SR] * np.hanning(min(len(x), SR)))) if len(x) else np.array([])
    f = np.fft.rfftfreq(min(len(x), SR), 1 / SR) if len(x) else np.array([])
    if len(s) < 16: return None
    m = f > 80; i = int(np.argmax(np.where(m, s, 0)))
    nb = np.median(s[max(0, i - 40):i + 40]) + 1e-12
    if s[i] < 8 * nb: return None
    return 69 + 12 * math.log2(f[i] / 440)


def parse_key(k):
    if not k: return None
    name, mode = k.split()[0], (k.split()[1] if len(k.split()) > 1 else "major")
    return NAMES.index(name), mode


def key_from_catalog(bg_files):
    try:
        music = json.loads((LIB / "catalog/music.json").read_text())
    except Exception:
        return None, "no music catalogue (video-sound scripts/library.py install)"
    for f in bg_files:
        for m in music:   # matched by file name, so an external track works once its file is in place
            if pathlib.Path(mix.resolve(f)).name == pathlib.Path(m["path"]).name and m.get("key"):
                if (m.get("keyConfidence") or 0) >= 0.05: return m["key"], f"catalogue ({m['id']})"
                return None, f"catalogue key of {m['id']} is ambiguous ({m.get('keyConfidence')})"
    return None, "bed not in the catalogue"


def best_shift(note, tonic, mode):
    scale = [0, 2, 4, 5, 7, 9, 11] if mode == "major" else [0, 2, 3, 5, 7, 8, 10]
    best = None
    for st in range(-3, 4):
        pc = round(note + st) % 12; rel = (pc - tonic) % 12
        cost = abs(st) + (0 if rel in (0, 7) else 0.5 if rel in scale else 99)
        if best is None or cost < best[0]: best = (cost, st, rel)
    return best[1] if best[0] < 99 else 0


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("timeline"); ap.add_argument("out")
    ap.add_argument("--duck", nargs=2, default=["fg", "bg"]); ap.add_argument("--depth", type=float, default=7.0)
    ap.add_argument("--merge", type=float, default=1.0); ap.add_argument("--key")
    a = ap.parse_args()
    T = json.loads(pathlib.Path(a.timeline).read_text()); ev = T["events"]; total = T["total"]
    N = int(total * SR) + SR; fg, bg = a.duck

    # ---- key for auto pitch
    key, why_key = (a.key or T.get("key")), "given"
    if not key and any(e.get("pitch") == "auto" for e in ev):
        key, why_key = key_from_catalog([e["file"] for e in ev if e.get("bus") == bg])
    pk = parse_key(key) if key else None

    # ---- resolve pitch first (it changes placement and spectrum)
    for e in ev:
        if e.get("pitch") != "auto": continue
        x = load(e["file"]); n = note_of(e["file"], x)
        if pk is None or n is None:
            e["pitch"] = 0; e["auto"] = dict(e.get("auto", {}), pitch=f"0 ({'no clear key: ' + why_key if pk is None else 'no clear note'})")
        else:
            st = best_shift(n, *pk); e["pitch"] = st
            e["auto"] = dict(e.get("auto", {}), pitch=f"{st:+d} st: note {NAMES[round(n) % 12]} -> {NAMES[round(n + st) % 12]} in {key} ({why_key})")

    for e in ev: e["at"] = round(mix.place(e), 4)

    # ---- the bed: music ducked per passage (+ stop_before), plus the voice
    music, voice = np.zeros(N), np.zeros(N)
    for e in ev:
        if e.get("bus") not in (fg, bg) or not isinstance(e.get("gain", 0), (int, float)): continue
        x = varispeed(load(e["file"]), mix.ratio(e)) * undb(e.get("gain", 0)); s = int(e["at"] * SR)
        tgt = voice if e.get("bus") == fg else music
        tgt[s:s + len(x)] += x[: max(0, N - s)]
    spans = sorted((e["at"], e["at"] + mix.dur(e["file"]) / mix.ratio(e)) for e in ev if e.get("bus") == fg)
    passages = []
    for s0, s1 in spans:
        if passages and s0 - passages[-1][1] < a.merge: passages[-1][1] = max(passages[-1][1], s1)
        else: passages.append([s0, s1])
    t = np.arange(N) / SR; D = np.zeros(N)
    for p0, p1 in passages:
        D = np.maximum(D, np.clip((t - (p0 - 0.3)) / 0.3, 0, 1) * np.clip((p1 + 0.5 - t) / 0.5, 0, 1))
    music *= undb(-a.depth * D)
    for e in ev:
        c = mix.cue_of(e)
        if e.get("stop_before") and c is not None:
            w = np.clip((t - (c - 0.4)) / 0.02, 0, 1) * np.clip((c - t) / 0.02, 0, 1); music *= 1 - 0.937 * w
    bed = music + voice

    # ---- solve each auto gain
    autos = []
    for e in ev:
        if e.get("gain") != "auto": continue
        x = varispeed(load(e["file"]), mix.ratio(e)); s = int(e["at"] * SR)
        xs = np.zeros(N); a0, a1 = max(0, s), min(N, s + len(x)); xs[a0:a1] = x[a0 - s:a1 - s]
        n = max(1, int(0.002 * SR)); env = np.convolve(xs * xs, np.ones(n) / n, mode="same")
        pkt = int(np.argmax(env)); w0, w1 = active_window(xs, pkt); w1 = min(N, w1)
        hero = bool(e.get("hero")); lift = 5.0 if hero else 3.5
        e_b = bands(xs[w0:w1]); m_b = np.maximum(bands(bed[w0:w1]), undb(-60))
        share = e_b ** 2 / (np.sum(e_b ** 2) + 1e-20)
        if hero: k = int(np.argmax(share)); why = "main band (hero)"
        else:
            need = np.where(share >= 0.1, m_b / (e_b + 1e-12), np.inf); k = int(np.argmin(need)); why = "easiest band"
        under_voice = any(p0 <= pkt / SR <= p1 for p0, p1 in passages)
        if under_voice:
            km = int(np.argmax(share)); g = float(m_b[km] * undb(-24) / (e_b[km] + 1e-12))
            why = "UNDER A VOICE: texture only (-24 dB) - move it to a gap to be heard"; k = km
        else:
            g = float(m_b[k] * np.sqrt(10 ** (lift / 10) - 1) / (e_b[k] + 1e-12))
            bed_rms = float(np.sqrt(np.mean(bed[w0:w1] ** 2))) if w1 > w0 else 0.0
            e28 = band_rms(xs[w0:w1], 2000, 8000); m28 = max(band_rms(bed[w0:w1], 2000, 8000), bed_rms * undb(-20), undb(-60))
            if e28 > 0 and not (hero and BANDS[k][1] <= 2000):
                g28 = m28 * np.sqrt(10 ** ((9 if hero else 6) / 10) - 1) / e28
                if g28 < g: g, why = g28, "2-8 kHz cap"
            reach = int((1.0 if hero else 0.15) * SR); lw0, lw1 = max(0, pkt - reach), min(N, pkt + reach)
            bed_pk = max(np.max(np.abs(bed[lw0:lw1])) if lw1 > lw0 else 0.0, undb(-26))
            gp = bed_pk * undb(8 if hero else 6) / (np.max(np.abs(x)) + 1e-12)
            if gp < g: g, why = gp, "peak cap"
        autos.append((e, float(db(g)), pkt / SR, hero, why, BANDS[k], under_voice))
    groups = {}
    for e, gd, *_ in autos: groups.setdefault((e["file"], bool(e.get("hero"))), []).append(gd)
    last = -9.0
    for e, gd, pk_s, hero, why, band, uv in sorted(autos, key=lambda r: r[2]):
        med = float(np.median(groups[(e["file"], hero)])); gd = float(np.clip(gd, med - 2, med + 2))
        if pk_s - last < 0.15 and not hero: gd += db(0.6); why += " + cluster x0.6"
        last = pk_s
        e["gain"] = round(gd, 2)
        e["auto"] = dict(e.get("auto", {}), gain=f"{gd:+.1f} dB: {why}, band {band[0]}-{band[1]} Hz")
    for e in ev: e.pop("at", None) if ("cue" in e or "frame" in e) else None
    pathlib.Path(a.out).write_text(json.dumps(T, indent=1, ensure_ascii=False))
    for e in ev:
        if "auto" in e: print(f"  {pathlib.Path(e['file']).stem[:40]:40s} {'; '.join(e['auto'].values())}")
    print(f"-> {a.out}")


if __name__ == "__main__":
    main()
