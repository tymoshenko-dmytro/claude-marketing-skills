#!/usr/bin/env python3
"""Build the library catalogue: catalog/music.json, catalog/sfx.json, catalog/CATALOG.md.

    python3 tools/build_catalog.py [--lib PATH]

Stdlib only. Every `path` in the catalogue is relative to the library root.

What gets indexed is driven by catalog/sources.json - one row per source folder, with its
licence. LICENSES.md says the same for people. A folder under music/ or sfx/ with no row in
sources.json is skipped with a warning: no licence row, no file.

  music/<source>/*      every audio file; beat grid, tempo and key from cues/<stem>.music-cues.json
                        (tools/analyze_music_cues.py, tools/music_key.py --write)
  musicExternal         tracks the package cannot ship (their licence does not allow it): an entry
                        with "external": true, where to get the file and where to put it. A recipe
                        rebuilds a cut from its source track (tools/prep_bed.py).
  sfx/kenney/           labels from catalog/kenney-sfx-analysis.json (shipped with latent-spaces/brag)
  sfx/osl/<type>/       the opus-sound-layer kit: type, tags, credit and peak offset from the per-sound
                        sidecar JSON + sfx/osl/catalog.osl.json; labels from catalog/osl-sfx-analysis.raw.json
  sfx/<source>/         any other source: labels from catalog/<source>-sfx-analysis.raw.json
                        (tools/analyze_sfx.py, run from the library root)

The library: --lib, else $VIDEO_LIBRARY, else the library this tools/ folder sits in, else
~/.local/share/marketing-agent-kit/video-library.
"""
import argparse, json, os, pathlib, re, sys

AUDIO = {".wav", ".mp3", ".ogg", ".flac", ".m4a", ".aif", ".aiff"}
DEFAULT_LIBRARY = "~/.local/share/marketing-agent-kit/video-library"


def library_root(arg=None):
    """--lib, then $VIDEO_LIBRARY, then the library this tools/ folder sits in, then the default."""
    if arg:
        return pathlib.Path(arg).expanduser().resolve()
    if os.environ.get("VIDEO_LIBRARY"):
        return pathlib.Path(os.environ["VIDEO_LIBRARY"]).expanduser().resolve()
    here = pathlib.Path(__file__).resolve().parent.parent
    if (here / "catalog" / "sources.json").exists():
        return here
    return pathlib.Path(DEFAULT_LIBRARY).expanduser().resolve()


ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
ap.add_argument("--lib", help="library root (default: see above)")
args = ap.parse_args()
LIB = library_root(args.lib)
CAT = LIB / "catalog"
if not (CAT / "sources.json").exists():
    sys.exit(f"no {CAT / 'sources.json'} - is {LIB} a video library? "
             "(install one: python3 skills/video-sound/scripts/library.py install)")
SOURCES = json.loads((CAT / "sources.json").read_text())
rel = lambda p: pathlib.Path(p).resolve().relative_to(LIB).as_posix()
warnings = []


def analysis_file(name):
    """Analysis JSON keyed by path; keys relative to the library root (or to tools/, or absolute)."""
    f = CAT / name
    if not f.exists():
        return {}
    out = {}
    for k, v in json.loads(f.read_text()).items():
        for cand in (LIB / k, LIB / "tools" / k, pathlib.Path(k)):
            if cand.exists():
                out[rel(cand)] = v
                break
    return out


# ---------------------------------------------------------------- music
def music_entry(f, src, meta, stem_ids=()):
    cue = LIB / "cues" / (f.stem + ".music-cues.json")
    c = json.loads(cue.read_text()) if cue.exists() else {}
    strong = sorted(c.get("strongCues", []), key=lambda x: -x.get("intensity", 0))[:5]
    mid = f.stem
    for a, b in meta.get("idReplace", []):
        mid = mid.replace(a, b)
    return {
        "id": mid, "path": rel(f) if f.exists() else f.relative_to(LIB).as_posix(), "source": src,
        "licence": meta.get("licence"), "ads": meta.get("ads", False), "credit": meta.get("credit"),
        "role": meta.get("role"), "duration": round(c.get("duration", 0), 2), "bpm": c.get("tempo"),
        "cues": rel(cue) if cue.exists() else None,
        "topStrongCues": sorted(round(x["time"], 2) for x in strong),
        "key": c.get("key"), "keyConfidence": c.get("keyConfidence"),
    }


