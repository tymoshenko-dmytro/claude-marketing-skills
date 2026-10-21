#!/usr/bin/env python3
"""Seam scan: one-frame glitches at the cuts of a rendered film.

Ported from latent-spaces/nanoclip-cutting-room scripts/switch-scan.mjs and switch-lab.mjs
@b06c75e (MIT): per-frame difference at every cut, the double jump (ghost or black frame),
the dead switch, the frame held before the cut, and a sheet of frames per seam. Ours takes the
cuts from our scene list, a list on the command line, or the file itself, and checks intended
transitions (dip, dissolve, wipe, whip, fade) against their own shape instead of flagging them.

    seamscan.py film.mp4                                    # detect the cuts on the file
    seamscan.py film.mp4 --scenes scenes.json --scene-in dip:3 [--seams more.json]
    seamscan.py film.mp4 --cuts 1.5,4.3,f387,62.0:dissolve:1.0,59.25:whip:0.6
    options: --detect (also check cuts nobody declared)  --sheet flagged|all|none
             --out DIR (default <film>.seams/)  --print 380-395 (per-frame numbers)

Where the cuts come from
  --scenes  our scene list (video-moves scaffold, scenes.json): {"scenes": [{"start", "dur",
            "in"?, "cut"?, "seams"?}]} or a bare list. Every scene start after the first is a
            seam of kind scene["in"], else --scene-in (default cut). "cut": u adds a hard cut at
            start + u. "seams": [{"at": u, "kind", "dur"/"frames"}] adds seams inside the scene.
  --seams   a file {"seams": [{"t": s | "frame": n, "kind", "dur"?, "frames"?, "note"?}]}.
  --cuts    comma list: 12.9 (seconds) | f387 (frame) | 62.0:dissolve:1.0 | 1.5:dip:3.
  nothing   detection on the file: every single-frame change that stands out from the motion
            around it is a cut.

Kinds and the time they name
  cut (also smash, match, jump, j, l)  the first frame of the new shot. Jump and match cuts
            may change little; they are not called SOFT.
  dip:N     the darkest frame; N frames down to it and N back up (a 3+3 dip is dip:3).
            The bottom must be a flat frame (black or any one colour).
  dissolve:D, wipe:D   the first frame of the transition, D seconds long (or Nf frames).
  whip:D    the first frame, D seconds: no held, flat or popping frame inside.
  fade:D    a scene leaves and the next arrives over the ground (a slide-and-fade): only
            a popping frame fails; pauses and the flat ground between the scenes are the design.
A time maps to the first frame at or after it: ceil(t * fps - 0.001).
Declare the cuts when you have them: at a known cut any mix of the two sides is a ghost, while
along the rest of the film a ghost must change a tenth of the frame or more (an element fading
in over two frames is a mix too). A ghost splits a cut in two, so detection alone does not see
the cut. Tested on a set of test films: every 25-75% ghost at a declared cut on still or slow
shots, 10 of 14 faint (25% old-shot) ghosts on a fast-moving new shot.

Verdicts (FAIL unless marked warn)
  GHOST      a frame that is a blend of the frames around it (a one-frame dissolve)
  BLACK/FLAT a black or flat frame alone between two pictures
  FLASH      a frame that belongs to neither side (a one-frame shot; a spliced poster at frame 0)
  HELD       the frame before the cut repeats the one before it while the shot was moving
  HELD-AFTER the first frame of the new shot repeats while the shot then moves (warn)
  DISPLACED  the change lands N frames off the declared frame (+N = late)
  DEAD       nothing changes at the declared seam
  SMEARED    the declared cut is spread over 2+ frames (a ghost too faint to confirm as a mix, or a
             soft transition declared as a cut)
  SOFT       the cut barely changes the picture: reads as a jolt (warn; not for jump/match)
  SHAPE      a declared transition does not have its shape (dip not monotonic, dissolve that
             pops or goes backwards, a dip held at the bottom)
Ghost, black and flash frames are looked for along the whole film, not only at seams.

Output: <out>/report.txt, <out>/report.json, <out>/seams-NN.jpg (7 frames per flagged seam,
labelled; the declared frame outlined yellow, the bad frame red). Exit 1 on any FAIL.
Needs ffmpeg, numpy, Pillow (system python3 has them).
"""
import argparse, json, math, pathlib, subprocess, sys
import numpy as np

# Thresholds, on frames scaled to 160 px on the long side, luma 0-255; d = mean |diff|.
FLOOR = 1.0          # a change smaller than this is never a cut or a glitch
DETECT_MIN = 2.5     # detection: a cut changes at least this much ...
DETECT_RATIO = 1.6   # ... this many times more than the frame before and after it, and not in
                     # the direction of either (a camera move that speeds up is not a cut)
CONFIRM_RATIO = 1.5  # a declared cut lands where the change is this much above its neighbours
# Ghost (a frame that is a mix of the frames around it), along the whole film. Calibrated on
# 7 clean films (0 false alarms) and ghosts injected at every cut of two of them.
GHOST_W = (0.15, 0.85)  # share of the next frame in the mix
GHOST_RES = 0.8      # the mix explains the frame to within this share of its distance to the nearest neighbour
GHOST_AREA = 0.10    # the change across it covers at least this share of the frame (an element fading
                     # in over 2 frames is a mix too, but a small one)
