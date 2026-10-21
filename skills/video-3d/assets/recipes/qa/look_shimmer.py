#!/usr/bin/env python3
"""Exact per-cell shimmer for grid looks (pixel art, dither, halftone), a companion to ascii_shimmer.py.

usage: python3 look_shimmer.py FRAMES_DIR --cell 6x6 [--fps 30] [--spans 0.1-2.6,2.75-3.95] [--offset 0x0]

ascii_shimmer.py signs a cell by its ink mask (luma above a threshold), which suits two-tone glyphs but
misses changes between two dark (or two light) colours. Here a cell's signature is a hash of ALL its RGB
bytes, so any change counts:
  change : share of cells whose bytes changed since the previous frame
  blip   : share of cells with frame n != n-1 while n-1 == n+1 exactly (A-B-A: a one-frame flicker or crawl)
  revisit: share of cells that return to the exact bytes of frame n-2 at n (A-B-A over any middle) - a
           crawl indicator for pixel art (edges stepping back and forth while the camera moves smoothly)
--offset shifts the grid (e.g. halftone dots are centred on k*radius). Standard library + numpy + Pillow.
"""
import argparse
import pathlib

import numpy as np
from PIL import Image


def cell_hash(path, cw, ch, ox, oy, weights):
    a = np.asarray(Image.open(path).convert("RGB"), dtype=np.uint32)[oy:, ox:]
    h, w = a.shape[:2]
    rows, cols = h // ch, w // cw
    a = a[: rows * ch, : cols * cw].reshape(rows, ch, cols, cw, 3).transpose(0, 2, 1, 3, 4).reshape(rows, cols, -1)
    return (a * weights[None, None, : a.shape[2]]).sum(axis=2, dtype=np.uint64)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("frames")
    ap.add_argument("--cell", default="6x6")
    ap.add_argument("--offset", default="0x0")
    ap.add_argument("--fps", type=float, default=30)
    ap.add_argument("--spans", default="")
    a = ap.parse_args()
    cw, ch = (int(v) for v in a.cell.split("x"))
    ox, oy = (int(v) for v in a.offset.split("x"))
    weights = np.random.default_rng(7).integers(1, 2**31 - 1, size=cw * ch * 3, dtype=np.uint64)
    files = sorted(pathlib.Path(a.frames).glob("*.png"))
    sig = [cell_hash(f, cw, ch, ox, oy, weights) for f in files]
    n = len(sig)
    change, blip, rev = np.zeros(n), np.zeros(n), np.zeros(n)
    for i in range(1, n):
        change[i] = (sig[i] != sig[i - 1]).mean()
    for i in range(1, n - 1):
        blip[i] = ((sig[i] != sig[i - 1]) & (sig[i - 1] == sig[i + 1])).mean()
    for i in range(2, n):
        rev[i] = ((sig[i] == sig[i - 2]) & (sig[i - 1] != sig[i])).mean()
    t = np.arange(n) / a.fps
    print(f"{n} frames, exact cells {cw}x{ch} offset {ox},{oy}")
    spans = [s for s in a.spans.split(",") if s] or [f"0-{n / a.fps}"]
    for span in spans:
        lo, hi = (float(v) for v in span.split("-"))
        m = (t >= lo) & (t < hi)
        m[:2] = False; m[-1] = False
        print(f"{lo:4.2f}-{hi:4.2f}s: change {change[m].mean()*100:6.2f}%   blip {blip[m].mean()*100:6.3f}%   "
              f"revisit {rev[m].mean()*100:6.3f}%   blip/change {blip[m].sum()/max(1e-9, change[m].sum())*100:5.2f}%")


if __name__ == "__main__":
    main()
