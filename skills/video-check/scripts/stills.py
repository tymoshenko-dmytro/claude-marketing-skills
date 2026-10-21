#!/usr/bin/env python3
"""Stills at chosen times, tiled into one contact sheet - the look-before-render pass.

    stills.py <project_dir> 0 1.8 3.6 3.9 ... [--cols 4] [--out sheet.jpg]
    stills.py <project_dir> --every 1.0            # one per second of the composition
    stills.py <project_dir> --every 0.5 --per-sheet 12           # sheets of 3x4 for a reviewer
    stills.py <project_dir> --every 1.5 --width 390 --cols 2 --out phone.jpg   # phone width

Pick times that include the MIDDLE of every transition, not only settled frames:
the double exposure, the element that is visible before its entrance, the content that
slides out while the window slides in - all of them live between scenes.

Uses `hyperframes snapshot --at ... --no-end`. For a 1:1 crop of something small
(an image that might be squashed, a tag, a caption edge) run snapshot yourself with
`--zoom "<selector>"` or `--zoom x,y,w,h`.

Every tile is labelled with its time. --per-sheet N splits the frames into numbered sheets
(sheet-01.jpg, ...) of N each - a reviewer reads a few small sheets better than one tall one.
"""
import argparse, json, pathlib, shutil, subprocess, sys

ap = argparse.ArgumentParser()
ap.add_argument("project"); ap.add_argument("times", nargs="*", type=float)
ap.add_argument("--every", type=float); ap.add_argument("--cols", type=int, default=4)
ap.add_argument("--out", default=None); ap.add_argument("--width", type=int, default=640)
ap.add_argument("--per-sheet", type=int, default=0, help="frames per sheet; 0 = one sheet")
a = ap.parse_args()

proj = pathlib.Path(a.project).resolve()
times = a.times
if a.every:
    info = subprocess.run(["npx", "--yes", "hyperframes", "info", "--json", str(proj)], capture_output=True, text=True).stdout
    try: total = float(json.loads(info[info.find("{"):]).get("duration", 0))
    except Exception: sys.exit("could not read the composition duration; pass times explicitly")
    times = [round(i * a.every, 2) for i in range(int(total / a.every) + 1)]
if not times: sys.exit("give times or --every")

out_dir = proj / "stills"
shutil.rmtree(out_dir, ignore_errors=True)
r = subprocess.run(["npx", "--yes", "hyperframes", "snapshot", str(proj), "-o", str(out_dir), "--no-end",
                    "--describe", "false", "--at", ",".join(f"{t:g}" for t in times)], capture_output=True, text=True)
import re
def _t(p):  # snapshot names carry the time; sort by it, not as strings (0, 11.4, 2.6 ...)
    m = re.findall(r"\d+(?:\.\d+)?", p.stem)
    return float(m[-1]) if m else 0.0
pngs = sorted(out_dir.glob("*.png"), key=_t)
if r.returncode or not pngs: sys.exit(r.stdout[-1500:] + r.stderr[-1500:])
sheet = pathlib.Path(a.out) if a.out else proj / "sheet.jpg"
groups = [pngs[i:i + a.per_sheet] for i in range(0, len(pngs), a.per_sheet)] if a.per_sheet else [pngs]
names = [sheet] if len(groups) == 1 else [sheet.with_name(f"{sheet.stem}-{k + 1:02d}{sheet.suffix}") for k in range(len(groups))]
try:
    from PIL import Image, ImageDraw, ImageFont
except ImportError:
    Image = None
for grp, name in zip(groups, names):
    rows = -(-len(grp) // a.cols)
    if Image is None:   # no Pillow: ffmpeg tile, unlabelled
        lst = out_dir / "_order.txt"
        lst.write_text("".join(f"file '{p}'\n" for p in grp))
        subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", str(lst),
                        "-vf", f"scale={a.width}:-1,tile={a.cols}x{rows}:padding=6:color=0x888888", "-frames:v", "1",
                        str(name), "-y"], check=True)
        continue
    ims = [Image.open(p).convert("RGB") for p in grp]
    h = round(ims[0].height * a.width / ims[0].width); pad = 6
    canvas = Image.new("RGB", (a.cols * a.width + (a.cols + 1) * pad, rows * h + (rows + 1) * pad), (136, 136, 136))
    try: font = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", max(12, a.width // 28))
    except Exception: font = ImageFont.load_default()
    for k, (im, p) in enumerate(zip(ims, grp)):
        x, y = pad + (k % a.cols) * (a.width + pad), pad + (k // a.cols) * (h + pad)
        canvas.paste(im.resize((a.width, h), Image.LANCZOS), (x, y))
        d = ImageDraw.Draw(canvas); label = f"{_t(p):g}s"
        box = d.textbbox((x + 4, y + 3), label, font=font)
        d.rectangle((box[0] - 3, box[1] - 2, box[2] + 3, box[3] + 2), fill=(0, 0, 0)); d.text((x + 4, y + 3), label, fill=(255, 255, 0), font=font)
    canvas.save(name, quality=88)
print(f"{len(pngs)} stills -> {', '.join(str(n) for n in names)}  (frames in {out_dir})")