GHOST_CHI = 0.10     # ... and changes the colours (histogram), or stands out 2x from the motion around it
GHOST_STAND = 1.2    # ... and is this much further from its neighbours than the motion around it,
GHOST_EXACT = 0.35   # ... or the mix fits it this closely
SEAM_W = (0.10, 0.90)  # at a declared or detected cut the same test is looser: any mix there is a ghost
ALIEN_RATIO = 2.0    # a frame that is not a mix (black, flat, foreign) needs twice the motion around it
ALIEN_SHARE = 0.4    # ... and matches neither neighbour on at least this share of its changed pixels
SOFT_D = 2.0         # a cut under this (and a histogram change under SOFT_CHI) is SOFT
SOFT_CHI = 0.12
HELD_SHARE = 0.15    # a held frame changes less than this share of the motion before it
LONG_SIDE = 160


def run(cmd, **kw):
    return subprocess.run(cmd, capture_output=True, **kw)


def probe(path):
    r = run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
             "stream=width,height,r_frame_rate,avg_frame_rate", "-of", "json", str(path)], text=True)
    if r.returncode:
        sys.exit(f"ffprobe failed: {r.stderr.strip()}")
    s = json.loads(r.stdout)["streams"][0]
    n, d = map(int, s["r_frame_rate"].split("/"))
    an, ad = map(int, (s.get("avg_frame_rate") or "0/1").split("/"))
    fps = n / d
    if ad and an and abs(an / ad - fps) > 0.01:
        print(f"warning: variable frame rate ({an / ad:.3f} avg vs {fps:.3f}); frame numbers follow decode order",
              file=sys.stderr)
    return s["width"], s["height"], fps


class Film:
    """Every frame at 160 px: luma (uint8), an 8x8x8 RGB histogram, the change from the frame before."""

    def __init__(self, path):
        self.path = path
        self.W0, self.H0, self.fps = probe(path)
        if self.W0 >= self.H0:
            w, h = LONG_SIDE, max(2, round(LONG_SIDE * self.H0 / self.W0 / 2) * 2)
        else:
            w, h = max(2, round(LONG_SIDE * self.W0 / self.H0 / 2) * 2), LONG_SIDE
        self.w, self.h = w, h
        p = subprocess.Popen(["ffmpeg", "-v", "error", "-i", str(path), "-map", "0:v:0", "-an",
                              "-vf", f"scale={w}:{h}:flags=area,format=rgb24", "-fps_mode", "passthrough",
                              "-f", "rawvideo", "-"], stdout=subprocess.PIPE)
        size = w * h * 3
        Y, Hs, d, prev = [], [], [], None
        while True:
            b = p.stdout.read(size)
            if len(b) < size:
                break
            a = np.frombuffer(b, np.uint8).reshape(h, w, 3)
            y = a[..., 0] * 0.2126 + a[..., 1] * 0.7152 + a[..., 2] * 0.0722
            d.append(0.0 if prev is None else float(np.abs(y - prev).mean()))
            prev = y
            Y.append(np.round(y).astype(np.uint8))
            idx = ((a[..., 0] >> 5).astype(np.int32) << 6) | ((a[..., 1] >> 5).astype(np.int32) << 3) | (a[..., 2] >> 5)
            Hs.append((np.bincount(idx.ravel(), minlength=512) / (w * h)).astype(np.float32))
        p.wait()
        if not Y:
            sys.exit(f"could not decode {path}")
        self.Y = np.stack(Y)
        self.H = np.stack(Hs)
        self.d = np.array(d)
        self.n = len(Y)
        flat = self.Y.reshape(self.n, -1).astype(np.float32)
        self.mean = flat.mean(axis=1)
        self.std = flat.std(axis=1)
        self.noise = max(0.02, float(np.percentile(self.d[1:], 20))) if self.n > 2 else 0.02
        self.motion_floor = max(0.15, 4 * self.noise)

    def D(self, i, j):
        """mean |luma difference| between any two frames"""
        return float(np.abs(self.Y[i].astype(np.float32) - self.Y[j]).mean())

    def chi(self, i, j):
        a, b = self.H[i], self.H[j]
        s = a + b
        m = s > 0
        return float((((a - b) ** 2)[m] / s[m]).sum())

    def dd(self, i):
        return float(self.d[i]) if 0 < i < self.n else 0.0

    def frame(self, t):
        return max(0, math.ceil(t * self.fps - 1e-3))


# ---------------------------------------------------------------- seam list

ALIAS = {"smash": "cut", "j": "cut", "l": "cut", "jcut": "cut", "lcut": "cut", "j-cut": "cut", "l-cut": "cut",
         "hard": "cut", "cut": "cut", "jump": "jump", "match": "match", "dip": "dip", "dissolve": "dissolve",
         "wipe": "wipe", "whip": "whip", "fade": "fade"}


def frames_of(arg, fps, kind):
    """dip: a bare number is frames; the rest: seconds. 'Nf' is frames for any kind."""
    if arg is None or arg == "":
        return {"dip": 3, "dissolve": round(1.0 * fps), "wipe": round(1.0 * fps), "whip": round(0.6 * fps),
                "fade": round(0.6 * fps)}.get(kind, 0)
    s = str(arg).strip()
    if s.endswith("f"):
        return int(round(float(s[:-1])))
    if kind == "dip" and "." not in s:
        return int(s)
    return int(round(float(s) * fps))


