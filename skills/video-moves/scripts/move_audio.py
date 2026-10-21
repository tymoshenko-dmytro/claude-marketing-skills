#!/usr/bin/env python3
"""Sound for camera and editing moves - an importable toolkit.

Brand- and film-neutral. Extracted from the audio script of a 24-move test reel. A project's
own audio script imports this module, lays the move sounds and the story-time voice on numpy
buffers, writes stems, and mixes them with video-sound's mix.py.

    import sys; sys.path.insert(0, "<path to video-moves/scripts>")
    import move_audio as ma
    fx = ma.buffer(total)
    ma.put(fx, ma.whoosh(0.6, 300, 3600), t=12.4, gain=-12)                 # whip pan
    s, r = ma.story_curve(scene["story"], scene["dur"])                     # same segs as camera-kit.js
    voice = ma.load(recording); y = ma.voice_at(voice, s) * ma.gate(r > 0.03) * ma.env_ad(len(s), 0.01, 0.08)

Run with the sound library's venv (numpy, scipy, soundfile; installed by
video-sound/scripts/library.py install):
    $VIDEO_LIBRARY/tools/.venv/bin/python move_audio.py --demo <dir>
renders every synth to <dir>/*.wav for listening. The library is found at $VIDEO_LIBRARY, else
~/.local/share/marketing-agent-kit/video-library; kenney() needs it, the synths do not.
"""
import argparse, os, pathlib, subprocess, tempfile
import numpy as np
import soundfile as sf
from scipy import signal

SR = 48000
# the shared sound library (installed by video-sound/scripts/library.py install)
LIB = pathlib.Path(os.environ.get("VIDEO_LIBRARY")
                   or pathlib.Path.home() / ".local/share/marketing-agent-kit/video-library").expanduser()
# Kenney CC0 sounds that served the test reel (paths under LIB; licence rows in LIB/LICENSES.md)
KENNEY = {
    "click": "sfx/kenney/ui/mouseclick1.ogg",               # a UI click before a whip
    "tick": "sfx/kenney/interface/click_005.ogg",           # focus pull, time-lapse ticks (low HF risk)
    "switch": "sfx/kenney/ui/switch12.ogg",                 # jump-cut jumps
    "bell": "sfx/kenney/impact/impactBell_heavy_003.ogg",   # match cut
    "punch": "sfx/kenney/impact/impactPunch_heavy_000.ogg", # smash cut
    "soft_hit": "sfx/kenney/impact/impactSoft_heavy_000.ogg",  # crash-zoom landing
    "tap": "sfx/kenney/impact/impactSoft_medium_000.ogg",   # a card's entrance
}
_rng = np.random.default_rng(11)


# ---------------------------------------------------------------- basics
def load(path):
    """Any audio file -> mono float at SR (ffmpeg decodes, so ogg/mp3 need no codecs)."""
    with tempfile.TemporaryDirectory() as d:
        tmp = pathlib.Path(d) / "x.wav"
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(path), "-ac", "1", "-ar", str(SR), str(tmp)], check=True)
        x, _ = sf.read(tmp)
    return x.astype(float)


def kenney(name):
    path = LIB / KENNEY[name]
    if not path.exists():
        raise SystemExit(f"missing {path} - install the sound library (video-sound/scripts/library.py install) "
                         "or set VIDEO_LIBRARY to where it lives")
    return load(path)


def buffer(seconds):
    return np.zeros(int(round(seconds * SR)) + SR)


def db(g):
    return 10 ** (g / 20)


def norm(x, peak=-6.0):
    m = np.max(np.abs(x)) or 1.0
    return x / m * db(peak)


def put(buf, x, t, gain=0.0):
    """Add x into buf at t seconds with a static gain (dB)."""
    i = int(round(t * SR))
    if i < 0:
        x, i = x[-i:], 0
    j = min(len(buf), i + len(x))
    buf[i:j] += x[: j - i] * db(gain)


def env_ad(n, a=0.01, d=None):
    """Linear attack (s) and optional release (s) over n samples - no hard edges."""
    e = np.ones(n)
    na = max(1, int(a * SR)); e[:na] = np.linspace(0, 1, na)
    if d:
        nd = max(1, int(d * SR)); e[-nd:] *= np.linspace(1, 0, nd)
    return e


def swell(n):
    return np.sin(np.linspace(0, np.pi, n)) ** 2


def bandnoise(dur, f0, f1, width=0.5):
    """Noise whose band centre glides f0 -> f1 (log), via an STFT mask."""
    n = int(dur * SR); x = _rng.standard_normal(n)
    f, _, Z = signal.stft(x, SR, nperseg=1024)
    cen = np.exp(np.linspace(np.log(f0), np.log(f1), Z.shape[1]))
    lf = np.log(np.maximum(f, 1))[:, None]
    mask = np.exp(-0.5 * ((lf - np.log(cen)[None, :]) / width) ** 2)
    _, y = signal.istft(Z * mask, SR, nperseg=1024)
    return y[:n]


