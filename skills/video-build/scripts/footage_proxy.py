#!/usr/bin/env python3
"""Real footage -> HyperFrames <video> windows with frame-exact maths (stdlib + ffmpeg only).

Takes one clip and an in/out range in the clip's own seconds, and prints:
  - a 30 fps CFR proxy of the range (default), resampled exactly the way HyperFrames
    0.8.157 resamples a <video> at render time, so proxy frame k == rendered frame k;
  - the scene cuts re-detected on the file that will be rendered (proxy frames, or the
    raw clip's own frame pts with --raw);
  - the <video> window for the range placed at --at (or one window per shot with --split),
    every time written as an exact double (frame / fps, shortest round-trip), plus each
    cut's composition time for timing anything else to it. Never round these.

Why (measured on hyperframes 0.8.157, references/hyperframes-gotchas.md "Real footage"):
times rounded to 4 or 2 decimals give black frames and duplicated first frames at window
edges, and an in-point rounded onto the 30 fps grid of a 24 fps clip shows one frame of
the previous shot. The engine already resamples 24/25/29.97/VFR footage correctly, so
the proxy is optional: use it for VFR or sparse-keyframe footage, long footage cut into
many windows, or whenever you want frame numbers that equal render frames.

usage:
  footage_proxy.py CLIP --in 3.5 --out 13 [--at 2] [-o assets/clip-p.mp4] [--raw] [--split]
                   [--min-shot 8] [--fps 30] [--threshold 0.12] [--src-attr assets/clip-p.mp4]
                   [--json out.json]
"""
import argparse
import json
import math
import os
import re
import subprocess
import sys
from fractions import Fraction


def run(cmd, **kw):
    return subprocess.run(cmd, capture_output=True, text=True, **kw)


def probe(path):
    out = run(["ffprobe", "-v", "error", "-show_entries",
               "stream=index,codec_type,r_frame_rate,avg_frame_rate,start_time:format=duration",
               "-of", "json", path], check=True).stdout
    j = json.loads(out)
    v = next(s for s in j["streams"] if s["codec_type"] == "video")
    fr = lambda s: float(Fraction(s)) if s and s != "0/0" else 0.0
    r, avg = fr(v["r_frame_rate"]), fr(v["avg_frame_rate"])
    keys = run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-skip_frame", "nokey",
                "-show_entries", "frame=pts_time", "-of", "csv=p=0", path]).stdout.split()
    keys = [float(k.split(",")[0]) for k in keys if k.split(",")[0]]
    gaps = [b - a for a, b in zip(keys, keys[1:])] or [float(j["format"]["duration"])]
    return {
        "r_fps": r, "avg_fps": avg,
        # the engine's own rule: r_frame_rate and avg_frame_rate differ by more than 10%
        "vfr": r > 0 and avg > 0 and abs(r - avg) / max(r, avg) > 0.1,
        "has_audio": any(s["codec_type"] == "audio" for s in j["streams"]),
        "duration": float(j["format"]["duration"]),
        "start_time": float(v.get("start_time") or 0),
        "max_keyframe_gap": max(gaps),
    }


def frame_pts(path, t0, t1):
    """Exact pts (pts x time_base, not ffprobe's 6-decimal pts_time) of the clip's own
    frames in [t0 - 1 s, t1 + 1 s]."""
    tb = Fraction(run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
                       "stream=time_base", "-of", "csv=p=0", path], check=True).stdout.strip())
    out = run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-read_intervals",
               f"{max(0, t0 - 1)}%{t1 + 1}", "-show_entries", "frame=pts", "-of", "csv=p=0",
               path], check=True).stdout.split()
    return sorted(float(int(p.split(",")[0]) * tb) for p in out if p.split(",")[0] not in ("", "N/A"))


def scene_cuts(path, threshold, ss=None, dur=None):
    cmd = ["ffmpeg", "-hide_banner", "-nostdin"]
    if ss is not None:
        cmd += ["-copyts", "-ss", repr(ss), "-t", repr(dur)]
    cmd += ["-i", path, "-an", "-vf", f"select='gt(scene,{threshold})',showinfo", "-f", "null", "-"]
    err = run(cmd).stderr
    return [float(m) for m in re.findall(r"pts_time:([\d.]+)", err)]