def make_seam(film, *, t=None, frame=None, kind="cut", arg=None, note="", source=""):
    k = kind.lower().split(":")[0]
    if k not in ALIAS:
        sys.exit(f"unknown transition kind '{kind}' (cut, smash, match, jump, j, l, dip, dissolve, wipe, whip, fade)")
    base = ALIAS[k]
    f = int(frame) if frame is not None else film.frame(float(t))
    return dict(t=round(f / film.fps, 3) if t is None else round(float(t), 3), frame=f, kind=base,
                label=k if k == base else f"{base} ({k})", span=frames_of(arg, film.fps, base), note=note,
                source=source)


def parse_cuts(film, text):
    out = []
    for item in [x.strip() for x in text.split(",") if x.strip()]:
        parts = item.split(":")
        when, kind, arg = parts[0], (parts[1] if len(parts) > 1 else "cut"), (parts[2] if len(parts) > 2 else None)
        if when.startswith("f"):
            out.append(make_seam(film, frame=int(when[1:]), kind=kind, arg=arg, source="--cuts"))
        else:
            out.append(make_seam(film, t=float(when), kind=kind, arg=arg, source="--cuts"))
    return out


def parse_kind(spec):
    if spec is None:
        return "cut", None
    if isinstance(spec, dict):
        return spec.get("kind", "cut"), spec.get("frames", spec.get("dur"))
    p = str(spec).split(":")
    return p[0], (p[1] if len(p) > 1 else None)


def parse_scenes(film, path, scene_in):
    data = json.loads(pathlib.Path(path).read_text())
    scenes = data.get("scenes", data) if isinstance(data, dict) else data
    out = []
    for i, s in enumerate(scenes):
        start = float(s.get("start", s.get("t", s.get("at", 0.0))))
        sid = str(s.get("id", i))
        if i > 0 and start > 0:
            kind, arg = parse_kind(s.get("in", scene_in))
            out.append(make_seam(film, t=start, kind=kind, arg=arg, note=f"{sid} starts", source="scenes"))
        if s.get("cut") is not None:
            out.append(make_seam(film, t=start + float(s["cut"]), kind=s.get("cut_kind", "cut"),
                                 note=f"{sid} cut at +{s['cut']}", source="scenes"))
        for x in s.get("seams", []):
            kind, arg = parse_kind(x)
            out.append(make_seam(film, t=start + float(x["at"]), kind=kind, arg=arg,
                                 note=x.get("note", f"{sid} +{x['at']}"), source="scenes"))
    return out


def parse_seams_file(film, path):
    data = json.loads(pathlib.Path(path).read_text())
    items = data.get("seams", []) if isinstance(data, dict) else data
    out = []
    for x in items:
        kind, arg = parse_kind(x)
        out.append(make_seam(film, t=x.get("t"), frame=x.get("frame"), kind=kind, arg=arg,
                             note=x.get("note", ""), source=pathlib.Path(path).name))
    return out


# ---------------------------------------------------------------- measures

def detect_cuts(F):
    """frames whose change from the frame before stands out from the frames around it"""
    cuts = []
    for i in range(1, F.n):
        di = F.dd(i)
        if di < DETECT_MIN:
            continue
        if di < DETECT_RATIO * max(F.dd(i - 1), F.dd(i + 1), F.noise):
            continue
        v = F.Y[i].astype(np.float32) - F.Y[i - 1]
        if any(F.dd(k) >= 0.3 * di and cos(v, F.Y[k].astype(np.float32) - F.Y[k - 1]) > 0.5
               for k in (i - 1, i + 1) if 0 < k < F.n):
            continue
        cuts.append(i)
    return cuts


def blend_fit(F, i):
    """fit frame i as (1-w)*prev + w*next; return w and the residual (mean |diff|)"""
    a = F.Y[i - 1].astype(np.float32)
    b = F.Y[i + 1].astype(np.float32)
    x = F.Y[i].astype(np.float32)
    ba = b - a
    den = float((ba * ba).sum())
    if den < 1e-6:
        return 0.5, float(np.abs(x - a).mean())
    w = float(((x - a) * ba).sum() / den)
    wc = min(1.0, max(0.0, w))
    return w, float(np.abs(x - (a + wc * ba)).mean())


def cos(u, v):
    nu, nv = float(np.linalg.norm(u)), float(np.linalg.norm(v))
    return float((u * v).sum() / (nu * nv)) if nu > 1e-6 and nv > 1e-6 else 0.0


def in_ramp(F, i):
    """frame i is one step of a longer gradual change (fade, dissolve, eased move): the change into the
    frame before it, or out of the frame after it, points the same way as the change across it"""
    if i < 2 or i + 2 >= F.n:
        return False
    v = F.Y[i + 1].astype(np.float32) - F.Y[i - 1]
    return (cos(F.Y[i - 1].astype(np.float32) - F.Y[i - 2], v) > 0.5
            or cos(F.Y[i + 2].astype(np.float32) - F.Y[i + 1], v) > 0.5)


