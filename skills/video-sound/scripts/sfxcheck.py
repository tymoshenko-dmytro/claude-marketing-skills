#!/usr/bin/env python3
"""Will each sound effect be heard? Reads the same timeline.json as mix.py and judges every
effect against the voice and the music at the moment it plays - the ear check an agent
cannot do itself.

    sfxcheck.py timeline.json [--fg fg] [--bg bg] [--json]

Give it the timeline mix.py mixed (after sfxauto.py when gains were "auto") or mix.py's
<out>.placed.json. Events placed by "cue"/"frame" + "align" are placed the way mix.py places
them; file paths resolve like mix.py's (~ and $VIDEO_LIBRARY). A film with no voice: every
effect is judged against the music bed (GAP / LOW), and ONSET / TAIL do not apply.

Effects = events with no bus (mix.py mixes them flat). Per effect, in its first 0.5 s, in
four bands (low / low-mid / mid / high): how far its peak rises over the average of what
plays at the same time (the masker), taken in the band where it does best - a click in the
high band can be heard over a louder bass-heavy bed.
  GAP      the voice is silent there (>= 20 dB under its typical level) and the effect
           reaches the music bed's level - heard
  LOW      in a gap, but the bed covers it
  OVER     under speech, and it reaches voice + bed - audible over the words (fine for a
           hit that should cut through; too much for texture)
  MASKED   under speech and quieter than that - effectively not there
The 0 dB line is a first guess, not calibrated by ear yet: read the margin, and after the
first film checked by ear, move the line here and note it in the film's own notes (for a change
to the skill itself, open a PR - CONTRIBUTING.md).
Flags (laws.md, Sound):
  ONSET    it starts within 0.15 s before a voice onset - a sound on a first syllable
  TAIL     its tail runs under speech for >= 0.2 s louder than voice - 24 dB
Mark texture you WANT under speech (keypresses, a soft riser) with "role": "texture" in its
event; texture is only checked for TAIL and ONSET. mix.py ignores the extra key.

Levels are compared before the master gain (one static gain, so nothing moves relative to
anything else). The bed is taken at its static gain without the duck - in a gap it is not
ducked anyway, under speech this overstates it, so LOW/MASKED err on the safe side.
Idea from video-talkcraft's sfx_check (presence + audibility); written from scratch here.

Exit: 0 every non-texture effect is GAP or OVER with no flags; 1 otherwise.
"""
import argparse, importlib.util, json, pathlib, subprocess, sys
import numpy as np

_spec = importlib.util.spec_from_file_location("mixmod", pathlib.Path(__file__).with_name("mix.py"))
mix = importlib.util.module_from_spec(_spec); _spec.loader.exec_module(mix)

SR = 16000
HOP = int(0.01 * SR); WIN = int(0.02 * SR)

def decode(path):
    raw = subprocess.run(["ffmpeg", "-v", "error", "-i", mix.resolve(path), "-vn", "-ac", "1", "-ar", str(SR),
                          "-f", "s16le", "-"], capture_output=True, check=True).stdout
    return np.frombuffer(raw, dtype=np.int16).astype(np.float64) / 32768.0