def sweep(dur, f0, f1):
    n = int(dur * SR); t = np.arange(n) / SR
    f = f0 * (f1 / f0) ** (t / dur)
    return np.sin(2 * np.pi * np.cumsum(f) / SR)


# ---------------------------------------------------------------- move sounds (peak -6 dBFS)
def air(dur):
    """Pan, tilt, dolly, orbit, crane, tracking: soft moving air, ~-24 dB under the bed."""
    return norm(bandnoise(dur, 260, 520, 0.6) * swell(int(dur * SR)))


def whoosh(dur, f0=300, f1=3000):
    """Whip pan, crash zoom, props passing the lens, freeze exit: noise with a rising band."""
    n = int(dur * SR)
    return norm(bandnoise(dur, f0, f1, 0.45) * np.sin(np.linspace(0, np.pi, n)) ** 1.5)


def riser(dur):
    """Dolly zoom: tone 110 -> 520 Hz + rising noise."""
    n = int(dur * SR); e = np.linspace(0, 1, n) ** 1.6
    return norm((sweep(dur, 110, 520) * 0.7 + bandnoise(dur, 400, 2400, 0.5) * 0.5) * e * env_ad(n, 0.02, 0.08))


def tape_stop(dur):
    """Speed ramp down: 260 -> 45 Hz, fading."""
    n = int(dur * SR)
    return norm(sweep(dur, 260, 45) * np.linspace(1, 0.2, n) * env_ad(n, 0.01, 0.1))


def ring(dur=1.3, f=1760):
    """Freeze frame: a high ring in the silence."""
    n = int(dur * SR); t = np.arange(n) / SR
    return norm((np.sin(2 * np.pi * f * t) + 0.25 * np.sin(2 * np.pi * 2 * f * t)) * np.exp(-t * 2.4) * env_ad(n, 0.004))


def _thump(f=55, dur=0.16):
    n = int(dur * SR); t = np.arange(n) / SR
    return np.sin(2 * np.pi * f * t * (1 - 0.3 * t / dur)) * np.exp(-t * 26)


def heartbeat():
    """Slow motion / the slow part of a ramp."""
    x = np.zeros(int(0.5 * SR)); x[: len(_thump())] += _thump()
    j = int(0.26 * SR); x[j:j + len(_thump())] += 0.6 * _thump(50)
    return norm(x)


def arpeggio(notes=(523.25, 659.25, 783.99, 1046.5), step=0.085):
    """Time-lapse ending: a short arpeggio up."""
    out = np.zeros(int((step * len(notes) + 0.35) * SR))
    for i, f in enumerate(notes):
        n = int(0.3 * SR); t = np.arange(n) / SR
        put(out, np.sin(2 * np.pi * f * t) * np.exp(-t * 9) * env_ad(n, 0.005), i * step)
    return norm(out)


def ticks(start, end, first=0.26, last=0.055, factor=0.86):
    """Time-lapse: tick times that speed up; lay a 'tick' sample at each."""
    out, u, step = [], start, first
    while u < end:
        out.append(round(u, 4)); u += step; step = max(last, step * factor)
    return out


def buzz(dur):
    """FPV: a saw near 185 Hz with vibrato, low-passed."""
    n = int(dur * SR); t = np.arange(n) / SR
    f = 185 + 5 * np.sin(2 * np.pi * 6 * t) + 25 * t / dur
    saw = signal.sawtooth(2 * np.pi * np.cumsum(f) / SR)
    sos = signal.butter(4, 1400, "low", fs=SR, output="sos")
    return norm(signal.sosfilt(sos, saw) * env_ad(n, 0.05, 0.6))


def hum(dur):
    """The quiet half of a smash cut: 60 Hz hum and room noise (lay it around -34 dB)."""
    n = int(dur * SR); t = np.arange(n) / SR
    room = signal.sosfilt(signal.butter(2, 300, "low", fs=SR, output="sos"), _rng.standard_normal(n))
    return norm((np.sin(2 * np.pi * 60 * t) * 0.5 + np.sin(2 * np.pi * 120 * t) * 0.2 + room * 0.3) * env_ad(n, 0.2, 0.01))


def drone(dur):
    """Dutch angle: a detuned low swell."""
    n = int(dur * SR); t = np.arange(n) / SR
    return norm((np.sin(2 * np.pi * 98 * t) + np.sin(2 * np.pi * 103.5 * t) + 0.4 * np.sin(2 * np.pi * 147 * t)) * swell(n))