def flat(F, k, side):
    return F.std[k] < 0.2 * side or F.std[k] < 2.0


def alien_share(F, i, tau=8.0):
    """of the pixels that change around frame i, the share that matches NEITHER neighbour. Two separate
    elements stepping on consecutive frames give ~0 (each pixel equals one side); a ghost, black
    or foreign frame gives most of them."""
    x = F.Y[i].astype(np.float32)
    a = np.abs(x - F.Y[i - 1]) > tau
    b = np.abs(x - F.Y[i + 1]) > tau
    either = int((a | b).sum())
    return float((a & b).sum()) / either if either else 0.0


def glitch_at(F, i):
    """Is frame i alone between two pictures (or a run of up to 3 flat frames)? -> (verdict, last, detail) or None"""
    if i <= 0 or i >= F.n - 1:
        return None
    entry, exit_ = F.dd(i), F.dd(i + 1)
    outer = max(F.dd(i - 1), F.dd(i + 2), F.noise)
    near = min(entry, exit_)
    if near >= FLOOR:
        across = F.Y[i + 1].astype(np.float32) - F.Y[i - 1]
        area = float((np.abs(across) > 8).mean())
        side = max(F.std[i - 1], F.std[i + 1], 1.0)
        stands = near >= ALIEN_RATIO * outer
        if stands and flat(F, i, side) and alien_share(F, i) >= ALIEN_SHARE:
            return ("BLACK" if F.mean[i] < 40 else "FLAT"), i, \
                f"frame {i}: in {entry:.1f}, out {exit_:.1f}, motion around {outer:.1f}"
        if area >= GHOST_AREA and not in_ramp(F, i):
            w, res = blend_fit(F, i)
            if (GHOST_W[0] <= w <= GHOST_W[1] and res <= GHOST_RES * near
                    and (F.chi(i - 1, i + 1) >= GHOST_CHI or stands)
                    and (near >= GHOST_STAND * outer or res <= GHOST_EXACT * near)):
                return "GHOST", i, (f"frame {i} = {1 - w:.0%} previous + {w:.0%} next (distance {near:.1f}, "
                                    f"motion around {outer:.1f})")
            if stands and alien_share(F, i) >= ALIEN_SHARE and not (0.0 <= w <= 1.0 and res <= GHOST_RES * near):
                return "FLASH", i, (f"frame {i} belongs to neither side: in {entry:.1f}, out {exit_:.1f}, "
                                    f"motion around {outer:.1f}")
    # two or three flat frames between two pictures (fast editing and stepped motion make
    # short runs of real pictures, so only flat runs count)
    for L in (2, 3):
        j = i + L
        if j >= F.n:
            return None
        entry, exit_ = F.dd(i), F.dd(j)
        inner = max(F.dd(k) for k in range(i + 1, j))
        outer = max(F.dd(i - 1), F.dd(j + 1), inner, F.noise)
        near = min(entry, exit_)
        side = max(F.std[i - 1], F.std[j], 1.0)
        if near >= FLOOR and near >= ALIEN_RATIO * outer and all(flat(F, k, side) for k in range(i, j)):
            return ("BLACK" if F.mean[i] < 40 else "FLAT"), j - 1, f"frames {i}-{j - 1} flat between two pictures"
    return None


def seam_ghost(F, k):
    """at a known cut, is frame k a mix of the frames around it? (looser than the film-wide test)"""
    if k < 2 or k + 2 >= F.n:
        return None
    near = min(F.dd(k), F.dd(k + 1))
    if near < 0.3 or in_ramp(F, k):
        return None
    w, res = blend_fit(F, k)
    if SEAM_W[0] <= w <= SEAM_W[1] and res <= GHOST_RES * near:
        return f"frame {k} = {1 - w:.0%} previous + {w:.0%} next at the cut (distance {near:.1f})"
    return None


def held_before(F, f):
    """frame f-1 repeats f-2 while the shot was moving (median change of f-6..f-2)"""
    if f < 7:
        return None
    m = float(np.median([F.dd(k) for k in range(f - 6, f - 1)]))
    if m < F.motion_floor:
        return None
    if F.dd(f - 1) <= max(0.02, HELD_SHARE * m) and F.dd(f - 2) >= 0.5 * m:
        return f"frame {f - 1} repeats {f - 2} (change {F.dd(f - 1):.2f}; the shot moved {m:.2f} per frame)"
    return None


def held_after(F, f):
    if f + 7 > F.n:
        return None
    m = float(np.median([F.dd(k) for k in range(f + 2, f + 7)]))
    if m < F.motion_floor:
        return None
    if F.dd(f + 1) <= max(0.02, HELD_SHARE * m) and F.dd(f + 2) >= 0.5 * m:
        return f"frame {f + 1} repeats {f} (change {F.dd(f + 1):.2f}; then {m:.2f} per frame)"
    return None


def spike(F, i, ratio):
    return F.dd(i) >= FLOOR and F.dd(i) >= ratio * max(F.dd(i - 1), F.dd(i + 1), F.noise)


# ---------------------------------------------------------------- checks per kind

