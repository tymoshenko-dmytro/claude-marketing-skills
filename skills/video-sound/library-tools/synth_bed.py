#!/usr/bin/env python3
"""A music bed, synthesised. No licence, no vendor, exact tempo.

    python3 tools/synth_bed.py out.wav [--bpm 110] [--bars 8] [--key 0] [--mood calm|warm|drive]

Needs numpy and ffmpeg (the library venv has numpy). A scratch bed: use it to build and time a
card before the real music is in; swapping the final track in is one line in the timeline plus
a re-mix, because the bed sits on its own bus as its own file. A bed for a card does not need to
be music - it needs to be a floor under a voice at a known tempo.

Four layers, all from sine and noise: a sub kick on the beat, a soft pad on the chord, a closed
hat on the offbeat, and one low sine holding the root. Nothing here is a melody, on purpose - a
hook under a voiceover competes with it. Output is levelled to -24 LUFS, 48 kHz mono.
music/own/synth-calm|warm|drive.wav in the library are this script at 110 BPM, 8 bars.
"""
import argparse, numpy as np, subprocess, sys, pathlib

ap = argparse.ArgumentParser()
ap.add_argument("out"); ap.add_argument("--bpm", type=int, default=110)
ap.add_argument("--bars", type=int, default=8); ap.add_argument("--key", type=int, default=0)
ap.add_argument("--mood", default="calm", choices=["calm", "warm", "drive"])
a = ap.parse_args()

SR = 48000
beat = 60.0 / a.bpm
total = beat * 4 * a.bars
n = int(total * SR)
t = np.arange(n) / SR
out = np.zeros(n)

def at(sec, buf, gain=1.0):
    i = int(sec * SR)
    m = min(len(buf), n - i)
    if m > 0: out[i:i+m] += buf[:m] * gain

def env(dur, atk, dec, curve=2.0):
    k = int(dur * SR)
    e = np.ones(k)
    ai, di = int(atk * SR), int(dec * SR)
    if ai: e[:ai] = np.linspace(0, 1, ai)
    if di: e[-di:] = np.linspace(1, 0, di) ** curve
    return e

def note(hz, dur, atk=0.01, dec=None, harm=(1.0, 0.28, 0.12)):
    dec = dur * 0.9 if dec is None else dec
    k = int(dur * SR); x = np.arange(k) / SR
    s = sum(g * np.sin(2*np.pi*hz*(i+1)*x) for i, g in enumerate(harm))
    return s * env(dur, atk, dec)

def kick(dur=0.20):
    k = int(dur*SR); x = np.arange(k)/SR
    f = 110 * np.exp(-x*28) + 44                      # a pitch drop, not a click
    return np.sin(2*np.pi*np.cumsum(f)/SR) * env(dur, 0.001, dur*0.85, 3.0)

def hat(dur=0.045):
    k = int(dur*SR)
    rng = np.random.default_rng(7)                     # fixed, so renders repeat
    return rng.standard_normal(k) * env(dur, 0.001, dur*0.9, 4.0) * 0.5

# minor-seventh voicings: enough colour to sit under a voice, no tune of their own
ROOT = 55.0 * 2 ** (a.key / 12)                        # A1
CHORDS = {"calm":  [[0, 3, 7, 10], [0, 3, 7, 10], [-2, 3, 5, 10], [-2, 3, 5, 10]],
          "warm":  [[0, 4, 7, 11], [-3, 4, 7, 9],  [-5, 2, 7, 11], [-3, 4, 7, 9]],
          "drive": [[0, 3, 7, 10], [5, 8, 12, 15], [3, 7, 10, 14], [-2, 3, 7, 10]]}[a.mood]

for b in range(a.bars):
    bar_t = b * beat * 4
    ch = CHORDS[b % len(CHORDS)]
    for st in ch:
        hz = ROOT * 2 ** (st / 12) * 4                 # up two octaves for the pad
        at(bar_t, note(hz, beat*4, atk=0.35, dec=beat*2.2, harm=(1.0, 0.14, 0.05)), 0.052)
    at(bar_t, note(ROOT * 2 ** (ch[0]/12), beat*4, atk=0.20, dec=beat*2.0,
                   harm=(1.0, 0.20)), 0.10)            # the low root
    for q in range(4):
        bt = bar_t + q * beat
        if a.mood == "drive" or q in (0, 2): at(bt, kick(), 0.34)
        at(bt + beat/2, hat(), 0.055)
        if a.mood == "drive": at(bt + beat*0.75, hat(), 0.030)

out /= max(1e-9, np.abs(out).max())
out *= 0.72
fade = int(0.9 * SR)
out[-fade:] *= np.linspace(1, 0, fade) ** 1.4
out[:int(0.05*SR)] *= np.linspace(0, 1, int(0.05*SR))

pathlib.Path(a.out).parent.mkdir(parents=True, exist_ok=True)
p = subprocess.run(["ffmpeg","-hide_banner","-loglevel","error","-f","f32le","-ar",str(SR),
    "-ac","1","-i","pipe:0","-af",f"loudnorm=I=-24:TP=-6:LRA=7","-ar","48000","-ac","1",
    a.out,"-y"], input=out.astype(np.float32).tobytes())
print(f"{a.out}  {total:.2f}s  {a.bpm} BPM  {a.bars} bars  mood={a.mood}")
