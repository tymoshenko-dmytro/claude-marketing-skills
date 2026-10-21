#!/usr/bin/env python3
"""Thin Atlas Cloud client: upload, submit, poll, download (Python standard library only).

Every request and response is kept as JSON in the jobs folder, so a paid job can always be
traced back to the exact payload that was sent.

Use it from the command line:

    atlas.py upload keyframe.jpg                         # -> a public URL for the payload
    atlas.py run video payload.json --tag s01 --out shots/
    atlas.py run image payload.json --tag kf01 --out keyframes/
    atlas.py submit video payload.json --tag s01         # submit only, prints the job id
    atlas.py poll <job-id> --tag s01                     # wait for a submitted job
    atlas.py download <url> shots/s01.mp4

or import it from a film's own script:

    import sys; sys.path.insert(0, "<path to this folder>")
    import atlas
    atlas.run("video", {"model": "...", "prompt": "...", ...}, tag="s01", out_dir="shots")

payload.json is the model's request body exactly as the Atlas Cloud model page shows it
(model id, prompt, image/last_image URLs, duration, resolution ...).

Key: ATLAS_API_KEY - the environment first, then ~/.config/marketing-agent-kit/.env
(override the file with MARKETING_KIT_ENV). Setup: connections/atlas-cloud.md.
Jobs folder: ATLAS_JOBS_DIR, else ~/.local/share/marketing-agent-kit/atlas/jobs (or --jobs).

There is no balance endpoint. On any new model: one paid call, then read the line on the
dashboard (atlascloud.ai/console), before the second call.
"""
import argparse
import json
import mimetypes
import os
import pathlib
import re
import sys
import time
import urllib.request
import uuid

BASE = "https://api.atlascloud.ai/api/v1"
ENV_FILE = pathlib.Path(os.path.expanduser(
    os.environ.get("MARKETING_KIT_ENV", "~/.config/marketing-agent-kit/.env")))
JOBS = pathlib.Path(os.path.expanduser(
    os.environ.get("ATLAS_JOBS_DIR", "~/.local/share/marketing-agent-kit/atlas/jobs")))
# A browser-like User-Agent: the API sits behind a CDN that has refused bare script agents.
UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/126.0 Safari/537.36"


def env_value(raw: str) -> str:
    """Value of KEY=value: drop an inline comment (a # at the start or after a space), then quotes."""
    return re.split(r"(?:^|\s)#", raw.strip(), maxsplit=1)[0].strip().strip('"').strip("'")


def key() -> str:
    v = os.environ.get("ATLAS_API_KEY", "").strip()
    if v:
        return v
    if ENV_FILE.exists():
        for line in ENV_FILE.read_text().splitlines():
            k, sep, raw = line.strip().partition("=")
            if sep and k.strip() == "ATLAS_API_KEY":
                v = env_value(raw)
                if v:
                    return v
    sys.exit(
        "error: no Atlas Cloud API key found.\n"
        f"  set $ATLAS_API_KEY, or add ATLAS_API_KEY=... to {ENV_FILE} (chmod 600).\n"
        "  Setup: connections/atlas-cloud.md")


def _jobs() -> pathlib.Path:
    JOBS.mkdir(parents=True, exist_ok=True)
    return JOBS


def _req(method, url, data=None, headers=None, timeout=120):
    h = {"Authorization": "Bearer " + key(), "User-Agent": UA, "Accept": "application/json"}
    h.update(headers or {})
    r = urllib.request.Request(url, data=data, headers=h, method=method)
    with urllib.request.urlopen(r, timeout=timeout) as resp:
        return json.loads(resp.read().decode())


def upload(path):
    """Upload a local file; returns a public URL to put in a payload. Upload JPEG keyframes:
    a 1.6 MB PNG timed out here."""
    path = pathlib.Path(path)
    b = uuid.uuid4().hex
    ctype = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
    body = (f"--{b}\r\nContent-Disposition: form-data; name=\"file\"; filename=\"{path.name}\"\r\n"
            f"Content-Type: {ctype}\r\n\r\n").encode() + path.read_bytes() + f"\r\n--{b}--\r\n".encode()
    j = _req("POST", BASE + "/model/uploadMedia", body, {"Content-Type": f"multipart/form-data; boundary={b}"})
    if j.get("code") != 200:
        raise SystemExit(f"upload failed: {j}")
    return j["data"]["download_url"]