def check_cut(F, s, glitches):
    f = s["frame"]
    res = dict(verdict="ok", ok=True, bad=None, detail="")
    # 1. a glitch frame within the seam window belongs to this seam
    for g in glitches:
        if f - 3 <= g["frame"] <= f + 2 and not g.get("claimed"):
            g["claimed"] = True
            return dict(verdict=g["verdict"], ok=False, bad=g["frame"], detail=g["detail"])
    # 2. at a known cut any mix of the two sides is a ghost, however small the change
    for k in (f, f - 1):
        gh = seam_ghost(F, k)
        if gh:
            return dict(verdict="GHOST", ok=False, bad=k, detail=gh)
    # 3. held frame before the cut
    hb = held_before(F, f)
    if hb:
        return dict(verdict="HELD", ok=False, bad=f - 1, detail=hb)
    # 4. where does the change land?
    if not spike(F, f, CONFIRM_RATIO):
        cands = [k for k in range(max(1, f - 3), min(F.n, f + 4)) if k != f and spike(F, k, CONFIRM_RATIO)]
        if cands:
            k = max(cands, key=lambda c: F.dd(c))
            off = k - f
            return dict(verdict="DISPLACED", ok=False, bad=k,
                        detail=f"the change lands on frame {k} ({off:+d}: {'late' if off > 0 else 'early'}), "
                               f"change {F.dd(k):.1f}; declared frame {f} changes {F.dd(f):.2f}")
        if F.D(max(0, f - 3), min(F.n - 1, f + 2)) < max(FLOOR, 2 * F.motion_floor):
            return dict(verdict="DEAD", ok=False, bad=f, detail=f"no change across frames {f - 3}..{f + 2}")
        if F.dd(f) >= FLOOR:
            return dict(verdict="SMEARED", ok=False, bad=f,
                        detail=f"the change at {f} ({F.dd(f):.1f}) does not stand out from the frames around it "
                               f"({F.dd(f - 1):.1f} / {F.dd(f + 1):.1f}): the cut is spread over 2+ frames - a ghost "
                               f"frame, or a transition declared as a cut")
        return dict(verdict="DEAD", ok=False, bad=f,
                    detail=f"no single-frame change near {f} (frame {f} changes {F.dd(f):.2f}; "
                           f"neighbours {F.dd(f - 1):.2f} / {F.dd(f + 1):.2f})")
    ha = held_after(F, f)
    if ha:
        res = dict(verdict="HELD-AFTER", ok=True, bad=f + 1, detail=ha, warn=True)
    elif s["kind"] == "cut" and F.dd(f) < SOFT_D and F.chi(f - 1, f) < SOFT_CHI:
        res = dict(verdict="SOFT", ok=True, bad=f, warn=True,
                   detail=f"the cut changes {F.dd(f):.2f} (histogram {F.chi(f - 1, f):.2f}): a jolt more than a cut")
    if not res["detail"]:
        res["detail"] = f"change {F.dd(f):.1f} vs {F.dd(f - 1):.1f} before / {F.dd(f + 1):.1f} after"
    return res


def check_dip(F, s):
    f, N = s["frame"], max(1, s["span"])
    if f - N - 1 < 0 or f + N + 1 >= F.n:
        return dict(verdict="SHAPE", ok=False, bad=f, detail="dip window runs off the film")
    c = {k: float(F.std[f + k]) for k in range(-N - 1, N + 2)}
    ref = max(min(c[-N - 1], c[-N]), min(c[N], c[N + 1]), 1.0)
    lo = min(range(-N, N + 1), key=lambda k: c[k])
    flat = [k for k in range(-N, N + 1) if c[k] <= max(1.0, 0.04 * ref)]
    prof = " ".join(f"{c[k] / ref:.2f}" for k in range(-N, N + 1))
    if c[lo] > max(2.0, 0.15 * ref):
        return dict(verdict="DEAD", ok=False, bad=f, detail=f"no flat bottom (contrast {prof})")
    if lo != 0 and c[0] > max(1.0, 0.04 * ref) + 0.05 * ref:
        return dict(verdict="DISPLACED", ok=False, bad=f + lo,
                    detail=f"the bottom is frame {f + lo} ({lo:+d}: {'late' if lo > 0 else 'early'}); contrast {prof}")
    if len(flat) > 1:
        return dict(verdict="SHAPE", ok=False, bad=f + flat[-1],
                    detail=f"held at the bottom for {len(flat)} frames ({f + flat[0]}-{f + flat[-1]}); contrast {prof}")
    tol = 0.06 * ref + 1.0
    for k in range(-N, 0):              # contrast falls into the bottom ...
        if c[k + 1] > c[k] + tol:
            return dict(verdict="SHAPE", ok=False, bad=f + k + 1, detail=f"contrast rises on the way down at frame {f + k + 1}; {prof}")
    for k in range(0, N):               # ... and rises out of it
        if c[k + 1] < c[k] - tol:
            return dict(verdict="SHAPE", ok=False, bad=f + k + 1, detail=f"contrast falls on the way up at frame {f + k + 1}; {prof}")
    # each dimmed frame belongs to its own side: the old picture before the bottom, the new after it
    A, B = F.Y[f - N - 1].astype(np.float32), F.Y[f + N + 1].astype(np.float32)

    def z(x):
        x = x - x.mean()
        return x / (np.linalg.norm(x) + 1e-6)
    za, zb = z(A), z(B)
    if float((za * zb).sum()) < 0.9:      # the two sides differ enough to tell apart
        for k in list(range(-N + 1, 0)) + list(range(1, N)):
            x = F.Y[f + k].astype(np.float32)
            if x.std() < 1.0:
                continue
            zx = z(x)
            ca, cb = float((zx * za).sum()), float((zx * zb).sum())
            if (k < 0 and cb > ca + 0.1) or (k > 0 and ca > cb + 0.1):
                return dict(verdict="GHOST", ok=False, bad=f + k,
                            detail=f"frame {f + k} shows the {'new' if k < 0 else 'old'} picture inside the dip "
                                   f"(match old {ca:.2f}, new {cb:.2f})")
    return dict(verdict="ok", ok=True, bad=None, detail=f"bottom at {f}, contrast {prof}")


