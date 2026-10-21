#!/usr/bin/env python3
"""Check a finished film's sound against its picture, by measurement (we cannot listen).

Adapted from github.com/Bodila51/opus-sound-layer scripts/qa.py @52ac266 (MIT, (c) 2026
Bodila51), for our pipeline: it reads the placement file that video-sound's mix.py writes
(<track>.placed.json), takes frames by number (never `fps=N`), and can look at a region of
the frame - on UI films the thing that moves is small, and whole-frame motion misses it.

    soundqa.py film.mp4 --placed audio/track.placed.json [--track audio/track.wav]
               [--cues extra-cues.json] [--target -14] [--silence-ok 12.0-13.5,40-41]

Events are checked when they carry these fields (in placed.json or an extra cues file):
  "cue": 3.2  (or "frame")       the picture moment the sound belongs to
  "visual": "cut" | "move" | "land" | "appear"
                                 what happens in the picture on that frame
  "roi": [x, y, w, h]            optional region in 1920x1080 px to measure motion in
  "hero": true                   picture/sync failures FAIL instead of warn
  "align": "peak"                sync: the mix's 2 ms envelope peaks within 1 frame (hero) /
                                 2 frames (support) of the cue - skipped where a voice event
                                 overlaps (the voice would own the peak)

Checks
  picture   cut = a hard frame change within 1 frame; move = a motion peak within 3 frames;
            land = motion settling within 2 frames; appear = a change within 1 frame
  sync      as above
  offset    the film's audio lines up with the mix WAV within 1 ms (3 loudest seconds)
  loudness  integrated within 1 LU of the target; true peak <= -1 dBTP - on the encoded file
  silence   no silence of 0.5 s or more outside --silence-ok spans

Run with the sound library's venv (numpy, scipy; made by video-sound's library.py venv):
  "${VIDEO_LIBRARY:-$HOME/.local/share/marketing-agent-kit/video-library}"/tools/.venv/bin/python soundqa.py ...
Exit 1 if any check FAILs. Writes <film>.soundqa.json next to the film.
"""
import argparse, json, os, pathlib, re, subprocess, sys
import numpy as np
from scipy import signal

SR = 48000


def ff(*a):
    return subprocess.run(["ffmpeg", "-hide_banner", *a], capture_output=True, text=True)


def probe(video):
    r = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
                        "stream=width,height,r_frame_rate", "-of", "json", str(video)], capture_output=True, text=True)
    s = json.loads(r.stdout)["streams"][0]
    n, d = map(int, s["r_frame_rate"].split("/"))
    return s["width"], s["height"], n / d


def decode_audio(path):
    raw = subprocess.run(["ffmpeg", "-v", "error", "-i", str(path), "-vn", "-ac", "1", "-ar", str(SR), "-f", "f32le", "-"],
                         capture_output=True, check=True).stdout
    return np.frombuffer(raw, np.float32).astype(np.float64)


def motion_curve(video, roi=None, size=(160, 90)):
    """Mean |frame - previous| (0-255) for EVERY frame (by number), optionally in a region."""
    w, h = size
    vf = (f"crop={roi[2]}:{roi[3]}:{roi[0]}:{roi[1]}," if roi else "") + f"scale={w}:{h},format=gray"
    raw = subprocess.run(["ffmpeg", "-v", "error", "-i", str(video), "-an", "-vf", vf, "-fps_mode", "passthrough",
                          "-f", "rawvideo", "-"], capture_output=True, check=True).stdout
    fr = np.frombuffer(raw, np.uint8).reshape(-1, h, w).astype(np.float32)
    m = np.zeros(len(fr)); m[1:] = np.mean(np.abs(np.diff(fr, axis=0)), axis=(1, 2))
    return m


def picture_check(kind, f, m):
    """opus-sound-layer's thresholds (MIT)."""
    n = len(m)
    if f < 1 or f >= n: return False, "cue outside the video"
    if kind == "cut":
        lo, hi = max(1, f - 1), min(n, f + 2)
        i = lo + int(np.argmax(m[lo:hi]))
        base = np.median(m[max(1, f - 15):min(n, f + 15)]) + 1.0
        return m[i] > 4 * base and m[i] > 6.0, f"largest change at frame {i} ({m[i]:.1f} vs local {base:.1f})"
    if kind == "move":
        lo, hi = max(1, f - 3), min(n, f + 4)
        i = lo + int(np.argmax(m[lo:hi]))
        ok = m[i] >= m[max(1, i - 1)] and m[i] >= m[min(n - 1, i + 1)] and m[i] > 0.5
        return ok and abs(i - f) <= 3, f"motion peak at frame {i} ({m[i]:.2f})"
    if kind == "land":
        pre = m[max(1, f - 15):max(2, f - 1)]
        if len(pre) == 0 or pre.max() < 0.5: return False, "no motion before the landing"
        thr = max(0.25, 0.05 * pre.max())
        for i in range(max(1, f - 6), min(n, f + 7)):
            if m[i] <= thr and m[i - 1] > thr:
                return abs(i - f) <= 2, f"motion stops at frame {i}"
        return False, "motion does not stop near the cue"
    if kind == "appear":
        lo, hi = max(1, f - 1), min(n, f + 2)
        i = lo + int(np.argmax(m[lo:hi]))
        base = np.median(m[max(1, f - 15):min(n, f + 15)])
        return m[i] >= 0.3 and m[i] >= 3 * (base + 0.1), f"change at frame {i} ({m[i]:.2f} vs local {base:.2f})"
    return True, "no visual check"


LIBRARY = os.path.expanduser(os.environ.get("VIDEO_LIBRARY") or "~/.local/share/marketing-agent-kit/video-library")


