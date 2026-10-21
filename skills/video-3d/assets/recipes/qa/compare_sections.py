#!/usr/bin/env python3
"""Compare two renders of the same film section by section (video-3d determinism protocol, qa-3d step 3).

usage: python3 compare_sections.py A B --cuts 0,4.5,8.5,... [--names lathe,glass,...] [--fps 30] [--psnr-floor 48]

A and B are each one of:
  - a framemd5 file (ffmpeg -i film.mp4 -f framemd5 - > film.framemd5)
  - a video file (decoded to framemd5 with ffmpeg)
  - a directory of PNG frames (hyperframes render --format png-sequence, or ffmpeg-extracted)
--cuts are the section START times in seconds (the first is usually 0).

Hash inputs: differing frames per section.
PNG directories: differing frames, max level difference and min PSNR per section. Use PNGs to prove a section
UNCHANGED between two versions of a film: an edit changes the ENCODED frames before it (x264 look-ahead /
mbtree; the data reel: 44 untouched frames before an edited section differed at ~50 dB), so MP4 checksums
across versions mislead. Without PNGs, a section whose min PSNR stays above --psnr-floor (48 dB) counts as
unchanged. Within one version, worker renders of WebGL-only output are bit-identical; DOM over WebGL may differ
by <= 2 levels on a few hundred pixels. Standard library + numpy + Pillow (PNG mode only).
"""
import argparse
import math
import pathlib
import subprocess


def hashes(p):
    p = pathlib.Path(p)
    if p.suffix in (".framemd5", ".md5"):
        lines = p.read_text().splitlines()
    else:
        out = subprocess.run(["ffmpeg", "-v", "error", "-i", str(p), "-map", "0:v:0", "-f", "framemd5", "-"],
                             capture_output=True, text=True, check=True).stdout
        lines = out.splitlines()
    return [l.split(",")[-1].strip() for l in lines if l.strip() and not l.startswith("#")]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("a"); ap.add_argument("b")
    ap.add_argument("--cuts", required=True, help="section start times in seconds, comma separated")
    ap.add_argument("--names", default="")
    ap.add_argument("--fps", type=float, default=30)
    ap.add_argument("--psnr-floor", type=float, default=48.0)
    o = ap.parse_args()
    starts = [round(float(c) * o.fps) for c in o.cuts.split(",") if c.strip()]
    names = [n for n in o.names.split(",") if n] or [f"s{i + 1}" for i in range(len(starts))]
    png = pathlib.Path(o.a).is_dir() and pathlib.Path(o.b).is_dir()
    if png:
        import numpy as np
        from PIL import Image
        A = sorted(pathlib.Path(o.a).glob("*.png")); B = sorted(pathlib.Path(o.b).glob("*.png"))
        n = min(len(A), len(B))
        print(f"PNG frames {len(A)} vs {len(B)}")
    else:
        A, B = hashes(o.a), hashes(o.b)
        n = min(len(A), len(B))
        print(f"decoded frames {len(A)} vs {len(B)}; identical overall {sum(x == y for x, y in zip(A, B))}/{n}")
    bounds = starts + [n]
    bad_sections = 0
    for k, name in enumerate(names[: len(starts)]):
        f0, f1 = bounds[k], min(bounds[k + 1], n)
        if not png:
            diff = [i for i in range(f0, f1) if A[i] != B[i]]
            if diff: bad_sections += 1
            print(f"{name:14s} frames {f0:5d}-{f1 - 1:5d}: {len(diff):4d} differ" + (f"  first {diff[:6]}" if diff else ""))
            continue
        ndiff, maxd, minpsnr = 0, 0, math.inf
        for i in range(f0, f1):
            x = np.asarray(Image.open(A[i]).convert("RGB"), dtype=np.int16)
            y = np.asarray(Image.open(B[i]).convert("RGB"), dtype=np.int16)
            d = np.abs(x - y)
            m = int(d.max())
            if m:
                ndiff += 1; maxd = max(maxd, m)
                mse = float((d.astype(np.float64) ** 2).mean())
                minpsnr = min(minpsnr, 10 * math.log10(255 ** 2 / mse))
        verdict = "identical" if not ndiff else ("unchanged (PSNR above floor)" if minpsnr > o.psnr_floor else "CHANGED")
        if verdict == "CHANGED": bad_sections += 1
        ps = "inf" if minpsnr == math.inf else f"{minpsnr:.1f}"
        print(f"{name:14s} frames {f0:5d}-{f1 - 1:5d}: {ndiff:4d} differ, max {maxd:3d} levels, min PSNR {ps:>5s} dB  {verdict}")
    raise SystemExit(1 if bad_sections else 0)


if __name__ == "__main__":
    main()
