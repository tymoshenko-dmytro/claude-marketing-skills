#!/usr/bin/env python3
"""Install and check the video sound library (music, sound effects, beat grids, tools).

    library.py install [--from ZIP] [--force] [--sha256 HEX]   download (or take ZIP), verify, unpack
    library.py venv [--python 3.12]                            make $VIDEO_LIBRARY/tools/.venv
    library.py path                                            print the library folder
    library.py doctor                                          say what is missing

Stdlib only. The library goes to $VIDEO_LIBRARY, default ~/.local/share/marketing-agent-kit/video-library
(set VIDEO_LIBRARY in your shell to put it elsewhere; every video skill reads the same variable).

install   downloads video-library-v1.zip from the kit's GitHub release (about 150 MB), checks its
          SHA-256 against the value pinned below, unpacks it, then copies this skill's
          library-tools/ into tools/ (so the tools match the skill). An existing library is kept:
          --force moves it to <library>.bak-<time> and moves your music/external/ files across.
venv      the analysis tools need librosa, numpy, scipy, soundfile, matplotlib. Uses uv when it is
          installed (Python 3.12 by default - librosa's numba lags behind new Pythons), else
          python3 -m venv + pip.
doctor    library, catalogue, tools, venv, ffmpeg, files the catalogue names but the disk lacks,
          and the external tracks that are not there yet, with where to get each one.
          Exit 1 when the library is not installed.
"""
import argparse, hashlib, json, os, pathlib, shutil, subprocess, sys, tempfile, time, urllib.error, urllib.request, zipfile

RELEASE_URL = ("https://github.com/tymoshenko-dmytro/claude-marketing-skills/releases/download/"
               "video-library-v1/video-library-v1.zip")
SHA256 = "a2292f6b5635847b02b84f2779c78f00ccf8fd71cfb1a9d62d9dde8358f77455"
ZIP_ROOT = "video-library"
DEFAULT_LIBRARY = "~/.local/share/marketing-agent-kit/video-library"
TOOLS_SRC = pathlib.Path(__file__).resolve().parent.parent / "library-tools"
PACKAGES = ["librosa", "numpy", "scipy", "soundfile", "matplotlib"]


def library():
    return pathlib.Path(os.path.expanduser(os.environ.get("VIDEO_LIBRARY") or DEFAULT_LIBRARY))


def installed(lib):
    return (lib / "catalog" / "sfx.json").exists()


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def download(url, dest):
    print(f"downloading {url}")
    req = urllib.request.Request(url, headers={"User-Agent": "marketing-agent-kit-library"})
    with urllib.request.urlopen(req, timeout=60) as r, open(dest, "wb") as out:
        total = int(r.headers.get("Content-Length") or 0); got, last = 0, 0.0
        while True:
            block = r.read(1 << 20)
            if not block:
                break
            out.write(block); got += len(block)
            if time.time() - last > 2:
                last = time.time()
                print(f"  {got / 1e6:6.1f} MB" + (f" of {total / 1e6:.1f} MB" if total else ""), flush=True)
    print(f"  {got / 1e6:.1f} MB")


def safe_extract(zpath, into):
    """Unpack only paths under video-library/; refuse absolute paths, '..' and links."""
    with zipfile.ZipFile(zpath) as z:
        for info in z.infolist():
            p = pathlib.PurePosixPath(info.filename)
            if p.is_absolute() or ".." in p.parts or not p.parts or p.parts[0] != ZIP_ROOT:
                sys.exit(f"refusing the zip: unexpected path {info.filename!r}")
            if (info.external_attr >> 16) & 0o170000 == 0o120000:
                sys.exit(f"refusing the zip: symlink {info.filename!r}")
        z.extractall(into)
    return pathlib.Path(into) / ZIP_ROOT