def make_proxy(clip, out, t_in, frames, fps, has_audio):
    dur = frames / fps
    # Same resampling as the engine's frame extraction: keep the frame on screen at t_in
    # (-noaccurate_seek), nudge one tick so frames on a grid boundary do not round up,
    # take the frame on screen at each k/fps (round=up), clone-pad the tail, exact count.
    vf = (f"[0:v]settb=intb/2,setpts=PTS-lte(TB\\,0.001),fps={fps}:start_time=0:round=up,"
          f"tpad=stop_mode=clone:stop_duration=2,trim=end_frame={frames},setpts=PTS-STARTPTS[v]")
    cmd = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-nostdin", "-y",
           "-noaccurate_seek", "-ss", repr(t_in), "-i", clip]
    maps = ["-map", "[v]"]
    if has_audio:   # audio: an accurate seek of its own, cut to the same length
        cmd += ["-ss", repr(t_in), "-t", repr(dur), "-i", clip]
        maps += ["-map", "1:a:0", "-c:a", "aac", "-b:a", "192k"]
    cmd += ["-filter_complex", vf, *maps, "-frames:v", str(frames), "-r", str(fps), "-fps_mode", "cfr",
            "-c:v", "libx264", "-preset", "fast", "-crf", "14", "-pix_fmt", "yuv420p",
            "-g", str(fps), "-keyint_min", str(fps), "-movflags", "+faststart", out]
    r = run(cmd)
    if r.returncode != 0:
        sys.exit(f"ffmpeg failed: {r.stderr[-800:]}")
    n = run(["ffprobe", "-v", "error", "-count_frames", "-select_streams", "v:0", "-show_entries",
             "stream=nb_read_frames", "-of", "csv=p=0", out], check=True).stdout.strip()
    if int(n) != frames:
        sys.exit(f"proxy has {n} frames, expected {frames}")


def t(frame, fps):
    """An exact double for a frame boundary: one division, shortest round-trip repr."""
    return repr(frame / fps)


