#!/usr/bin/env python3
"""Lay voices, effects and a music bed on a timeline and mix down - in stereo, with
no gain riding anywhere.

    mix.py timeline.json out.wav [--duck FG BG] [--depth 7] [--merge 1.0] [--mono]

timeline.json (same shape motion-card used, so old projects only change the path):
{
  "total": 12.4,
  "loudness": -14,                                   # master target, LUFS
  "events": [
    {"file": "audio/lines/l1.wav", "at": 0.35, "gain": 0,  "bus": "fg"},
    {"file": "audio/bed.wav",      "at": 0.0,  "gain": -8, "bus": "bg"},
    {"file": "/abs/sfx/click.wav", "at": 2.10, "gain": -18}
  ]
}
Relative paths resolve against the current directory; `~` and `$VIDEO_LIBRARY` are expanded
(`$VIDEO_LIBRARY` defaults to ~/.local/share/marketing-agent-kit/video-library, the sound library
that video-sound's `library.py install` puts there), so a library sound is written
    {"file": "$VIDEO_LIBRARY/sfx/osl/hit/fs-558238-distorted-impact-short-wav-1.wav", ...}
- the form `sfxlib.py browse` prints. Events with no "bus" are mixed flat and never ducked.

Placing an effect ON a picture event (after opus-sound-layer, MIT): instead of
"at", give "cue" (seconds, or "frame" + "fps") and "align":
    {"file": ".../hit.wav", "cue": 3.20, "align": "peak", "gain": -10}
  peak  - the sound's loudest moment (2 ms RMS envelope) lands on the cue: at = cue - peak.
          The peak comes from the sound's sidecar JSON (`peak_offset_s`, library sfx/osl/) or
          is measured from the file.
  start - the file starts on the cue (the same as "at": cue).
  end   - the file ends on the cue (risers, reverses).
Every resolved placement is written to <out>.placed.json for the sync check
(video-check soundqa).

Per-event extras (after opus-sound-layer, MIT):
  "pitch": 2          semitones, varispeed (pitch and length change together); a peak-aligned
                      event keeps its peak on the cue. "auto" is resolved by sfxauto.py.
  "gain": "auto"      resolved by sfxauto.py (per-band level against music + voice).
  "stop_before": true on an effect: the music bus drops to -24 dB for the 0.4 s before its cue
                      (20 ms edges) and comes back on the hit - one real silence before the peak.
  "build": true       on an effect: the 2 s before its cue the music is high-passed, rising
                      40 -> 300 Hz, full range back on the cue.

A shared room on the effects (a blind A/B picked it: "effects a little louder, more
interesting"): the flat bus (events with no "bus") is convolved with a synthetic
stereo room - decorrelated noise, decay to -60 dB at 0.6 s, band 250 Hz-7 kHz, 12 ms
pre-delay, unit energy (opus-sound-layer's recipe, MIT) - and added at --room-db (-16) under
the dry effects. The room is OFF while a voice passage runs (the same passages the duck
uses), so nothing with a tail sits over a voice. --room off disables it.

--duck FG BG: the BG bus dips by --depth dB under the FG bus - but per spoken PASSAGE,
not per word. FG events closer together than --merge seconds form one passage; the dip
starts 0.30 s before the passage (ramp 0.30 s) and recovers 0.50 s after it. The
previous version keyed a compressor on the voice and let the bed jump ~11 dB back up
in every 0.2-0.3 s gap between words; it was heard as "louder, quieter, louder".

The master is ONE static gain to "loudness" plus a 4x-oversampled limiter that only catches
peaks at --tp-ceiling (-2 dBTP), the gain re-solved until the file lands within 0.3 LU of the
target. Single-pass loudnorm is a dynamic rider and is not used.
"""
import argparse, array, json, os, pathlib, re, subprocess, sys

LIBRARY = os.path.expanduser(os.environ.get("VIDEO_LIBRARY") or "~/.local/share/marketing-agent-kit/video-library")