def copy_tools(lib):
    if not TOOLS_SRC.is_dir():
        print(f"  (no {TOOLS_SRC}; keeping the package's tools)")
        return
    (lib / "tools").mkdir(exist_ok=True)
    for f in sorted(TOOLS_SRC.iterdir()):
        if f.is_file() and f.suffix in (".py", ".toml"):
            shutil.copy2(f, lib / "tools" / f.name)
    print(f"  tools/ <- {TOOLS_SRC.name}/ ({sum(1 for f in TOOLS_SRC.iterdir() if f.suffix in ('.py', '.toml'))} files)")


def cmd_install(a):
    lib = library()
    if installed(lib) and not a.force:
        print(f"already installed: {lib}\n  (re-install with --force; the old one is kept as a backup)")
        copy_tools(lib)
        return
    lib.parent.mkdir(parents=True, exist_ok=True)
    work = pathlib.Path(tempfile.mkdtemp(prefix=".video-library-", dir=lib.parent))
    try:
        if a.zip:
            zpath = pathlib.Path(a.zip).expanduser()
            if not zpath.exists():
                sys.exit(f"no such file: {zpath}")
        else:
            zpath = work / "video-library-v1.zip"
            try:
                download(RELEASE_URL, zpath)
            except (urllib.error.URLError, OSError) as e:
                sys.exit(f"download failed: {e}\n  {RELEASE_URL}\n"
                         "Check the connection, or download the zip in a browser and run: install --from <zip>")
        want = (a.sha256 or SHA256).lower()
        got = sha256(zpath)
        if got != want:
            sys.exit(f"SHA-256 mismatch for {zpath.name}:\n  expected {want}\n  got      {got}\n"
                     "The download is damaged or not the v1 package. Nothing was installed.")
        print(f"  SHA-256 ok ({got[:16]}...)")
        new = safe_extract(zpath, work / "unpacked")
        if lib.exists():
            if not a.force:
                sys.exit(f"{lib} exists but holds no library (no catalog/sfx.json). Move it away or use --force.")
            bak = lib.with_name(lib.name + ".bak-" + time.strftime("%Y%m%d-%H%M%S"))
            lib.rename(bak)
            print(f"  old library kept at {bak}")
            ext = bak / "music" / "external"
            for f in sorted(ext.glob("*")) if ext.is_dir() else []:
                if f.is_file() and f.name != "README.md":
                    shutil.move(str(f), new / "music" / "external" / f.name)
                    print(f"  moved your music/external/{f.name} across")
        new.rename(lib)
    finally:
        shutil.rmtree(work, ignore_errors=True)
    copy_tools(lib)
    n_sfx = len(json.loads((lib / "catalog" / "sfx.json").read_text()))
    n_mus = len(json.loads((lib / "catalog" / "music.json").read_text()))
    print(f"installed: {lib}  ({n_mus} music entries, {n_sfx} sound effects)\n"
          f"next: python3 {pathlib.Path(__file__).name} venv")


def run(cmd, **k):
    print("  $ " + " ".join(map(str, cmd)))
    return subprocess.run(cmd, **k)


def cmd_venv(a):
    lib = library()
    if not installed(lib):
        sys.exit(f"no library at {lib} - run: python3 {pathlib.Path(__file__).name} install")
    venv = lib / "tools" / ".venv"; py = venv / "bin" / "python"
    uv = shutil.which("uv")
    if uv:
        if not py.exists() and run([uv, "venv", "--python", a.python, str(venv)]).returncode:
            sys.exit("uv venv failed")
        if run([uv, "pip", "install", "--python", str(py), *PACKAGES]).returncode:
            sys.exit("uv pip install failed")
    else:
        print("  (uv not found - using python3 -m venv + pip; install uv for a pinned Python 3.12)")
        if not py.exists() and run([sys.executable, "-m", "venv", str(venv)]).returncode:
            sys.exit("python3 -m venv failed")
        if run([str(py), "-m", "pip", "install", "--quiet", *PACKAGES]).returncode:
            sys.exit("pip install failed (librosa needs numba, which may lag the newest Python; "
                     "try a Python 3.12 venv or install uv)")
    r = subprocess.run([str(py), "-c", "import librosa, numpy, scipy, soundfile, matplotlib; print(librosa.__version__)"],
                       capture_output=True, text=True)
    if r.returncode:
        sys.exit(r.stderr[-800:])
    print(f"venv ready: {py} (librosa {r.stdout.strip()})")


