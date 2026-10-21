#!/usr/bin/env python3
"""Shimmer QA for an ASCII-cinema render: how glyphs change between frames, cell by cell.

usage: python3 ascii_shimmer.py FRAMES_DIR [--cell 12x24] [--fps 30] [--spans 0-7.2,7.2-11]
                                [--compare OTHER_DIR]

FRAMES_DIR holds a PNG sequence (hyperframes render --format png-sequence, or ffmpeg-extracted
frames). Every cell gets a signature per frame: its ink mask (luma above a threshold), packed.
  change : share of cells whose glyph changed since the previous frame (motion + shimmer)
  blip   : share of cells where frame n differs from BOTH neighbours while n-1 == n+1 (A-B-A, a
           one-frame flicker). Fast-moving texture also makes some; compare spans and variants.
  jitter : sum |L(n+1) - 2L(n) + L(n-1)| / sum |L(n+1) - L(n-1)| over all pixels (luma). Smooth
           motion keeps it low; popping and flicker push it up (the logo film's measure).
With --compare, also the share of frames whose pixels differ between two renders (determinism).
Standard library + numpy + Pillow.
"""
import argparse
import pathlib

import numpy as np
from PIL import Image


def load(path):
    a = np.asarray(Image.open(path).convert("RGB"), dtype=np.float32)
    return 0.2126 * a[..., 0] + 0.7152 * a[..., 1] + 0.0722 * a[..., 2]


def signatures(luma, cw, ch, thr):
    h, w = luma.shape
    rows, cols = h // ch, w // cw
    ink = (luma[: rows * ch, : cols * cw] > thr).reshape(rows, ch, cols, cw).transpose(0, 2, 1, 3)
    packed = np.packbits(ink.reshape(rows, cols, ch * cw), axis=2)
    return packed, ink


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("frames")
    ap.add_argument("--cell", default="12x24")
    ap.add_argument("--fps", type=float, default=30)
    ap.add_argument("--thr", type=float, default=60, help="luma threshold for ink (0..255)")
    ap.add_argument("--spans", default="", help="time spans to summarise, e.g. 0-7.2,7.2-11")
    ap.add_argument("--compare", default="")
    a = ap.parse_args()
    cw, ch = (int(v) for v in a.cell.split("x"))
    files = sorted(pathlib.Path(a.frames).glob("*.png"))
    sig, d1, d2 = [], [], []
    win = []
    for f in files:
        L = load(f)
        s, _ = signatures(L, cw, ch, a.thr)
        sig.append(s)
        win = (win + [L])[-3:]
        if len(win) == 3:
            d1.append(np.abs(win[2] - win[0]).sum() / 2)
            d2.append(np.abs(win[2] - 2 * win[1] + win[0]).sum())
        else:
            d1.append(0.0); d2.append(0.0)
    n = len(sig)
    # d1/d2 index k describes frame k-1 (the middle of the window); shift so index = middle frame
    d1 = np.array(d1[1:] + [0.0]); d2 = np.array(d2[1:] + [0.0])
    differs = lambda x, y: np.any(x != y, axis=2)
    change = np.zeros(n)
    blip = np.zeros(n)
    for i in range(1, n):
        change[i] = differs(sig[i], sig[i - 1]).mean()
    for i in range(1, n - 1):
        same_outer = ~differs(sig[i - 1], sig[i + 1])
        blip[i] = (differs(sig[i], sig[i - 1]) & same_outer).mean()
    t = np.arange(n) / a.fps
    print(f"{n} frames, cells {cw}x{ch}, threshold {a.thr}")
    print(f"all     : change {change[1:].mean()*100:6.2f}%   blip {blip[1:-1].mean()*100:6.3f}%   "
          f"blip/change {blip[1:-1].sum()/max(1e-9, change[1:].sum())*100:5.2f}%   jitter {d2[1:-1].sum()/max(1e-9, d1[1:-1].sum()):.3f}")
    for span in filter(None, a.spans.split(",")):
        lo, hi = (float(v) for v in span.split("-"))
        m = (t >= lo) & (t < hi)
        m[0] = m[-1] = False
        print(f"{lo:4.1f}-{hi:4.1f}s: change {change[m].mean()*100:6.2f}%   blip {blip[m].mean()*100:6.3f}%   "
              f"blip/change {blip[m].sum()/max(1e-9, change[m].sum())*100:5.2f}%   jitter {d2[m].sum()/max(1e-9, d1[m].sum()):.3f}")
    worst = np.argsort(blip)[-5:][::-1]
    print("worst blip frames:", ", ".join(f"{i} ({t[i]:.2f}s) {blip[i]*100:.2f}%" for i in worst))
    if a.compare:
        other = sorted(pathlib.Path(a.compare).glob("*.png"))
        diff = sum(1 for x, y in zip(files, other)
                   if not np.array_equal(np.asarray(Image.open(x)), np.asarray(Image.open(y))))
        print(f"compare: {diff} of {min(len(files), len(other))} frames differ")


if __name__ == "__main__":
    main()