music = []
for src, meta in SOURCES.get("music", {}).items():
    folder = LIB / "music" / src
    files = sorted(p for p in folder.glob("*") if p.suffix.lower() in AUDIO) if folder.is_dir() else []
    if not files:
        warnings.append(f"music/{src}/ has no audio files")
    for f in files:
        e = music_entry(f, src, meta)
        if meta.get("note"):
            e["note"] = meta["note"]
        music.append(e)
for x in SOURCES.get("musicExternal", []):
    f = LIB / x["path"]
    e = music_entry(f, "external", x)
    e["id"] = x["id"]
    e.update({"external": True, "title": x.get("title"), "where": x.get("where"),
              "derivedFrom": x.get("derivedFrom"), "recipe": x.get("recipe"), "note": x.get("note")})
    music.append({k: v for k, v in e.items()
                  if v is not None or k in ("ads", "credit", "cues", "key", "keyConfidence")})
known = set(SOURCES.get("music", {})) | {"external"}
for d in sorted(p for p in (LIB / "music").glob("*") if p.is_dir()):
    if d.name not in known:
        warnings.append(f"music/{d.name}/ skipped: no row in catalog/sources.json (add it and LICENSES.md first)")

# ---------------------------------------------------------------- sfx
sfx = []
SFX = SOURCES.get("sfx", {})


def words(stem):
    return [w for w in re.split(r"[^a-z]+", stem.lower()) if len(w) > 1]


for src, meta in SFX.items():
    base = LIB / "sfx" / src
    ads = meta.get("ads", False)
    if not base.is_dir():
        warnings.append(f"sfx/{src}/ is listed in sources.json but missing")
        continue
    kind = meta.get("kind", "generic")
    if kind == "kenney":     # the analysis shipped with latent-spaces/brag (MIT)
        K = json.loads((CAT / meta["analysis"]).read_text())["files"]
        for f in K:
            p = base / f["path"]
            if not p.exists():
                warnings.append(f"missing {rel(base)}/{f['path']}"); continue
            sfx.append({"id": meta.get("idPrefix", "k-") + p.stem, "path": rel(p), "family": f["family"],
                        "source": meta.get("source", src), "licence": meta["licence"], "ads": ads,
                        "duration": f["duration"], **f["labels"]})
    elif kind == "osl":      # opus-sound-layer kit: sidecars + catalog.osl.json + our labels
        meta_osl = {s["id"]: s for s in json.loads((base / "catalog.osl.json").read_text())["sounds"]}
        scans = sorted(base.glob("speech-scan-*.json"))
        speech = json.loads(scans[-1].read_text()) if scans else {}
        A = analysis_file(meta["analysis"])
        for side in sorted(base.glob("*/*.json")):
            wav = side.with_suffix(".wav")
            if not wav.exists():
                continue
            d = json.loads(side.read_text()); t = side.parent.name
            m = meta_osl.get(f"{t}/{wav.stem}", {})
            a = A.get(rel(wav), {})
            fs = "freesound" in m.get("tags", [])
            suspect = bool(speech.get(f"{t}/{wav.stem}", {}).get("suspect"))
            sfx.append({"id": f"osl-{t}-{wav.stem}", "path": rel(wav), "family": f"osl-{t}", "type": t,
                        "source": "freesound" if fs else "kenney", "licence": meta["licence"],
                        "ads": ads and not suspect,
                        "duration": d.get("dur_s"), **a.get("labels", {}),
                        "tags": [x for x in m.get("tags", []) if x not in ("freesound", t)],
                        "suggestedUses": [], "default": bool(m.get("default")),
                        "credit": m.get("credit"), "peakOffset": d.get("peak_offset_s"), "riseMs": d.get("rise_ms"),
                        "centroidHz": d.get("centroid_hz"), "below150": d.get("below150"), "above6k": d.get("above6k"),
                        "midiNote": d.get("note"), "speechSuspect": suspect})
    else:                    # keyboard, own-elevenlabs, and any source a user adds
        A = analysis_file(meta.get("analysis", f"{src}-sfx-analysis.raw.json"))
        tags_by = meta.get("tagsByStem", {})
        files = sorted(p for p in base.rglob("*") if p.suffix.lower() in AUDIO)
        for p in files:
            a = A.get(rel(p))
            if a is None:
                warnings.append(f"{rel(p)}: no analysis - run tools/analyze_sfx.py (see README.md)"); continue
            sub = p.parent.relative_to(base).as_posix()
            fam = meta.get("family") or (f"{src}-{sub}" if sub != "." else src)
            tags, uses = tags_by.get(p.stem, [meta.get("tags") or words(p.stem), meta.get("suggestedUses", [])])
            e = {"id": meta.get("idPrefix", src + "-") + p.stem, "path": rel(p), "family": fam,
                 "source": meta.get("source", src), "licence": meta["licence"], "ads": ads,
                 "duration": a["duration"], **a["labels"], "tags": tags, "suggestedUses": uses}
            if meta.get("credit"):
                e["credit"] = meta["credit"]
            sfx.append(e)