# ---------------------------------------------------------------- story time (= camera-kit.js)
def piecewise_rate(segs):
    """Same semantics as CK.piecewiseRate: {until, rate} holds, {until, to} smoothsteps."""
    def rate(u):
        prev_end, prev_rate = 0.0, segs[0].get("rate", 1)
        for s in segs:
            end = s.get("until", float("inf"))
            if u < end:
                if s.get("to") is not None:
                    k = min(1, max(0, (u - prev_end) / (end - prev_end))); k = k * k * (3 - 2 * k)
                    return prev_rate + (s["to"] - prev_rate) * k
                return s["rate"]
            prev_rate = s["to"] if s.get("to") is not None else s["rate"]; prev_end = end
        return prev_rate
    return rate


def story_curve(story, dur):
    """Story time s and rate r at every output sample of a scene. story = {s0, segs}."""
    rate = piecewise_rate(story["segs"])
    u = np.arange(int(dur * SR)) / SR
    r = np.array([rate(x) for x in u])
    s = story["s0"] + np.concatenate([[0], np.cumsum((r[1:] + r[:-1]) / 2) / SR])
    return s, r


def real_at(s_curve, s_target):
    """Real time (s, from the scene start) when the story reaches s_target - place sounds
    that belong to the world (a clock tick, a step) here, so they thin out in slow motion
    and vanish in a freeze. s_curve from story_curve()."""
    i = int(np.searchsorted(s_curve, s_target))
    return i / SR if i < len(s_curve) else None


def voice_at(voice, s):
    """Read a recording at story times s (linear interpolation = tape-style varispeed:
    pitch follows speed, as slow motion and a ramp should sound)."""
    t = np.arange(len(voice)) / SR
    return np.interp(s, t, voice, left=0.0, right=0.0)


def gate(on, smooth=0.012):
    """Smooth on/off mask from a boolean array (a freeze: rate == 0 -> silent)."""
    k = int(smooth * SR)
    return np.convolve(on.astype(float), np.ones(k) / k, mode="same")


def speech_onset(voice, thresh_db=-35, win=0.01):
    """First time (s) the recording rises above thresh - J/L leads are measured from here,
    not from 0 (the test reel's recording starts speaking at 0.2 s and a 0.45 s lead became 0.25)."""
    n = int(win * SR)
    for i in range(0, len(voice) - n, n):
        if 20 * np.log10(np.sqrt(np.mean(voice[i:i + n] ** 2)) + 1e-12) > thresh_db:
            return i / SR
    return 0.0


def bed_gap(env, t0, t1, level=0.0, fin=0.03, fout=0.12):
    """Cut the bed's envelope between t0 and t1 (a freeze, the quiet half of a smash)."""
    i0, i1 = int(t0 * SR), int(t1 * SR)
    env[i0:i1] = np.minimum(env[i0:i1], level)
    a = int(fin * SR); env[i0 - a:i0] = np.minimum(env[i0 - a:i0], np.linspace(1, level, a))
    b = int(fout * SR); env[i1:i1 + b] = np.minimum(env[i1:i1 + b], np.linspace(level, 1, b))


def true_peak_pass(src, dst, limit=0.66):
    """Only for a mix NOT made by video-sound's mix.py - since 2026-10-14 mix.py ends in its own
    oversampled true-peak limiter (-2 dBTP, gain re-solved to the target). Old note: a sample-peak
    limiter leaves inter-sample peaks and AAC overshoot. One
    oversampled peak-only pass: limit 0.66 (-3.6 dBFS) left -3.4 dBTP after AAC on the test reel;
    0.78 left -0.5 dBTP after AAC. No gain riding."""
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(src), "-af",
                    f"aresample=192000,alimiter=limit={limit}:attack=0.5:release=40:level=disabled,aresample=48000",
                    "-c:a", "pcm_s24le", str(dst)], check=True)


# ---------------------------------------------------------------- demo
if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--demo", metavar="DIR", help="render every synth to DIR for listening")
    a = ap.parse_args()
    if a.demo:
        out = pathlib.Path(a.demo); out.mkdir(parents=True, exist_ok=True)
        for name, x in [("air", air(2.0)), ("whoosh", whoosh(0.6, 300, 3600)), ("riser", riser(1.8)),
                        ("tape_stop", tape_stop(0.55)), ("ring", ring()), ("heartbeat", heartbeat()),
                        ("arpeggio", arpeggio()), ("buzz", buzz(2.6)), ("hum", hum(1.2)), ("drone", drone(2.0))]:
            sf.write(out / f"{name}.wav", x.astype(np.float32), SR)
        print(f"10 synths -> {out}")
    else:
        ap.print_help()