def check_smooth(F, s):
    """dissolve / wipe / whip / fade: no held, popping, black or ghost frame inside; the change happens in the window"""
    f, M, kind = s["frame"], max(2, s["span"]), s["kind"]
    a, b = max(1, f - 2), min(F.n - 1, f + M + 2)
    if b - a < 4:
        return dict(verdict="SHAPE", ok=False, bad=f, detail="window runs off the film")
    total = F.D(max(0, f - 1), min(F.n - 1, f + M))
    if total < max(FLOOR, 2 * F.motion_floor):
        return dict(verdict="DEAD", ok=False, bad=f, detail=f"the picture before and after differ by {total:.2f} only")
    ds = [F.dd(i) for i in range(a, b + 1)]
    med = float(np.median([x for x in ds if x > F.noise] or [0.0]))
    for i in range(a + 1, b):
        di, nb = F.dd(i), max(F.dd(i - 1), F.dd(i + 1))
        if di >= max(FLOOR, 0.25 * total) and di >= 2.5 * nb:
            return dict(verdict="SHAPE", ok=False, bad=i,
                        detail=f"pops at frame {i}: change {di:.1f} vs {nb:.1f} around it ({di / total:.0%} of the whole {kind})")
        lo = min(F.dd(i - 1), F.dd(i + 1))
        if kind == "fade":      # passes over the ground: a pause or a flat frame there is the design
            continue
        if f <= i <= f + M and lo >= max(F.motion_floor, 0.5 * med) and di <= max(0.02, HELD_SHARE * lo):
            return dict(verdict="HELD", ok=False, bad=i, detail=f"frame {i} repeats {i - 1} inside the {kind}")
    for i in range(a, b + 1):
        if kind != "fade" and F.std[i] < 2.0 and min(F.std[a - 1] if a > 0 else 0, F.std[min(F.n - 1, b + 1)]) > 8:
            return dict(verdict="BLACK" if F.mean[i] < 40 else "FLAT", ok=False, bad=i, detail=f"flat frame {i} inside the {kind}")
    if kind in ("dissolve", "wipe"):
        A = F.Y[max(0, f - 1)].astype(np.float32)
        B = F.Y[min(F.n - 1, f + M)].astype(np.float32)
        BA = B - A
        den = float((BA * BA).sum()) + 1e-6
        p = [float(((F.Y[i].astype(np.float32) - A) * BA).sum() / den) for i in range(a, b + 1)]
        steps = [p[k + 1] - p[k] for k in range(len(p) - 1)]
        big = max(0.3, 4.0 / M)
        for k, st in enumerate(steps):
            if st > big:
                return dict(verdict="SHAPE", ok=False, bad=a + k + 1,
                            detail=f"jumps {st:.0%} of the {kind} in one frame at {a + k + 1} (allowed {big:.0%})")
            if st < -0.15:
                return dict(verdict="SHAPE", ok=False, bad=a + k + 1, detail=f"goes back {-st:.0%} at frame {a + k + 1}")
        if p[0] > 0.1 or p[-1] < 0.9:
            return dict(verdict="DISPLACED", ok=False, bad=f,
                        detail=f"the {kind} is not inside its window: progress {p[0]:.2f} at frame {a}, {p[-1]:.2f} at {b}")
        mid = next((a + k for k, v in enumerate(p) if v >= 0.5), f)
        return dict(verdict="ok", ok=True, bad=None, detail=f"progress monotonic, half-way at frame {mid}")
    return dict(verdict="ok", ok=True, bad=None, detail=f"smooth over {f}-{f + M}: peak change {max(ds):.1f}")


# ---------------------------------------------------------------- sheet