for d in sorted(p for p in (LIB / "sfx").glob("*") if p.is_dir()):
    if d.name not in SFX:
        warnings.append(f"sfx/{d.name}/ skipped: no row in catalog/sources.json (add it and LICENSES.md first)")

(CAT / "music.json").write_text(json.dumps(music, indent=1, ensure_ascii=False))
(CAT / "sfx.json").write_text(json.dumps(sfx, indent=1, ensure_ascii=False))

# ---------------------------------------------------------------- human-readable summary
L = ["# Library catalogue", "",
     "Generated by `tools/build_catalog.py`. Every path is relative to the library root.", "",
     "## Music", "", "| id | BPM | length | source | ads | role | strongest cues (s) |", "|---|---|---|---|---|---|---|"]
for m in music:
    if m.get("external"):
        continue
    L.append(f"| `{m['id']}` | {m['bpm']} | {m['duration']}s | {m['source']} | {'yes' if m['ads'] else 'no'} | "
             f"{m['role']} | {', '.join(map(str, m['topStrongCues']))} |")
ext = [m for m in music if m.get("external")]
if ext:
    L += ["", "### Not in the package (external)", "",
          "Their licence does not allow redistribution. The beat grids are here (`cues/`); put the file at "
          "its path to use it. `python3 skills/video-sound/scripts/library.py doctor` lists what is missing.", "",
          "| id | BPM | length | path | title | how to get it |", "|---|---|---|---|---|---|"]
    for m in ext:
        how = (f"cut from `{m['derivedFrom']}`: `{m['recipe']}`" if m.get("derivedFrom") else m.get("where") or "-")
        L.append(f"| `{m['id']}` | {m['bpm']} | {m['duration']}s | `{m['path']}` | {m.get('title') or '-'} | {how} |")
fam = {}
for s in sfx:
    fam.setdefault(s["family"], []).append(s)
L += ["", "## Sound effects", "",
      f"{len(sfx)} files. `highFrequencyRisk: high` = sharp/clicky - fine once, tiring when repeated.", "",
      "| family | files | source | licence | high-HF-risk share |", "|---|---|---|---|---|"]
for k, xs in fam.items():
    hi = sum(x.get("highFrequencyRisk") == "high" for x in xs)
    L.append(f"| {k} | {len(xs)} | {xs[0]['source']} | {xs[0]['licence']} | {hi}/{len(xs)} |")
L += ["", "Pick-by-use lists for the Kenney set: `catalog/kenney-sfx-analysis.md` (its paths are inside `sfx/kenney/`).", ""]
osl = [s for s in sfx if s["family"].startswith("osl-")]
if osl:
    L += ["## By type (opus-sound-layer kit)", "",
          "Functional types from the kit. `peakOffset` (s) = where the sound's peak sits: place the file at "
          "`cue - peakOffset` so the hit lands on the frame (mix.py does this with `\"align\": \"peak\"`). "
          "Defaults = the kit author's first picks.", "",
          "| type | files | defaults |", "|---|---|---|"]
    by = {}
    for s in osl:
        by.setdefault(s["type"], []).append(s)
    for t, xs in sorted(by.items(), key=lambda kv: -len(kv[1])):
        d = ", ".join(f"`{x['id']}`" for x in xs if x["default"])[:400] or "-"
        L.append(f"| {t} | {len(xs)} | {d} |")
    L.append("")
(CAT / "CATALOG.md").write_text("\n".join(L))
for w in warnings:
    print("  warning:", w, file=sys.stderr)
print(f"music {len(music)} ({len(ext)} external), sfx {len(sfx)} -> {CAT}")
