#!/usr/bin/env python3
"""Blank / frozen output check for a rendered film (video-3d qa-3d step 4).

usage: python3 blank_check.py film.mp4 [--cuts 0,4.5,8.5,...] [--min-step 0.05] [--freeze 15]

Why: a rejected build hold does NOT fail a HyperFrames render (0.8.156: exit 0, also with --no-best-effort) -
the film comes out blank; an exception inside the hf-seek handler leaves the previous frame on the canvas while
DOM labels move on. The renderAt try/catch clears to MAGENTA, so it is visible here.
Reports per section (cuts = section start times): mean luma, the share of near-black frames, magenta frames,
and the longest run of frames whose mean frame-to-frame change is below --min-step (gray levels, 480x270).
A run longer than --freeze frames outside a deliberate still is a frozen hold. ffmpeg + numpy.
"""
import argparse
import subprocess

import numpy as np


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("video")
    ap.add_argument("--cuts", default="0")
    ap.add_argument("--fps", type=float, default=30)
    ap.add_argument("--min-step", type=float, default=0.05)
    ap.add_argument("--freeze", type=int, default=15)
    o = ap.parse_args()
    W, H = 480, 270
    proc = subprocess.Popen(["ffmpeg", "-v", "error", "-i", o.video, "-vf", f"scale={W}:{H}:flags=area", "-f", "rawvideo",
                             "-pix_fmt", "rgb24", "-"], stdout=subprocess.PIPE)
    wts = np.array([0.2126, 0.7152, 0.0722], np.float32)
    mean, step, magenta, prev = [], [], [], None
    while True:                                      # stream: one frame in memory at a time
        buf = proc.stdout.read(W * H * 3)
        if len(buf) < W * H * 3: break
        f = np.frombuffer(buf, np.uint8).reshape(H, W, 3)
        l = f.astype(np.float32) @ wts
        mean.append(float(l.mean()))
        step.append(np.inf if prev is None else float(np.abs(l - prev).mean()))
        magenta.append(bool(((f[..., 0] > 200) & (f[..., 2] > 200) & (f[..., 1] < 60)).mean() > 0.5))
        prev = l
    proc.wait()
    mean, step, magenta = np.array(mean), np.array(step), np.array(magenta)
    n = len(mean)
    starts = [round(float(c) * o.fps) for c in o.cuts.split(",") if c.strip()] + [n]
    bad = 0
    print(f"{n} frames")
    for k in range(len(starts) - 1):
        f0, f1 = starts[k], min(starts[k + 1], n)
        if f0 >= f1: continue
        run = best = 0
        for i in range(f0 + 1, f1):
            run = run + 1 if step[i] < o.min_step else 0
            best = max(best, run)
        dark = float((mean[f0:f1] < 2).mean())
        mag = int(magenta[f0:f1].sum())
        flag = []
        if dark > 0.9: flag.append("BLANK")
        if mag: flag.append(f"MAGENTA x{mag} (renderAt error)")
        if best >= o.freeze: flag.append(f"FROZEN {best} frames")
        bad += bool(flag)
        print(f"section {k + 1:2d} frames {f0:5d}-{f1 - 1:5d}: mean luma {mean[f0:f1].mean():6.1f}, near-black {dark * 100:5.1f}%, "
              f"min step {step[f0 + 1:f1].min() if f1 - f0 > 1 else 0:6.3f}, longest still run {best:3d}  {' '.join(flag)}")
    raise SystemExit(1 if bad else 0)


if __name__ == "__main__":
    main()