def sheet(F, rows, out_dir):
    try:
        from PIL import Image, ImageDraw, ImageFont
    except ImportError:
        print("no Pillow: sheet skipped", file=sys.stderr)
        return []
    if not rows:
        return []
    tw = 300 if F.W0 >= F.H0 else 170
    th = round(tw * F.H0 / F.W0 / 2) * 2
    need = sorted({k for r in rows for k in r["frames"]})
    # one decode pass, frames by number (never fps=N)
    ranges, s0 = [], None
    for k in need:
        if s0 is None:
            s0 = e0 = k
        elif k == e0 + 1:
            e0 = k
        else:
            ranges.append((s0, e0)); s0 = e0 = k
    ranges.append((s0, e0))
    sel = "+".join(f"between(n\\,{x}\\,{y})" for x, y in ranges)
    raw = run(["ffmpeg", "-v", "error", "-i", str(F.path), "-map", "0:v:0", "-an",
               "-vf", f"select='{sel}',scale={tw}:{th}:flags=area,format=rgb24", "-fps_mode", "passthrough",
               "-f", "rawvideo", "-"]).stdout
    fr = np.frombuffer(raw, np.uint8)
    cnt = len(fr) // (tw * th * 3)
    tiles = {k: Image.fromarray(fr[i * tw * th * 3:(i + 1) * tw * th * 3].reshape(th, tw, 3))
             for i, k in enumerate(need[:cnt])}
    try:
        font = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", 15)
        big = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", 18)
    except Exception:
        font = big = ImageFont.load_default()
    pad, head, cols = 6, 30, 7
    per = 8
    names = []
    for si in range(0, len(rows), per):
        grp = rows[si:si + per]
        Wc = cols * tw + (cols + 1) * pad
        Hc = len(grp) * (th + head + pad) + pad
        cv = Image.new("RGB", (Wc, Hc), (40, 40, 40))
        dr = ImageDraw.Draw(cv)
        for r_i, r in enumerate(grp):
            y0 = pad + r_i * (th + head + pad)
            col = (255, 90, 90) if not r["ok"] else ((255, 200, 60) if r.get("warn") else (150, 230, 150))
            dr.text((pad + 2, y0 + 5), r["title"], fill=col, font=big)
            for c_i, k in enumerate(r["frames"]):
                x0 = pad + c_i * (tw + pad)
                yt = y0 + head
                if k in tiles:
                    cv.paste(tiles[k], (x0, yt))
                if k == r.get("bad") and not r["ok"]:
                    dr.rectangle((x0 - 3, yt - 3, x0 + tw + 2, yt + th + 2), outline=(255, 50, 50), width=4)
                elif k == r.get("bad"):
                    dr.rectangle((x0 - 3, yt - 3, x0 + tw + 2, yt + th + 2), outline=(255, 200, 60), width=3)
                if k == r["declared"]:
                    dr.rectangle((x0 - 1, yt - 1, x0 + tw, yt + th), outline=(255, 230, 0), width=2)
                lab = f"f{k}  {k / F.fps:.3f}s  d{F.dd(k):.1f}"
                bb = dr.textbbox((x0 + 4, yt + 3), lab, font=font)
                dr.rectangle((bb[0] - 3, bb[1] - 2, bb[2] + 3, bb[3] + 2), fill=(0, 0, 0))
                dr.text((x0 + 4, yt + 3), lab, fill=(255, 255, 0), font=font)
        name = out_dir / f"seams-{si // per + 1:02d}.jpg"
        cv.save(name, quality=88)
        names.append(name)
    return names


