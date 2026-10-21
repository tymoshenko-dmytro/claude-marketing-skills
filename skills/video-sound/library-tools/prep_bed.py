#!/usr/bin/env python3
"""Cut a card-length bed out of a longer track, on the film's tempo.

    python3 tools/prep_bed.py source.mp3 out.wav --from 46.5 --secs 18 [--from-bpm 114.8] [--bpm 120]

Stdlib + ffmpeg. --from-bpm stretches the track onto the project grid (ffmpeg atempo, pitch kept).
It is not about the voice, which is not rhythmic: it is about the percussive effects. A swell
or a chime placed on the beats of the film's grid falls between the bed's own hits when the bed
runs at its own tempo, and that is heard as slop. A stretch under ~10% is inaudible.

The chain: grab --secs x stretch + 0.5 s from --from, stretch, fade in 0.35 s, fade out over the
last 0.9 s, loudnorm to --lufs (-24) with -6 dBTP, 48 kHz mono.

The two external cuts in the catalogue were made with it (re-made from the source tracks, the
output matched the original cuts sample for sample):
    prep_bed.py music/external/simple-explainer.mp3 music/external/bed-clean-120.wav --from 0.5 --secs 18
    prep_bed.py music/external/info-overviews.mp3  music/external/bed-long-120.wav --from 46.5 --secs 18 --from-bpm 114.8
"""
import argparse, subprocess

ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
ap.add_argument("src"); ap.add_argument("out")
ap.add_argument("--from", dest="start", type=float, required=True, help="start in the source, s")
ap.add_argument("--secs", type=float, default=18.0, help="length of the bed, s")
ap.add_argument("--from-bpm", type=float, default=None, help="the source's tempo; stretch it to --bpm")
ap.add_argument("--bpm", type=float, default=120.0, help="the film's grid")
ap.add_argument("--lufs", type=float, default=-24.0)
a = ap.parse_args()

ratio = (a.bpm / a.from_bpm) if a.from_bpm else 1.0
grab = a.secs * ratio + 0.5
chain = []
if abs(ratio - 1.0) > 0.002:
    chain.append(f"atempo={ratio:.5f}")
chain += [f"afade=t=in:d=0.35",
          f"afade=t=out:st={a.secs - 0.9:.3f}:d=0.9",
          f"loudnorm=I={a.lufs}:TP=-6:LRA=7"]
subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-ss", str(a.start),
    "-t", f"{grab:.3f}", "-i", a.src, "-af", ",".join(chain),
    "-t", str(a.secs), "-ar", "48000", "-ac", "1", a.out, "-y"], check=True)
d = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
    "-of", "csv=p=0", a.out], capture_output=True, text=True).stdout.strip()
print(f"  {a.out}  {float(d):.2f}s  stretch x{ratio:.4f}"
      + (f"  ({a.from_bpm} -> {a.bpm} BPM)" if a.from_bpm else "  (already on grid)"))
