#!/usr/bin/env python3
"""Find and look at sounds in the library, because we cannot listen.

    sfxlib.py browse --type hit [--like "metal heavy"] [--max-dur 1.0] [--min-dur 0.1]
                     [--bright warm|balanced|bright] [--n 12] [--sheet out.png] [--ads]
    sfxlib.py sheet <file-or-id> [<file-or-id> ...] --sheet out.png
    sfxlib.py measure <file> [<file> ...]

browse  ranks the catalogue ($VIDEO_LIBRARY/catalog/sfx.json): words in --like matched against
        the id and tags, the kit's default picks first, then by how close the length is to the
        middle of the range; filters by type, length, brightness. Prints each pick's path in the
        form a mix.py timeline takes ("$VIDEO_LIBRARY/sfx/..."). --sheet draws each pick's waveform
        and spectrogram (peak marked) so the shortlist can be judged by eye, then open the PNG.
        --ads keeps only sounds cleared for ads (drops speech-suspect Freesound items).
sheet   the same picture for named files or catalogue ids.
measure peak offset (s), duration, spectral centroid, the strongest note - for a new sound.
Types (opus-sound-layer kit): hit glitch zap boom ui pop tick click riser swish reverse whoosh
thump chime tap key shimmer transition paper; other families: k-* (Kenney), kb-* (keypresses),
el-* (ElevenLabs-generated), and any source you add to the library.
Idea and sheet layout after opus-sound-layer's sfx.py browse/sheet (MIT).
Run with the library venv: $VIDEO_LIBRARY/tools/.venv/bin/python sfxlib.py ... (library.py venv).
"""
import argparse, json, math, os, pathlib, subprocess, sys
import numpy as np

LIB = pathlib.Path(os.path.expanduser(os.environ.get("VIDEO_LIBRARY") or "~/.local/share/marketing-agent-kit/video-library"))
SR = 48000


def catalogue():
    f = LIB / "catalog/sfx.json"
    if not f.exists():
        sys.exit(f"no sound library at {LIB} - run: python3 {pathlib.Path(__file__).with_name('library.py')} install")
    return json.loads(f.read_text())


def path_of(item): return LIB / item["path"]


def timeline_path(item): return "$VIDEO_LIBRARY/" + item["path"]


def load(p):
    raw = subprocess.run(["ffmpeg", "-v", "error", "-i", str(p), "-ac", "1", "-ar", str(SR), "-f", "f32le", "-"],
                         capture_output=True, check=True).stdout
    return np.frombuffer(raw, np.float32).astype(np.float64)


def measure(p):
    x = load(p); n = max(1, int(0.002 * SR))
    env = np.convolve(x * x, np.ones(n) / n, mode="same"); pk = int(np.argmax(env)) / SR if len(x) else 0
    s = np.abs(np.fft.rfft(x[:SR] * np.hanning(min(len(x), SR)))); f = np.fft.rfftfreq(min(len(x), SR), 1 / SR)
    cen = float((f * s ** 2).sum() / ((s ** 2).sum() + 1e-20))
    i = int(np.argmax(np.where(f > 80, s, 0))); nb = np.median(s[max(0, i - 40):i + 40]) + 1e-12
    note = round(69 + 12 * math.log2(f[i] / 440), 1) if s[i] >= 8 * nb else None
    return dict(file=str(p), duration=round(len(x) / SR, 3), peakOffset=round(pk, 4), centroidHz=round(cen), midiNote=note)


def sheet(items, out):
    import matplotlib; matplotlib.use("Agg"); import matplotlib.pyplot as plt
    n = len(items); cols = 3; rows = math.ceil(n / cols)
    fig, axes = plt.subplots(rows * 2, cols, figsize=(5 * cols, 2.6 * rows), squeeze=False,
                             gridspec_kw=dict(height_ratios=[1, 1.4] * rows))
    for k, it in enumerate(items):
        r, c = 2 * (k // cols), k % cols; x = load(it["_file"]); t = np.arange(len(x)) / SR
        aw, asg = axes[r][c], axes[r + 1][c]
        aw.plot(t, x, lw=0.4, color="k"); aw.set_xlim(0, max(0.05, t[-1] if len(t) else 0.05))
        pko = it.get("peakOffset")
        if pko is not None: aw.axvline(pko, color="tab:red", lw=0.8)
        aw.set_title(f"{it['id'][:42]}\n{it.get('duration')} s  {it.get('brightness', '')}  {it.get('highFrequencyRisk', '')}", fontsize=7)
        aw.set_xticks([]); aw.set_yticks([])
        if len(x) > 512:
            asg.specgram(x, NFFT=512, Fs=SR, noverlap=384, cmap="magma", vmin=-120); asg.set_ylim(0, 16000)
        asg.set_xticks([]); asg.set_yticks([0, 4000, 8000, 12000, 16000]); asg.tick_params(labelsize=6)
    for k in range(n, rows * cols):
        r, c = 2 * (k // cols), k % cols; axes[r][c].axis("off"); axes[r + 1][c].axis("off")
    fig.tight_layout(); fig.savefig(out, dpi=90); plt.close(fig)
    print(f"sheet -> {out}")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("cmd", choices=["browse", "sheet", "measure"]); ap.add_argument("names", nargs="*")
    ap.add_argument("--type"); ap.add_argument("--like", default=""); ap.add_argument("--n", type=int, default=12)
    ap.add_argument("--min-dur", type=float, default=0.0); ap.add_argument("--max-dur", type=float, default=99.0)
    ap.add_argument("--bright"); ap.add_argument("--sheet"); ap.add_argument("--ads", action="store_true",
                    help="only sounds cleared for ads (excludes speech-suspect Freesound items)")
    a = ap.parse_args()
    if a.cmd == "measure":
        for f in a.names: print(json.dumps(measure(f)))
        return
    cat = catalogue(); byid = {x["id"]: x for x in cat}
    if a.cmd == "sheet":
        items = []
        for n in a.names:
            it = dict(byid[n]) if n in byid else dict(id=pathlib.Path(n).stem, **{k: v for k, v in measure(n).items() if k != "file"})
            it["_file"] = path_of(byid[n]) if n in byid else pathlib.Path(n); items.append(it)
        sheet(items, a.sheet or "sfx-sheet.png"); return
    words = [w.lower() for w in a.like.split()]
    pool = []
    for x in cat:
        if a.type and x.get("type") != a.type and not x["family"].startswith(a.type) and a.type not in x.get("tags", []): continue
        d = x.get("duration") or 0
        if not (a.min_dur <= d <= a.max_dur): continue
        if a.bright and x.get("brightness") != a.bright: continue
        if a.ads and (x.get("speechSuspect") or x.get("ads") is False): continue
        if not path_of(x).exists(): continue          # an external or removed file
        hay = (x["id"] + " " + " ".join(x.get("tags", []))).lower()
        score = sum(w in hay for w in words) * 2 + (1.5 if x.get("default") else 0)
        score -= abs(d - (a.min_dur + min(a.max_dur, 3)) / 2) * 0.2
        pool.append((score, x))
    pool.sort(key=lambda s: -s[0]); picks = [dict(x, _file=path_of(x)) for _, x in pool[: a.n]]
    print(f"{len(pool)} match; top {len(picks)}:")
    for p in picks:
        print(f"  {p['id'][:56]:56s} {p.get('duration')} s  {p.get('brightness', '')[:8]:8s} peak {p.get('peakOffset')}  {', '.join(p.get('tags', [])[:4])}")
        print(f"      {timeline_path(p)}")
    if a.sheet: sheet(picks, a.sheet)


if __name__ == "__main__":
    main()