def file_dur(p):
    """Length of a file named in placed.json; ~ and $VIDEO_LIBRARY expanded the way mix.py does."""
    p = os.path.expanduser(os.path.expandvars(str(p).replace("${VIDEO_LIBRARY}", LIBRARY).replace("$VIDEO_LIBRARY", LIBRARY)))
    r = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=nw=1:nk=1", p],
                       capture_output=True, text=True)
    return float(r.stdout)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("video"); ap.add_argument("--placed"); ap.add_argument("--track"); ap.add_argument("--cues")
    ap.add_argument("--target", type=float, default=-14.0); ap.add_argument("--silence-ok", default="")
    a = ap.parse_args()
    W, H, fps = probe(a.video)
    events = []
    if a.placed: events += json.loads(pathlib.Path(a.placed).read_text())["events"]
    if a.cues: events += json.loads(pathlib.Path(a.cues).read_text())["events"]
    res = []

    def add(check, ok, detail, hard=True):
        res.append(dict(check=check, status="pass" if ok else ("FAIL" if hard else "warn"), detail=detail))

    final = decode_audio(a.video)

    # offset of the encoded audio against the mix
    if a.track:
        mix = decode_audio(a.track); win = SR; lags = []
        energy = [np.sum(mix[i:i + win] ** 2) for i in range(SR // 2, max(SR // 2 + 1, len(mix) - win - SR // 2), SR // 2)]
        for k in np.argsort(energy)[-3:]:
            s = SR // 2 + int(k) * (SR // 2); r = mix[s:s + win]; R = min(12000, s)
            d = final[s - R:s + win + R]
            if len(d) < len(r) + 2 * R: continue
            c = signal.correlate(d, r, mode="valid", method="fft"); lags.append(int(np.argmax(c)) - R)
        worst = max([abs(l) for l in lags], default=0)
        add("offset", worst <= 48, f"film audio vs {pathlib.Path(a.track).name}: worst {worst} samples ({worst / SR * 1000:.2f} ms)")

    # loudness and true peak on the encoded file
    rep = ff("-i", a.video, "-vn", "-af", "ebur128=peak=true", "-f", "null", "-").stderr
    I = float(re.findall(r"I:\s+(-?[\d.]+) LUFS", rep)[-1]); P = float(re.findall(r"Peak:\s+(-?[\d.]+) dBFS", rep)[-1])
    add("loudness", abs(I - a.target) <= 1.0, f"integrated {I:.1f} LUFS, target {a.target}")
    add("true peak", P <= -1.0, f"{P:.1f} dBTP (limit -1.0)")

    # picture: one motion curve per distinct region
    curves = {}
    voice = [(e["at"], e["at"] + file_dur(e["file"])) for e in events if e.get("bus") == "fg" and "file" in e and "at" in e]
    n = max(1, int(0.002 * SR)); env = np.sqrt(np.convolve(final * final, np.ones(n) / n, mode="same"))
    for k, e in enumerate(events):
        cue = e.get("cue", (e["frame"] / e.get("fps", fps)) if "frame" in e else None)
        if cue is None: continue
        name = e.get("id") or pathlib.Path(e.get("file", f"cue{k}")).stem
        hero = bool(e.get("hero"))
        if e.get("visual"):
            roi = tuple(e["roi"]) if e.get("roi") else None
            if roi and (W, H) != (1920, 1080):
                sx, sy = W / 1920, H / 1080; roi = (int(roi[0] * sx), int(roi[1] * sy), int(roi[2] * sx), int(roi[3] * sy))
            if roi not in curves: curves[roi] = motion_curve(a.video, roi)
            f = int(round(cue * fps))
            ok, why = picture_check(e["visual"], f, curves[roi])
            add(f"picture {name}", ok, f"{e['visual']} at {cue:.3f} s (frame {f}){' in ' + str(list(roi)) if roi else ''}: {why}", hard=hero)
        if e.get("align") == "peak" and "file" in e:
            if any(v0 - 0.05 <= cue <= v1 + 0.05 for v0, v1 in voice):
                add(f"sync {name}", True, "skipped: a voice event overlaps the cue", hard=False); continue
            p = int(cue * SR); lo, hi = max(0, p - int(0.06 * SR)), min(len(env), p + int(0.06 * SR))
            found = lo + int(np.argmax(env[lo:hi])); err = abs(found - p) / SR * fps
            add(f"sync {name}", err <= (1 if hero else 2), f"envelope peak {err:.2f} frames from the cue", hard=hero)

    # silence
    ok_spans = [tuple(map(float, s.split("-"))) for s in a.silence_ok.split(",") if s]
    err = ff("-i", a.video, "-vn", "-af", "silencedetect=noise=-50dB:d=0.5", "-f", "null", "-").stderr
    st = [float(x) for x in re.findall(r"silence_start: (-?[\d.]+)", err)]
    en = [float(x) for x in re.findall(r"silence_end: ([\d.]+)", err)] + [len(final) / SR]
    bad = [(round(s, 2), round(e, 2)) for s, e in zip(st, en) if not any(s >= a0 - 0.1 and e <= a1 + 0.1 for a0, a1 in ok_spans)]
    add("silence", not bad, f"unplanned silence: {bad}" if bad else "none")

    fails = [r for r in res if r["status"] == "FAIL"]; warns = [r for r in res if r["status"] == "warn"]
    out = pathlib.Path(a.video).with_suffix(".soundqa.json")
    out.write_text(json.dumps(dict(passed=not fails, fps=fps, results=res), indent=1, ensure_ascii=False))
    for r in res: print(f"{r['status']:4s}  {r['check']:28s} {r['detail']}")
    print(f"\n{'PASSED' if not fails else 'FAILED'}: {len(fails)} failed, {len(warns)} warnings -> {out.name}")
    sys.exit(1 if fails else 0)


if __name__ == "__main__":
    main()
