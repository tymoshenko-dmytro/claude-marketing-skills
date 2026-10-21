#!/usr/bin/env python3
"""Measure sound effects and label them the way the Kenney analysis does.

    cd "$VIDEO_LIBRARY"
    tools/.venv/bin/python tools/analyze_sfx.py sfx/mine/*.wav > catalog/mine-sfx-analysis.raw.json

Run it from the library root, so the keys of the JSON are paths relative to the root;
build_catalog.py reads `catalog/<source>-sfx-analysis.raw.json` for every sfx source that
is not one of the shipped ones.

The Kenney/keyboard analysis (catalog/kenney-sfx-analysis.json) came already computed with
github.com/latent-spaces/brag (MIT); the script that produced it was not published. This one
measures the same quantities and applies thresholds read off that file, so new sounds sit
on the same scale. It is an approximation: where it disagrees with your ear, trust the ear
and correct the catalogue entry.

Labels
  brightness       warm < 2000 Hz <= balanced < 3500 Hz <= bright   (median spectral centroid)
  highFrequencyRisk  high if the 90th-percentile spectral centroid is >= 4900 Hz,
                   otherwise medium. Fitted against the 228 Kenney/keyboard labels:
                   88% agreement (brightness 87%, envelope 76%). The Kenney "low" class
                   (12 files) is not separable by anything measured here, so this script
                   never says "low" - read medium as "not sharp".
  envelopeShape    continuous if the level stays up for most of the sound,
                   transient if one hit carries it, textured in between
"""
import json, sys, warnings
warnings.filterwarnings("ignore")   # very short clicks are shorter than one FFT window
import numpy as np
import librosa

SR, NFFT, HOP = 44100, 2048, 256

def analyze(path):
    y, sr = librosa.load(path, sr=SR, mono=True)
    dur = len(y) / sr
    rms = librosa.feature.rms(y=y, frame_length=NFFT, hop_length=HOP)[0]
    peak = float(np.max(np.abs(y))) if y.size else 0.0
    S = np.abs(librosa.stft(y, n_fft=NFFT, hop_length=HOP)) ** 2
    freqs = librosa.fft_frequencies(sr=sr, n_fft=NFFT)
    cent = librosa.feature.spectral_centroid(S=np.sqrt(S), sr=sr)[0]
    loud = rms > (rms.max() * 0.1 if rms.size else 0)
    c = cent[loud] if loud.any() else cent
    total = S.sum() + 1e-12
    e_low = S[freqs < 500].sum() / total
    e_high = S[(freqs >= 4000) & (freqs <= 16000)].sum() / total
    e_mid = 1 - e_low - e_high
    active = loud.sum() * HOP / sr
    burden = float(e_high * min(active, 1.0))
    cont = float(loud.mean()) if loud.size else 0.0
    onset = librosa.onset.onset_strength(y=y, sr=sr, hop_length=HOP)
    sharp = float(onset.max() / (onset.mean() + 1e-9)) if onset.size else 0.0

    c50 = float(np.percentile(c, 50)) if c.size else 0.0
    brightness = "warm" if c50 < 2000 else "balanced" if c50 < 3500 else "bright"
    c90 = float(np.percentile(c, 90)) if c.size else 0.0
    risk = "high" if c90 >= 4900 else "medium"
    shape = "continuous" if cont > 0.55 else "transient" if cont < 0.38 else "textured"
    return {
        "duration": round(dur, 3),
        "loudness": {"rms": round(float(rms.mean()), 4), "peak": round(peak, 4)},
        "transient": {"sharpness": round(sharp, 3), "activeDuration": round(active, 3),
                      "continuousRatio": round(cont, 3)},
        "spectral": {"centroidP50Hz": round(c50, 1),
                     "centroidP90Hz": round(float(np.percentile(c, 90)) if c.size else 0.0, 1),
                     "energyRatioLow": round(float(e_low), 4), "energyRatioMid": round(float(e_mid), 4),
                     "energyRatioHigh": round(float(e_high), 4), "brightBurden": round(burden, 4)},
        "labels": {"brightness": brightness, "highFrequencyRisk": risk, "envelopeShape": shape},
    }

if __name__ == "__main__":
    if len(sys.argv) < 2 or sys.argv[1] in ("-h", "--help"):
        sys.exit(__doc__)
    print(json.dumps({p: analyze(p) for p in sys.argv[1:]}, indent=1))