def resolve(p):
    """A timeline path with ~ and $VARS expanded; $VIDEO_LIBRARY falls back to the kit's default."""
    s = str(p).replace("${VIDEO_LIBRARY}", LIBRARY).replace("$VIDEO_LIBRARY", LIBRARY)
    return os.path.expanduser(os.path.expandvars(s))


def ff(*a, **k):
    return subprocess.run(["ffmpeg", "-hide_banner", *a], capture_output=True, text=True, **k)

def dur(p):
    return float(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of",
                                 "default=nw=1:nk=1", resolve(p)], capture_output=True, text=True).stdout)

def peak_offset(p):
    """Seconds from the file's start to its loudest 2 ms (RMS); the sidecar wins if present."""
    p = resolve(p)
    side = pathlib.Path(p).with_suffix(".json")
    if side.exists():
        try:
            v = json.loads(side.read_text()).get("peak_offset_s")
            if v is not None: return float(v)
        except Exception:
            pass
    raw = subprocess.run(["ffmpeg", "-v", "error", "-i", str(p), "-ac", "1", "-ar", "48000", "-f", "s16le", "-"],
                         capture_output=True).stdout
    x = array.array("h"); x.frombytes(raw[: len(raw) // 2 * 2])
    w, best, at = 96, -1.0, 0
    for i in range(0, max(1, len(x) - w), w):
        e = sum(v * v for v in x[i:i + w])
        if e > best: best, at = e, i
    return (at + w / 2) / 48000


def ratio(e):
    """Varispeed ratio for a "pitch" in semitones (1.0 = untouched)."""
    st = e.get("pitch", 0)
    return 2 ** (float(st) / 12) if isinstance(st, (int, float)) and st else 1.0


def cue_of(e):
    return e["cue"] if "cue" in e else e["frame"] / e.get("fps", 30) if "frame" in e else None


def place(e):
    """Resolve "cue"/"frame" + "align" into "at" (seconds); pitch shortens/lengthens the file."""
    if "at" in e and "cue" not in e and "frame" not in e:
        return e["at"]
    cue, r = cue_of(e), ratio(e)
    al = e.get("align", "peak")
    if al == "peak": return cue - peak_offset(e["file"]) / r
    if al == "end": return cue - dur(e["file"]) / r
    return cue


def integrated(p):
    r = ff("-i", str(p), "-af", "ebur128", "-f", "null", "-").stderr
    return float(re.findall(r"I:\s+(-?[\d.]+) LUFS", r)[-1])

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("timeline"); ap.add_argument("out")
    ap.add_argument("--duck", nargs=2, metavar=("FG", "BG"))
    ap.add_argument("--depth", type=float, default=7.0, help="dB the bed dips under speech")
    ap.add_argument("--merge", type=float, default=1.0, help="gaps shorter than this stay ducked")
    ap.add_argument("--mono", action="store_true")
    ap.add_argument("--room", choices=["on", "off"], default="on", help="shared room on the effects bus, off under speech")
    ap.add_argument("--room-db", type=float, default=-16.0, help="room level under the dry effects")
    ap.add_argument("--tp-ceiling", type=float, default=-2.0,
                    help="true-peak ceiling (dBTP) of an oversampled limiter; leaves room for AAC overshoot")
    a = ap.parse_args()

    T = json.loads(pathlib.Path(a.timeline).read_text())
    total, ev, target = T["total"], T["events"], T.get("loudness", -14)
    if not ev: sys.exit("no events")
    ch = "mono" if a.mono else "stereo"

    for e in ev:
        if not os.path.exists(resolve(e["file"])):
            hint = (" - is the sound library installed? (video-sound scripts/library.py doctor)"
                    if "VIDEO_LIBRARY" in e["file"] or e["file"].startswith(LIBRARY) else "")
            sys.exit(f"{e['file']}: no such file{hint}")
        if e.get("gain") == "auto" or e.get("pitch") == "auto":
            sys.exit(f"{e['file']}: \"auto\" gain/pitch - resolve the timeline with sfxauto.py first")
        e["at"] = round(place(e), 4)
        if e["at"] < 0: sys.exit(f"{e['file']}: placed at {e['at']} s (before the start)")
    ins, filt, buses = [], [], {}
    for n, e in enumerate(ev):
        ins += ["-i", resolve(e["file"])]
        ms = int(round(e["at"] * 1000))
        r = ratio(e)
        vs = f"asetrate={48000 * r:.3f},aresample=48000," if r != 1.0 else ""
        filt.append(f"[{n}:a]aresample=48000,{vs}aformat=channel_layouts={ch},volume={e.get('gain', 0)}dB,"
                    f"adelay={ms}|{ms}[v{n}]")
        buses.setdefault(e.get("bus", "_flat"), []).append(f"[v{n}]")

    def bus(name, extra=""):
        lbl = buses[name]
        filt.append("".join(lbl) + f"amix=inputs={len(lbl)}:normalize=0:dropout_transition=0,"
                    f"apad,atrim=0:{total}{extra}[B{name}]")
        return f"[B{name}]"

    parts, ducked, D = [], None, None
    # one real silence before the peak / a filter build into it (music bus only)
    stops = [cue_of(e) for e in ev if e.get("stop_before") and cue_of(e) is not None]
    builds = [cue_of(e) for e in ev if e.get("build") and cue_of(e) is not None]
    STOP = "1"
    if stops:
        w = [f"clip((t-{c - 0.4:.3f})/0.02,0,1)*clip(({c:.3f}-t)/0.02,0,1)" for c in stops]
        W = w[0]
        for x in w[1:]: W = f"max({W},{x})"
        STOP = f"1-0.937*({W})"                                  # -24 dB
    K = None   # build: crossfade full music -> music high-passed at 300 Hz over the 2 s before the cue
    if builds:
        w = [f"clip((t-{c - 2.0:.3f})/2.0,0,1)*clip(({c:.3f}-t)/0.01,0,1)" for c in builds]
        K = w[0]
        for x in w[1:]: K = f"max({K},{x})"
    bgname = a.duck[1] if a.duck else "bg"
    def music_auto(label):
        """stop + build on the music bus label; returns the new label"""
        out = label
        if stops:
            filt.append(f"{out}asetnsamples=240,volume='{STOP}':eval=frame[MBs]"); out = "[MBs]"
        if K:
            filt.append(f"{out}asplit=2[MBd][MBh]")
            filt.append(f"[MBh]highpass=f=300:poles=2,highpass=f=300:poles=2,asetnsamples=240,volume='{K}':eval=frame[MBh2]")
            filt.append(f"[MBd]asetnsamples=240,volume='1-({K})':eval=frame[MBd2]")
            filt.append("[MBd2][MBh2]amix=inputs=2:normalize=0:dropout_transition=0[MBb]"); out = "[MBb]"
        return out
    if a.duck and all(b in buses for b in a.duck):
        fg, bg = a.duck
        spans = sorted((e["at"], e["at"] + dur(e["file"])) for e in ev if e.get("bus") == fg)
        passages = []
        for s0, s1 in spans:
            if passages and s0 - passages[-1][1] < a.merge: passages[-1][1] = max(passages[-1][1], s1)
            else: passages.append([s0, s1])
        terms = [f"clip((t-{p0 - 0.30:.3f})/0.30,0,1)*clip(({p1 + 0.50:.3f}-t)/0.50,0,1)" for p0, p1 in passages]
        D = terms[0]
        for t in terms[1:]: D = f"max({D},{t})"
        parts.append(bus(fg))
        parts.append(music_auto(bus(bg, f",asetnsamples=240,volume='pow(10,-{a.depth}*({D})/20)':eval=frame")))
        ducked = (bg, fg, passages)
    for k in buses:
        if a.duck and k in a.duck: continue
        if k == "_flat" and a.room == "on":
            ir = pathlib.Path(a.out).with_suffix(".room-ir.wav")
            noise = lambda seed: f"anoisesrc=d=0.6:c=white:r=48000:a=0.5:seed={seed}"
            lavfi = (f"{noise(11)}[l];{noise(23)}[r];[l][r]amerge=inputs=2," if ch == "stereo" else f"{noise(11)},") + \
                    "volume='exp(-t*11.513)':eval=frame,highpass=f=250,lowpass=f=7000,adelay=12:all=1"
            ff("-f", "lavfi", "-i", lavfi, "-ar", "48000", str(ir), "-y", check=True)
            ins += ["-i", str(ir)]; irn = len(ins) // 2 - 1
            # +10 dB: ffmpeg's afir normalisation sits 10 dB under the numpy unit-energy IR that
            # won the blind A/B (measured on a camera-moves test film)
            lvl = 10 ** ((a.room_db + 10.0) / 20)
            amp = f"{lvl:.5f}*(1-({D}))" if D else f"{lvl:.5f}"
            fl = bus(k)
            filt.append(f"{fl}asplit=2[Fd][Fw]")
            filt.append(f"[Fw][{irn}:a]afir=irnorm=2:irgain=1,asetnsamples=240,volume='{amp}':eval=frame[Fwet]")
            filt.append("[Fd][Fwet]amix=inputs=2:normalize=0:dropout_transition=0[Froom]")
            parts.append("[Froom]")
            continue
        parts.append(music_auto(bus(k)) if k == bgname else bus(k))
    if len(parts) > 1:
        filt.append("".join(parts) + f"amix=inputs={len(parts)}:normalize=0:dropout_transition=0,apad,atrim=0:{total}[m]")
        src = "[m]"
    else:
        src = parts[0]

    out = pathlib.Path(a.out)
    raw = out.with_suffix(".raw.wav")
    r = ff(*ins, "-filter_complex", ";".join(filt) + f";{src}anull[o]", "-map", "[o]",
           "-ar", "48000", "-ac", "1" if a.mono else "2", str(raw), "-y")
    if r.returncode: sys.exit(r.stderr[-2000:])
    # one static gain to the target, then an oversampled (4x) peak-only limiter at the true-peak
    # ceiling; the gain is re-solved until the file lands within 0.3 LU (limiting costs loudness)
    lim = 10 ** (a.tp_ceiling / 20)
    g = target - integrated(raw)
    for _ in range(4):
        ff("-i", str(raw), "-af", f"volume={g:.2f}dB,aresample=192000,alimiter=limit={lim:.4f}:attack=1:release=60:"
           "level=disabled,aresample=48000", "-ar", "48000", "-ac", "1" if a.mono else "2", "-c:a", "pcm_s24le",
           str(out), "-y", check=True)
        miss = target - integrated(out)
        if abs(miss) <= 0.3: break
        g += miss
    raw.unlink()
    pathlib.Path(a.out).with_suffix(".room-ir.wav").unlink(missing_ok=True)
    (out.with_suffix(".placed.json")).write_text(json.dumps(
        {"total": total, "events": [{k: e[k] for k in e if k in ("file", "at", "cue", "frame", "fps", "align", "gain", "bus", "role", "hero", "visual", "roi")}
                                     for e in ev]}, indent=1, ensure_ascii=False))

    rep = ff("-i", str(out), "-af", "ebur128=peak=true", "-f", "null", "-").stderr
    I = re.findall(r"I:\s+(-?[\d.]+) LUFS", rep)[-1]; P = re.findall(r"Peak:\s+(-?[\d.]+) dBFS", rep)[-1]
    print(f"  {out}  {total}s  {len(ev)} events  {ch}  I={I} LUFS  true peak={P} dBFS  (master {g:+.1f} dB)")
    if ducked:
        print(f"  {ducked[0]} dips {a.depth} dB under {ducked[1]} in {len(ducked[2])} passage(s): "
              + ", ".join(f"{p0:.2f}-{p1:.2f}" for p0, p1 in ducked[2]))

if __name__ == "__main__":
    main()