def span(f0, f1, fps):
    """data-duration such that start + duration == the next window's start in doubles.
    (f1 - f0) / fps can overshoot by one ulp: the render tolerates it, but lint then
    reports overlapping audible windows on one track (duplicate_audio_track)."""
    a, b = f0 / fps, f1 / fps
    d = (f1 - f0) / fps
    for _ in range(8):
        s = a + d
        if s == b:
            break
        d = math.nextafter(d, math.inf if s < b else -math.inf)
    return repr(d)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("clip")
    ap.add_argument("--in", dest="t_in", type=float, required=True, help="in-point, clip seconds")
    ap.add_argument("--out", dest="t_out", type=float, required=True, help="out-point, clip seconds")
    ap.add_argument("--at", type=float, default=0.0, help="composition time of the first frame (snapped to the frame grid)")
    ap.add_argument("--fps", type=int, default=30, help="render fps (default 30)")
    ap.add_argument("-o", "--proxy", help="proxy path (default: <clip>-p<fps>-<in>-<out>.mp4 next to the clip)")
    ap.add_argument("--raw", action="store_true", help="no proxy: windows on the raw clip, in-points at its own frame pts")
    ap.add_argument("--threshold", type=float, default=0.12, help="scene-cut threshold (default 0.12)")
    ap.add_argument("--src-attr", help="src= to write in the snippet (default: the file path as given/made)")
    ap.add_argument("--split", action="store_true", help="one window per shot (default: one window for the range)")
    ap.add_argument("--min-shot", type=int, default=8, help="with --split, never make a shot shorter than this many frames (default 8)")
    ap.add_argument("--id", default="shot", help="id prefix for the <video> elements")
    ap.add_argument("--json", help="also write the result here")
    a = ap.parse_args()

    fps = a.fps
    info = probe(a.clip)
    t_in, t_out = a.t_in, min(a.t_out, info["duration"])
    if not 0 <= t_in < t_out:
        sys.exit("need 0 <= --in < --out")
    frames = round((t_out - t_in) * fps)
    at_f = round(a.at * fps)
    notes = []
    if info["vfr"]:
        notes.append("VFR source: the engine re-normalises it on every render; prefer the proxy")
    if info["max_keyframe_gap"] > 2:
        notes.append(f"sparse keyframes (max gap {info['max_keyframe_gap']:.1f} s): render warns and the live player seeks slowly; prefer the proxy")
    if abs(at_f / fps - a.at) > 1e-9:
        notes.append(f"--at {a.at} snapped to frame {at_f} ({t(at_f, fps)} s)")

    if a.raw:
        src = a.clip
        pts = frame_pts(a.clip, t_in, t_out)
        # cuts as the clip's own frame pts (exact), inside (in, out)
        cut_pts = []
        for c in scene_cuts(a.clip, a.threshold, ss=t_in, dur=t_out - t_in):
            p = min(pts, key=lambda x: abs(x - c))
            if t_in < p < t_out and p not in cut_pts:
                cut_pts.append(p)
        # the window frame where each cut first shows: the engine shows the frame on screen
        # at in + k/fps, so the first k with in + k/fps >= pts
        cuts = [(math.ceil((p - t_in) * fps - 1e-6), repr(p)) for p in cut_pts]
    else:
        src = a.proxy or os.path.splitext(a.clip)[0] + f"-p{fps}-{t_in:g}-{t_out:g}.mp4"
        make_proxy(a.clip, src, t_in, frames, fps, info["has_audio"])
        cuts = [(f, t(f, fps)) for f in sorted({round(p * fps) for p in scene_cuts(src, a.threshold)} - {0})]

    # a shot shorter than --min-shot frames is a flash frame, not a shot: merge it forward
    kept, merged = [], []
    for f, m in cuts:
        if f - (kept[-1][0] if kept else 0) < a.min_shot or frames - f < a.min_shot:
            merged.append(f)
        else:
            kept.append((f, m))
    if merged:
        notes.append(f"cuts closer than {a.min_shot} frames to a neighbour were not split at: {merged}")
    if len(cuts) > max(4, frames / fps / 2):
        notes.append(f"{len(cuts)} cuts in {frames / fps:.1f} s: screen recordings trip the 0.12 threshold on UI changes; try --threshold 0.3")
    first_media = repr(t_in) if a.raw else t(0, fps)
    if a.split:
        bounds = [(0, first_media)] + kept
        shots = [{"f0": f0, "f1": (bounds[k + 1][0] if k + 1 < len(bounds) else frames), "media_start": m}
                 for k, (f0, m) in enumerate(bounds)]
    else:
        shots = [{"f0": 0, "f1": frames, "media_start": first_media}]
    key = "clip_pts" if a.raw else "proxy_time"
    cuts_out = [{"window_frame": f, "composition_time": t(at_f + f, fps), key: m, "split": (f, m) in kept and a.split}
                for f, m in cuts]

    windows = []
    for k, s in enumerate(shots):
        windows.append({
            "id": f"{a.id}{k}",
            "data-start": t(at_f + s["f0"], fps),
            "data-duration": span(at_f + s["f0"], at_f + s["f1"], fps),
            "data-media-start": s["media_start"],
            "frames": [at_f + s["f0"], at_f + s["f1"]],
        })
    attr_src = a.src_attr or src
    sound = ' data-has-audio="true"' if info["has_audio"] else " muted"
    snippet = "\n".join(
        f'<video id="{w["id"]}" src="{attr_src}" data-start="{w["data-start"]}" '
        f'data-duration="{w["data-duration"]}" data-media-start="{w["data-media-start"]}" '
        f'data-track-index="0"{sound} playsinline></video>' for w in windows)
    if info["has_audio"]:
        notes.append('data-has-audio="true" plays the clip\'s own sound; use "muted" to drop it (data-has-audio on a file without audio fails the render)')
    result = {
        "file": src, "fps": fps, "frames": frames, "seconds": t(frames, fps),
        "in": t_in, "out": t_out, "at_frame": at_f,
        "source": info, "cuts": cuts_out, "windows": windows, "notes": notes, "html": snippet,
    }
    if a.json:
        with open(a.json, "w") as f:
            json.dump(result, f, indent=2)
    print(json.dumps({k: v for k, v in result.items() if k != "html"}, indent=2))
    print("\n" + snippet)


if __name__ == "__main__":
    main()
