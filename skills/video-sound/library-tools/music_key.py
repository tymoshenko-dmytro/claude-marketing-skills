#!/usr/bin/env python3
"""Estimate a track's musical key and write it into its cue file.

    tools/.venv/bin/python tools/music_key.py <track> [<track> ...] [--write] [--lib PATH]

Method: mean constant-Q chroma over the whole track, correlated with the Krumhansl-Kessler
major and minor key profiles (24 keys); the best correlation wins, `keyConfidence` is its lead
over the runner-up (r difference; under ~0.05 = ambiguous - treat the key as a hint).
--write adds "key", "keyTonic" (pitch class 0 = C), "keyMode" and "keyConfidence" to
cues/<stem>.music-cues.json in the library, which build_catalog.py copies into catalog/music.json.
Used by video-sound's sfxauto.py to pitch tonal effects into the music's key
(an idea from opus-sound-layer, MIT; it had no key detection).

The library: --lib, else $VIDEO_LIBRARY, else the library this tools/ folder sits in, else
~/.local/share/marketing-agent-kit/video-library.
"""
import json, os, pathlib, sys, warnings
warnings.filterwarnings("ignore")
import numpy as np
import librosa

NAMES = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]
MAJOR = np.array([6.35, 2.23, 3.48, 2.33, 4.38, 4.09, 2.52, 5.19, 2.39, 3.66, 2.29, 2.88])
MINOR = np.array([6.33, 2.68, 3.52, 5.38, 2.60, 3.53, 2.54, 4.75, 3.98, 2.69, 3.34, 3.17])
DEFAULT_LIBRARY = "~/.local/share/marketing-agent-kit/video-library"


def library_root(arg=None):
    """--lib, then $VIDEO_LIBRARY, then the library this tools/ folder sits in, then the default."""
    if arg:
        return pathlib.Path(arg).expanduser().resolve()
    if os.environ.get("VIDEO_LIBRARY"):
        return pathlib.Path(os.environ["VIDEO_LIBRARY"]).expanduser().resolve()
    here = pathlib.Path(__file__).resolve().parent.parent
    if (here / "catalog").is_dir() and (here / "cues").is_dir():
        return here
    return pathlib.Path(DEFAULT_LIBRARY).expanduser()


def estimate(path):
    y, sr = librosa.load(str(path), sr=22050, mono=True, duration=240)
    chroma = librosa.feature.chroma_cqt(y=y, sr=sr).mean(axis=1)
    scores = []
    for t in range(12):
        for mode, prof in (("major", MAJOR), ("minor", MINOR)):
            scores.append((float(np.corrcoef(chroma, np.roll(prof, t))[0, 1]), t, mode))
    scores.sort(reverse=True)
    (r, t, mode), r2 = scores[0], scores[1][0]
    return {"key": f"{NAMES[t]} {mode}", "keyTonic": t, "keyMode": mode, "keyConfidence": round(r - r2, 3)}


def main():
    argv = sys.argv[1:]
    if not argv or "-h" in argv or "--help" in argv:
        sys.exit(__doc__)
    lib_arg = None
    if "--lib" in argv:
        i = argv.index("--lib"); lib_arg = argv[i + 1]; del argv[i:i + 2]
    args = [a for a in argv if not a.startswith("--")]
    write = "--write" in argv
    lib = library_root(lib_arg)
    for a in args:
        p = pathlib.Path(a); k = estimate(p)
        print(f"{p.name:60s} {k['key']:9s} confidence {k['keyConfidence']}")
        if write:
            cue = lib / "cues" / (p.stem + ".music-cues.json")
            if cue.exists():
                c = json.loads(cue.read_text()); c.update(k); cue.write_text(json.dumps(c, indent=1))
            else:
                print(f"   (no cue file {cue}; key not stored - run analyze_music_cues.py first)")


if __name__ == "__main__":
    main()