def window(F, center, n=7):
    a = max(0, min(center - n // 2, F.n - n))
    return list(range(a, min(F.n, a + n)))


# ---------------------------------------------------------------- main

def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("film")
    ap.add_argument("--scenes", help="scenes.json: every scene start is a seam")
    ap.add_argument("--scene-in", default="cut", help="kind at scene starts without their own 'in' (e.g. dip:3)")
    ap.add_argument("--seams", action="append", default=[], help="seams file {seams:[{t|frame, kind, dur|frames}]}")
    ap.add_argument("--cuts", default="", help="12.9,f387,62.0:dissolve:1.0,1.5:dip:3")
    ap.add_argument("--detect", action="store_true", help="also check cuts found on the file that nobody declared")
    ap.add_argument("--sheet", default="flagged", choices=["flagged", "all", "none"])
    ap.add_argument("--out", help="output folder (default <film>.seams/ next to the film)")
    ap.add_argument("--print", dest="pr", help="print per-frame numbers for a frame range a-b and exit")
    a = ap.parse_args()

    film = pathlib.Path(a.film).resolve()
    F = Film(film)
    if a.pr:
        x, y = map(int, a.pr.split("-"))
        for i in range(max(0, x), min(F.n, y + 1)):
            g = glitch_at(F, i)
            print(f"f{i:5d} {i / F.fps:8.3f}s  d {F.dd(i):6.2f}  chi {F.chi(max(0, i - 1), i):.3f}  "
                  f"mean {F.mean[i]:6.1f} std {F.std[i]:5.1f}" + (f"  <- {g[0]} {g[2]}" if g else ""))
        return 0

    declared = []
    if a.scenes:
        declared += parse_scenes(F, a.scenes, a.scene_in)
    for p in a.seams:
        declared += parse_seams_file(F, p)
    if a.cuts:
        declared += parse_cuts(F, a.cuts)
    declared = [s for s in declared if 0 < s["frame"] < F.n]
    declared.sort(key=lambda s: s["frame"])
    mode = "declared" if declared else "detected"
    seams = list(declared)
    if not declared or a.detect:
        near = {k for s in declared for k in range(s["frame"] - 3, s["frame"] + max(3, s["span"]) + 4)}
        for c in detect_cuts(F):
            if c not in near:
                seams.append(make_seam(F, frame=c, kind="cut", source="detected"))
        seams.sort(key=lambda s: s["frame"])

    # soft transitions own their window; glitch frames inside them are judged by their shape
    owned = set()
    for s in seams:
        if s["kind"] == "dip":
            owned |= set(range(s["frame"] - s["span"] - 1, s["frame"] + s["span"] + 2))
        elif s["kind"] in ("dissolve", "wipe", "whip"):     # a fade is still scanned for ghost frames
            owned |= set(range(s["frame"] - 2, s["frame"] + s["span"] + 3))

    # ghost, black and flash frames along the whole film
    glitches, i = [], 0
    if F.n > 2 and F.dd(1) >= FLOOR and F.dd(1) >= ALIEN_RATIO * max(F.dd(2), F.noise) and F.D(0, 2) >= 0.7 * F.dd(1):
        glitches.append(dict(frame=0, last=0, verdict="FLASH",
                             detail=f"frame 0 differs from frame 1 by {F.dd(1):.1f} and the film goes on like frame 1 "
                                    f"(change {F.dd(2):.2f}): a spliced poster blinks for one frame"))
    i = 1
    while i < F.n - 1:
        g = glitch_at(F, i) if i not in owned else None
        if g:
            glitches.append(dict(frame=i, last=g[1], verdict=g[0], detail=g[2]))
            i = g[1] + 1
        else:
            i += 1

    # a glitch frame splits a cut in two: keep the detected cut on its way in, drop the one on its way out
    seams = [s for s in seams if not (s["source"] == "detected"
                                      and any(g["frame"] < s["frame"] <= g["last"] + 1 for g in glitches))]
    for s in seams:
        if s["kind"] in ("cut", "jump", "match"):
            r = check_cut(F, s, glitches)
        elif s["kind"] == "dip":
            r = check_dip(F, s)
        else:
            r = check_smooth(F, s)
        s.update(r)
    for g in glitches:
        if not g.get("claimed"):
            seams.append(dict(t=round(g["frame"] / F.fps, 3), frame=g["frame"], kind="-", label="(no seam)", span=0,
                              note="", source="whole-film scan", verdict=g["verdict"], ok=False, bad=g["frame"],
                              detail=g["detail"]))
    seams.sort(key=lambda s: s["frame"])

    out = pathlib.Path(a.out) if a.out else film.with_suffix(".seams")
    out.mkdir(parents=True, exist_ok=True)
    for old in out.glob("seams-*.jpg"):
        old.unlink()
    for k, s in enumerate(seams, 1):
        s["n"] = k
        if s["kind"] in ("dissolve", "wipe", "whip", "fade"):
            c = s["bad"] if s.get("bad") is not None else s["frame"] + s["span"] // 2
        elif s["kind"] == "dip":
            c = s["bad"] if s.get("bad") is not None else s["frame"]
        else:
            c = s["bad"] if s.get("bad") is not None and abs(s["bad"] - s["frame"]) > 2 else s["frame"]
        s["frames"] = window(F, c)
        s["title"] = (f"#{k}  {s['t']:.3f} s  f{s['frame']}  {s['label']}{(':' + str(s['span'])) if s['span'] else ''}"
                      f"  ->  {s['verdict']}   {s['detail']}")[:150]
        s["declared"] = s["frame"] if s["kind"] != "-" else None
    flagged = [s for s in seams if not s["ok"] or s.get("warn")]
    pick = seams if a.sheet == "all" else ([] if a.sheet == "none" else flagged)
    sheets = sheet(F, pick, out)

    fails = [s for s in seams if not s["ok"]]
    warns = [s for s in seams if s["ok"] and s.get("warn")]
    lines = [f"seamscan  {film.name}  {F.W0}x{F.H0}  {F.fps:g} fps  {F.n} frames",
             f"seams: {len([s for s in seams if s['source'] != 'whole-film scan'])} "
             f"({mode}; {len(declared)} declared, {len([s for s in seams if s['source'] == 'detected'])} detected)  "
             f"noise {F.noise:.2f}, motion floor {F.motion_floor:.2f}",
             "",
             f"{'#':>3}  {'time':>8}  {'frame':>5}  {'kind':<16} {'verdict':<11} detail"]
    for s in seams:
        kind = s["label"] + (f":{s['span']}" if s["span"] else "")
        note = f"  [{s['note']}]" if s.get("note") else ""
        lines.append(f"{s['n']:>3}  {s['t']:>8.3f}  {s['frame']:>5}  {kind:<16} {s['verdict']:<11} {s['detail']}{note}")
    lines += ["", f"{'FAIL' if fails else 'PASS'}: {len(fails)} defect(s), {len(warns)} warning(s)"
              + (f"; sheets: {', '.join(str(x) for x in sheets)}" if sheets else "")]
    text = "\n".join(lines)
    (out / "report.txt").write_text(text + "\n")
    (out / "report.json").write_text(json.dumps(dict(
        film=str(film), fps=F.fps, frames=F.n, mode=mode, noise=F.noise, fail=len(fails), warn=len(warns),
        sheets=[str(x) for x in sheets],
        seams=[{k: v for k, v in s.items() if k not in ("frames", "title")} for s in seams]), indent=1))
    print(text)
    print(f"report: {out / 'report.txt'}")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