def frames_db(x):
    n = max(1, (len(x) - WIN) // HOP + 1)
    idx = np.arange(WIN)[None, :] + HOP * np.arange(n)[:, None]
    p = np.mean(np.pad(x, (0, WIN))[idx] ** 2, axis=1)
    return 10 * np.log10(p + 1e-12)

BANDS = [(0, 300), (300, 1000), (1000, 3000), (3000, 8000)]   # Hz
BNAME = ["low", "low-mid", "mid", "high"]

def band_db(x, f0, f1):
    """Per-band level (dB) of 20 ms frames f0..f1 of signal x: shape (frames, bands)."""
    idx = np.arange(WIN)[None, :] + HOP * np.arange(max(0, f0), max(f0 + 1, f1))[:, None]
    seg = np.pad(x, (0, WIN))[np.clip(idx, 0, len(x) + WIN - 1)] * np.hanning(WIN)
    spec = np.abs(np.fft.rfft(seg, axis=1)) ** 2
    hz = np.fft.rfftfreq(WIN, 1 / SR)
    return 10 * np.log10(np.stack([spec[:, (hz >= lo) & (hz < hi)].sum(1) for lo, hi in BANDS], 1) + 1e-12)

def margin(fx_b, mask_b):
    """How far the effect's peak rises over the masker's average, in the band where it does best.
    Bands where the effect itself is 30 dB under its own strongest band do not count."""
    pk = fx_b.max(0); mk = 10 * np.log10(np.mean(10 ** (mask_b / 10), 0) + 1e-12)
    use = pk > pk.max() - 30
    d = np.where(use, pk - mk, -np.inf)
    return float(d.max()), BNAME[int(d.argmax())]

def mean_db(fr, a, b):
    seg = fr[max(0, a):max(a + 1, b)]
    return float(10 * np.log10(np.mean(10 ** (seg / 10)) + 1e-12)) if len(seg) else -120.0

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("timeline"); ap.add_argument("--fg", default="fg"); ap.add_argument("--bg", default="bg")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()
    T = json.loads(pathlib.Path(a.timeline).read_text())
    total = float(T["total"]); N = int(total * SR) + SR
    fg, bg, fx = np.zeros(N), np.zeros(N), []
    for e in T["events"]:
        if e.get("gain") == "auto" or e.get("pitch") == "auto":
            sys.exit(f"{e['file']}: \"auto\" gain/pitch - check the timeline sfxauto.py resolved, not the one before it")
        x = decode(e["file"]) * 10 ** (e.get("gain", 0) / 20)
        at = e["at"] if "at" in e and "cue" not in e and "frame" not in e else mix.place(e)
        s = int(round(at * SR)); x = x[:max(0, N - s)]
        bus = e.get("bus")
        if bus == a.fg: fg[s:s + len(x)] += x
        elif bus == a.bg: bg[s:s + len(x)] += x
        elif bus is None: fx.append((e, s, x))
    if not fx: sys.exit("no effects (events without a bus) in the timeline")
    Ffg, Fbg = frames_db(fg), frames_db(bg)
    voiced = bool(np.any(fg))                                     # a film with no voice: all gaps
    active = Ffg[Ffg > Ffg.max() - 35]
    ref = float(np.median(active)) if voiced and len(active) else 0.0   # typical speech level
    fi = lambda t: int(t * SR / HOP)

    rows = []
    for e, s, x in sorted(fx, key=lambda r: r[1]):
        t = s / SR; dur = len(x) / SR
        if not len(x): continue                                   # starts after the end
        buf = np.zeros(N); buf[s:s + len(x)] = x; Fx = frames_db(buf)
        w0, w1 = fi(t), fi(t + min(dur, 0.5))
        v = mean_db(Ffg, w0, w1)
        fx_b = band_db(buf, w0, w1)
        if v < ref - 20:                                   # a gap in the speech: the bed is the masker
            mg, band = margin(fx_b, band_db(bg, w0, w1)); cls = "GAP" if mg >= 0 else "LOW"
        else:                                              # under speech: voice + bed
            mg, band = margin(fx_b, band_db(fg + bg, w0, w1)); cls = "OVER" if mg >= 0 else "MASKED"
        flags = []
        if voiced and mean_db(Ffg, fi(t - 0.15), fi(t)) < ref - 20 and Ffg[fi(t):fi(t + 0.25)].max(initial=-120) > ref - 6:
            flags.append("ONSET")
        a0, a1 = fi(t + 0.15), min(len(Fx), len(Ffg), fi(t + dur))
        if voiced and a1 > a0:
            under = (Ffg[a0:a1] > ref - 20) & (Fx[a0:a1] > Ffg[a0:a1] - 24)
            if under.sum() * HOP / SR >= 0.2: flags.append("TAIL")
        texture = e.get("role") == "texture"
        bad = bool(flags) or (not texture and cls not in ("GAP", "OVER"))
        rows.append(dict(at=round(t, 2), file=pathlib.Path(e["file"]).name, role=e.get("role", "event"), cls=cls,
                         flags=flags, margin_db=round(mg, 1), band=band, bad=bad))

    if a.json:
        print(json.dumps({"speech_level_db": round(ref, 1) if voiced else None, "effects": rows}, indent=1))
    else:
        print(f"sfxcheck {a.timeline}  {len(rows)} effects  "
              + (f"typical speech {ref:.1f} dB (pre-master)" if voiced else "no voice: effects judged against the bed"))
        for r in rows:
            mark = "!!" if r["bad"] else "  "
            print(f"{mark} {r['at']:6.2f}s  {r['cls']:6} {','.join(r['flags']):11} {r['margin_db']:+6.1f} dB over masker ({r['band']:7})  "
                  f"{'[texture] ' if r['role'] == 'texture' else ''}{r['file']}")
        c = {k: sum(r["cls"] == k for r in rows) for k in ("GAP", "LOW", "OVER", "MASKED")}
        print(f"GAP {c['GAP']} · OVER {c['OVER']} · LOW {c['LOW']} · MASKED {c['MASKED']} · "
              f"flagged {sum(bool(r['flags']) for r in rows)} · to look at {sum(r['bad'] for r in rows)}")
    sys.exit(1 if any(r["bad"] for r in rows) else 0)

main()