def submit(kind, payload, tag):
    """kind 'image' -> generateImage, anything else -> generateVideo. Returns the job id."""
    ep = "generateImage" if kind == "image" else "generateVideo"
    j = _req("POST", f"{BASE}/model/{ep}", json.dumps(payload).encode(), {"Content-Type": "application/json"})
    (_jobs() / f"{tag}.submit.json").write_text(json.dumps({"payload": payload, "response": j}, indent=1))
    d = j.get("data") if isinstance(j, dict) else None
    jid = (d or {}).get("id") if isinstance(d, dict) else None
    if not jid:
        raise SystemExit(f"submit failed [{tag}]: {json.dumps(j)[:500]}")
    (_jobs() / f"{tag}.id").write_text(jid)
    return jid


def poll(jid, tag, interval=6, timeout=1500):
    t0 = time.time()
    last = None
    while time.time() - t0 < timeout:
        j = None
        for ep in ("prediction", "result"):
            try:
                j = _req("GET", f"{BASE}/model/{ep}/{jid}")
                break
            except Exception:
                j = None
        if not j:
            time.sleep(interval)
            continue
        d = j.get("data") if isinstance(j.get("data"), dict) else j
        st = d.get("status")
        if st != last:
            print(f"  [{tag}] {st} {int(time.time() - t0)}s", flush=True)
            last = st
        if st in ("completed", "failed", "timeout", "canceled"):
            (_jobs() / f"{tag}.result.json").write_text(json.dumps(j, indent=1))
            return d
        time.sleep(interval)
    raise SystemExit(f"poll timeout [{tag}]")


def download(url, dest):
    dest = pathlib.Path(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    r = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(r, timeout=600) as resp:
        dest.write_bytes(resp.read())
    return dest


def _ext(kind, url):
    if kind != "image":
        return ".mp4"
    for e in (".png", ".jpg", ".jpeg", ".webp"):
        if e in url:
            return ".jpg" if e == ".jpeg" else e
    return ".png"


def run(kind, payload, tag, out_dir):
    """Submit, wait, download every output to out_dir/<tag>[-n].<ext>. Returns the job data
    (None if the job did not complete)."""
    jid = submit(kind, payload, tag)
    print(f"  [{tag}] job {jid}", flush=True)
    d = poll(jid, tag)
    if d.get("status") != "completed":
        print(f"  [{tag}] FAILED: {json.dumps(d)[:600]}")
        return None
    paths = []
    for i, u in enumerate(d.get("outputs") or []):
        p = pathlib.Path(out_dir) / f"{tag}{'' if i == 0 else '-' + str(i)}{_ext(kind, u)}"
        download(u, p)
        paths.append(p)
    print(f"  [{tag}] done tokens={d.get('completion_tokens')}/{d.get('total_tokens')} "
          f"-> {[str(p) for p in paths]}", flush=True)
    return d


def main():
    global JOBS
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--jobs", metavar="DIR", help=f"folder for job JSON (default {JOBS})")
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("upload", help="upload a local file, print its public URL")
    p.add_argument("file")
    for name, hlp in (("run", "submit, wait and download"), ("submit", "submit only, print the job id")):
        p = sub.add_parser(name, help=hlp)
        p.add_argument("kind", choices=["image", "video"])
        p.add_argument("payload", help="JSON file with the model's request body")
        p.add_argument("--tag", required=True, help="name for the job files and the outputs")
        if name == "run":
            p.add_argument("--out", default=".", help="folder for the outputs (default: here)")
    p = sub.add_parser("poll", help="wait for a submitted job, print its result")
    p.add_argument("job_id")
    p.add_argument("--tag", default="manual")
    p = sub.add_parser("download", help="download a URL to a file")
    p.add_argument("url")
    p.add_argument("dest")
    a = ap.parse_args()
    if a.jobs:
        JOBS = pathlib.Path(os.path.expanduser(a.jobs))

    if a.cmd == "upload":
        print(upload(a.file))
    elif a.cmd == "submit":
        print(submit(a.kind, json.loads(pathlib.Path(a.payload).read_text()), a.tag))
    elif a.cmd == "run":
        d = run(a.kind, json.loads(pathlib.Path(a.payload).read_text()), a.tag, a.out)
        sys.exit(0 if d else 1)
    elif a.cmd == "poll":
        print(json.dumps(poll(a.job_id, a.tag), indent=1)[:2000])
    elif a.cmd == "download":
        print(download(a.url, a.dest))


if __name__ == "__main__":
    main()