def cmd_doctor(a):
    lib = library(); ok, warn, bad = "ok  ", "WARN", "MISS"
    print(f"video library: {lib}")
    if not installed(lib):
        print(f"  {bad} not installed - run: python3 {pathlib.Path(__file__).name} install")
        sys.exit(1)
    src = lib / "catalog" / "sources.json"
    version = json.loads(src.read_text()).get("package", "?") if src.exists() else "?"
    music = json.loads((lib / "catalog" / "music.json").read_text())
    sfx = json.loads((lib / "catalog" / "sfx.json").read_text())
    print(f"  {ok} {version}: {len(music)} music entries, {len(sfx)} sound effects")
    tools = ["analyze_music_cues.py", "analyze_sfx.py", "build_catalog.py", "music_key.py", "prep_bed.py", "synth_bed.py"]
    gone = [t for t in tools if not (lib / "tools" / t).exists()]
    print(f"  {warn if gone else ok} tools/" + (f" missing {', '.join(gone)}" if gone else ""))
    py = lib / "tools" / ".venv" / "bin" / "python"
    if py.exists():
        r = subprocess.run([str(py), "-c", "import librosa, numpy, scipy, soundfile, matplotlib"], capture_output=True, text=True)
        print(f"  {ok if r.returncode == 0 else warn} venv {py}" + ("" if r.returncode == 0 else
              f" - imports fail; run: python3 {pathlib.Path(__file__).name} venv"))
    else:
        print(f"  {warn} no venv (sfxlib, sfxauto, soundqa and the analysis tools need it) - "
              f"run: python3 {pathlib.Path(__file__).name} venv")
    for t in ("ffmpeg", "ffprobe"):
        print(f"  {ok if shutil.which(t) else bad} {t}" + ("" if shutil.which(t) else " not on PATH (every sound script needs it)"))
    lost = [x["path"] for x in music + sfx if not x.get("external") and not (lib / x["path"]).exists()]
    if lost:
        print(f"  {bad} {len(lost)} catalogued files missing on disk, e.g. {lost[0]} - reinstall with --force")
    ext = [m for m in music if m.get("external")]
    have = [m for m in ext if (lib / m["path"]).exists()]
    print(f"  {ok if len(have) == len(ext) else warn} external tracks: {len(have)} of {len(ext)} present")
    by_id = {m["id"]: m for m in ext}
    for m in ext:
        if (lib / m["path"]).exists():
            continue
        if m.get("derivedFrom"):
            src_m = by_id.get(m["derivedFrom"])
            ready = src_m and (lib / src_m["path"]).exists()
            print(f"       {m['id']:18s} -> {m['path']}: a cut of {m['derivedFrom']}"
                  + (f"; make it: cd {lib} && {m['recipe']}" if ready else f" (get {m['derivedFrom']} first)"))
        else:
            print(f"       {m['id']:18s} -> {m['path']}: \"{m.get('title')}\". {m.get('where', '')}")
    sys.exit(0)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("install", help="download, verify and unpack the library")
    p.add_argument("--from", dest="zip", help="use this local zip instead of downloading")
    p.add_argument("--force", action="store_true", help="replace an existing library (kept as a backup)")
    p.add_argument("--sha256", help="expect this SHA-256 instead of the pinned one (your own build)")
    p = sub.add_parser("venv", help="create tools/.venv with the analysis packages")
    p.add_argument("--python", default="3.12", help="Python version for uv (default 3.12)")
    sub.add_parser("path", help="print the library folder")
    sub.add_parser("doctor", help="say what is missing")
    a = ap.parse_args()
    if a.cmd == "path":
        print(library())
    else:
        {"install": cmd_install, "venv": cmd_venv, "doctor": cmd_doctor}[a.cmd](a)


if __name__ == "__main__":
    main()
