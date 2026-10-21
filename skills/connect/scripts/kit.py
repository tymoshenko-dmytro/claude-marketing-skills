#!/usr/bin/env python3
"""marketing-agent-kit setup helper: keys file, health check, MCP registration.

    kit.py init                    create the keys file (chmod 600) if missing, print its path
    kit.py open                    open the keys file in a text editor (macOS / Linux)
    kit.py doctor [--live]         tools, keys (never printed), Google login, MCP servers
    kit.py mcp list                MCP servers this helper can register
    kit.py mcp add NAME [--dry-run] [--oauth] [--scope user|project|local]

Keys live in ONE file outside any repository:
    ~/.config/marketing-agent-kit/.env     (override with MARKETING_KIT_ENV)

The user types keys into that file themselves. This script reads them and never prints
them: doctor shows "set (51 chars)", mcp add masks secrets in the command it echoes.
Keys pasted into a chat end up in session transcripts on disk — the file avoids that.
Python stdlib only.
"""
from __future__ import annotations

import argparse
import json
import os
import pathlib
import platform
import re
import shutil
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request

ENV = pathlib.Path(os.path.expanduser(os.environ.get(
    "MARKETING_KIT_ENV", "~/.config/marketing-agent-kit/.env")))
ADC = pathlib.Path.home() / ".config" / "gcloud" / "application_default_credentials.json"

# every variable doctor reports, in the order of the template
KEYS = ["PARALLEL_API_KEY", "SEARCHAPI_KEY", "AHREFS_MCP_KEY", "AHREFS_API_KEY",
        "CRUX_API_KEY", "BING_WMT_API_KEY", "SLACK_WEBHOOK_URL",
        "OPENAI_API_KEY", "ELEVENLABS_API_KEY", "ATLAS_API_KEY", "STRIPE_AGENT_KEY",
        "GOOGLE_CLOUD_PROJECT", "GA4_PROPERTY_ID", "GOOGLE_ADS_LOGIN_CUSTOMER_ID"]
SEO_DIR = pathlib.Path(os.path.expanduser(os.environ.get(
    "SEO_SKILLS_CONFIG_DIR", "~/.config/marketing-agent-kit/seo")))
VIDEO_LIBRARY = pathlib.Path(os.path.expanduser(os.environ.get(
    "VIDEO_LIBRARY", "~/.local/share/marketing-agent-kit/video-library")))

TEMPLATE = """\
# marketing-agent-kit — API keys. This file stays on your machine (chmod 600).
# Never commit it. Never paste keys into a chat: chats are saved to disk.
# Fill in only what you use; empty lines are fine. Guides: connections/<name>.md

# Research
PARALLEL_API_KEY=            # platform.parallel.ai            → connections/parallel-api.md
SEARCHAPI_KEY=               # searchapi.io dashboard          → connections/searchapi.md
AHREFS_MCP_KEY=              # Ahrefs → Account → API keys → Generate MCP key → connections/ahrefs-mcp.md
AHREFS_API_KEY=              # optional: API v3 key, Lite plan and up (scripts: ahrefs_api.py, kw.py)

# SEO (site config: ~/.config/marketing-agent-kit/seo/<site>.toml → connections/search-console.md)
CRUX_API_KEY=                # free Google Cloud key, Chrome UX Report API → connections/crux-api.md
BING_WMT_API_KEY=            # Bing Webmaster Tools → Settings → API access → connections/bing-webmaster.md
SLACK_WEBHOOK_URL=           # optional: incoming webhook for the weekly SEO post → connections/slack.md

# Creative
OPENAI_API_KEY=              # platform.openai.com/api-keys    → connections/openai-images-api.md
ELEVENLABS_API_KEY=          # elevenlabs.io/app/settings/api-keys → connections/elevenlabs-api.md
ATLAS_API_KEY=               # optional: Atlas Cloud, generated people and scenes → connections/atlas-cloud.md

# Analytics (Google uses your gcloud login, not a key — see connections/ga4-mcp.md)
GOOGLE_CLOUD_PROJECT=        # your Google Cloud project id
GA4_PROPERTY_ID=             # optional: default GA4 property for ga4.py
GOOGLE_ADS_LOGIN_CUSTOMER_ID=  # optional: manager (MCC) id, digits only
STRIPE_AGENT_KEY=            # optional: restricted key with the Agent tag, Read only → connections/stripe-mcp.md
"""


# ------------------------------------------------------------------ keys ------
def env_value(raw: str) -> str:
    """The value of KEY=value. Every script in the kit reads the keys file with this
    same rule: drop an inline comment (a # at the start or after a space), then quotes.
    The template puts a comment after every key, so a key typed in front of it must
    not swallow the comment."""
    return re.split(r"(?:^|\s)#", raw.strip(), maxsplit=1)[0].strip().strip('"').strip("'")


def read_env() -> dict:
    vals = {}
    if ENV.exists():
        for line in ENV.read_text().splitlines():
            k, sep, v = line.strip().partition("=")
            if not sep or k.startswith("#"):
                continue
            v = env_value(v)
            if v:
                vals[k.strip()] = v
    for k in list(vals) + KEYS:
        if os.environ.get(k):
            vals[k] = os.environ[k]          # env vars win over the file
    return vals


def cmd_init(_a) -> None:
    ENV.parent.mkdir(parents=True, exist_ok=True)
    if ENV.exists():
        print(f"keys file exists: {ENV}")
    else:
        ENV.write_text(TEMPLATE)
        print(f"created keys file: {ENV}")
    os.chmod(ENV, 0o600)
    try:
        os.chmod(ENV.parent, 0o700)
    except OSError:
        pass
    print("permissions: owner read/write only (600)")
    print("next: open it, paste the keys you have after the = signs, save. Then: kit.py doctor --live")


def cmd_open(_a) -> None:
    if not ENV.exists():
        cmd_init(_a)
    opener = ["open", "-t"] if platform.system() == "Darwin" else ["xdg-open"]
    if not shutil.which(opener[0]):
        sys.exit(f"open this file in any text editor: {ENV}")
    subprocess.run(opener + [str(ENV)])
    print(f"opened {ENV} — paste keys after the = signs and save")


# ---------------------------------------------------------------- doctor ------
def http(url, headers=None, data=None, method=None, timeout=20):
    req = urllib.request.Request(url, headers=headers or {}, data=data, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, r.read()
    except urllib.error.HTTPError as e:
        return e.code, e.read()
    except Exception as e:                                   # network down, DNS, TLS
        return None, str(e).encode()


def live_check(name, key):
    """Free requests that only prove the key works. Nothing is generated or billed."""
    if name == "PARALLEL_API_KEY":
        # a run id that can't exist: 404 = key accepted, 401 = key rejected
        code, _ = http("https://api.parallel.ai/v1/tasks/runs/trun_kit_doctor_check", {"x-api-key": key})
        return code == 404, {404: "accepted", 401: "rejected (401)"}.get(code, f"HTTP {code}")
    if name == "SEARCHAPI_KEY":
        code, body = http("https://www.searchapi.io/api/v1/me", {"Authorization": f"Bearer {key}"})
        if code == 200:
            try:
                d = json.loads(body)
                left = d.get("account", {}).get("remaining_credits", d.get("remaining_credits"))
                return True, f"accepted, remaining credits: {left}" if left is not None else "accepted"
            except ValueError:
                return True, "accepted"
        return False, f"HTTP {code}"
    if name == "OPENAI_API_KEY":
        code, _ = http("https://api.openai.com/v1/models", {"Authorization": f"Bearer {key}"})
        return code == 200, "accepted" if code == 200 else f"HTTP {code}"
    if name == "ELEVENLABS_API_KEY":
        code, _ = http("https://api.elevenlabs.io/v1/user", {"xi-api-key": key})
        if code == 200:
            return True, "accepted"
        return code not in (401,), "rejected (401)" if code == 401 else f"HTTP {code} (restricted key? fine if TTS works)"
    if name == "AHREFS_API_KEY":
        code, _ = http("https://api.ahrefs.com/v3/subscription-info/limits-and-usage",
                       {"Authorization": f"Bearer {key}"})
        return code == 200, "accepted" if code == 200 else f"HTTP {code}"
    if name == "CRUX_API_KEY":
        code, _ = http("https://chromeuxreport.googleapis.com/v1/records:queryRecord",
                       {"X-Goog-Api-Key": key, "Content-Type": "application/json"},
                       json.dumps({"origin": "https://www.google.com"}).encode(), "POST")
        return code == 200, "accepted" if code == 200 else f"HTTP {code} (is the Chrome UX Report API enabled?)"
    if name == "BING_WMT_API_KEY":
        # Bing Webmaster takes the key only as a query parameter
        code, body = http("https://ssl.bing.com/webmaster/api.svc/json/GetUserSites?apikey="
                          + urllib.parse.quote(key))
        if code == 200:
            try:
                return True, f"accepted, {len(json.loads(body).get('d') or [])} site(s)"
            except ValueError:
                return True, "accepted"
        return False, "rejected" if b"InvalidApiKey" in (body or b"") else f"HTTP {code}"
    if name == "ATLAS_API_KEY":
        # a job id that can't exist: 404 = key accepted, 401 = key rejected
        code, _ = http("https://api.atlascloud.ai/api/v1/model/prediction/kit_doctor_check",
                       {"Authorization": f"Bearer {key}", "Accept": "application/json",
                        "User-Agent": "Mozilla/5.0"})
        return code == 404, {404: "accepted", 401: "rejected (401)"}.get(code, f"HTTP {code}")
    return None, "checked inside Claude (/mcp) — not called from scripts"


def google_status():
    if not shutil.which("gcloud"):
        return "gcloud not installed — needed for GA4, Google Ads, BigQuery (connections/ga4-mcp.md)"
    if not ADC.exists():
        return "not logged in — run the login from connections/ga4-mcp.md"
    out = subprocess.run(["gcloud", "auth", "application-default", "print-access-token"],
                         capture_output=True, text=True, timeout=60)
    tok = out.stdout.strip()
    if out.returncode != 0 or not tok:
        return "login expired — repeat the login from connections/ga4-mcp.md (it opens a browser)"
    code, body = http("https://oauth2.googleapis.com/tokeninfo",
                      {"Content-Type": "application/x-www-form-urlencoded"},
                      urllib.parse.urlencode({"access_token": tok}).encode(), "POST")
    try:
        scopes = json.loads(body).get("scope", "").split()
    except ValueError:
        scopes = []
    short = {"analytics.readonly": "GA4", "adwords": "Google Ads", "bigquery": "BigQuery",
             "cloud-platform": "Cloud", "drive": "Drive", "spreadsheets": "Sheets"}
    have = [v for k, v in short.items() if any(s.endswith("/" + k) for s in scopes)]
    return "logged in · scopes: " + (", ".join(have) if have else "none of GA4 / Ads / BigQuery")


def claude_bin():
    for c in [shutil.which("claude"), str(pathlib.Path.home() / ".claude/local/claude"),
              str(pathlib.Path.home() / ".local/bin/claude"), "/opt/homebrew/bin/claude", "/usr/local/bin/claude"]:
        if c and pathlib.Path(c).exists():
            return c
    return None


def mcp_servers():
    cb = claude_bin()
    if not cb:
        return None
    out = subprocess.run([cb, "mcp", "list"], capture_output=True, text=True, timeout=120)
    servers = {}
    for line in out.stdout.splitlines():
        m = re.match(r"^([\w.@-]+): .*? - (.*)$", line.strip())
        if m:
            servers[m.group(1)] = m.group(2).strip()
    return servers


def version(cmd, args=("--version",)):
    p = shutil.which(cmd)
    if not p:
        return None
    try:
        out = subprocess.run([p, *args], capture_output=True, text=True, timeout=20)
        return (out.stdout or out.stderr).strip().splitlines()[0][:60]
    except Exception:
        return "installed"


def cmd_doctor(a) -> None:
    ok, warn, bad = "✓", "·", "✗"
    print("Tools")
    tools = [("python3", "all scripts", ("--version",)), ("node", "Playwright MCP (18+), HyperFrames (22+)", ("--version",)),
             ("npx", "Playwright MCP, HyperFrames", ("--version",)),
             ("ffmpeg", "video skills, ads-video-library, HyperFrames", ("-version",)),
             ("ffprobe", "video skills, ads-video-library", ("-version",)),
             ("uv", "SEO skills (gsc-insights, seo-tech-audit, ahrefs kw.py), sound-library venv", ("--version",)), ("gcloud", "GA4, Google Ads, BigQuery", ("--version",)),
             ("pipx", "GA4 MCP, Google Ads MCP", ("--version",)), ("claude", "registering MCP servers", ("--version",)),
             ("higgsfield", "Higgsfield (optional)", ("--version",))]
    for cmd, why, args in tools:
        v = version(cmd, args) if cmd != "claude" else (claude_bin() and "installed")
        print(f"  {ok if v else warn} {cmd:<11} {v or 'not found'}  — {why}")

    print(f"\nKeys  ({ENV}{'' if ENV.exists() else ' — missing, run: kit.py init'})")
    if ENV.exists():
        mode = oct(ENV.stat().st_mode & 0o777)
        if mode != "0o600":
            print(f"  {bad} permissions are {mode[2:]}, should be 600 — run: chmod 600 {ENV}")
    vals = read_env()
    for k in KEYS:
        v = vals.get(k)
        if not v:
            print(f"  {warn} {k:<29} not set")
            continue
        line = f"set ({len(v)} chars)"
        mark = ok
        if a.live and k.endswith("_KEY"):
            good, note = live_check(k, v)
            line += f" · {note}"
            mark = ok if good else (warn if good is None else bad)
        print(f"  {mark} {k:<29} {line}")
    if not a.live:
        print("  (add --live to test each key with a free request; SLACK_WEBHOOK_URL is never tested — "
              "a test would post a message)")

    print("\nSEO site configs  (" + str(SEO_DIR) + ")")
    sites = sorted(SEO_DIR.glob("*.toml")) if SEO_DIR.is_dir() else []
    if sites:
        for t in sites:
            print(f"  {ok} {t.stem}")
    else:
        print(f"  {warn} none — gsc-insights, seo-tech-audit and ahrefs kw.py need one "
              "(skills/gsc-insights/references/config.md)")

    print("\nVideo sound library  (" + str(VIDEO_LIBRARY) + ")")
    if (VIDEO_LIBRARY / "catalog" / "sfx.json").exists():
        venv = (VIDEO_LIBRARY / "tools" / ".venv" / "bin" / "python").exists()
        print(f"  {ok} installed" + ("" if venv else
              f"\n  {warn} analysis venv missing — run: python3 skills/video-sound/scripts/library.py venv"))
    else:
        print(f"  {warn} not installed — run: python3 skills/video-sound/scripts/library.py install")

    print("\nGoogle login (GA4 / Ads / BigQuery)")
    print("  " + google_status())

    print("\nMCP servers registered in Claude Code")
    servers = mcp_servers()
    if servers is None:
        print("  claude CLI not found — see connections/README.md for adding servers in the desktop app")
    elif not servers:
        print("  none yet — kit.py mcp list")
    else:
        for n, st in servers.items():
            print(f"  {ok if 'Connected' in st or '✓' in st else warn} {n:<22} {st}")


# ------------------------------------------------------------ mcp add -------
# name → how to register. "key" is the env-file variable; "auth" says what the key goes into.
MCP = {
    "ahrefs": {"url": "https://api.ahrefs.com/mcp/mcp", "key": "AHREFS_MCP_KEY",
               "header": "Authorization: Bearer {}", "oauth": True,
               "doc": "connections/ahrefs-mcp.md"},
    "parallel-search": {"url": "https://search.parallel.ai/mcp", "key": "PARALLEL_API_KEY",
                        "header": "Authorization: Bearer {}", "optional_key": True,
                        "doc": "connections/parallel-api.md"},
    "parallel-task": {"url": "https://task-mcp.parallel.ai/mcp", "key": "PARALLEL_API_KEY",
                      "header": "Authorization: Bearer {}", "oauth": True,
                      "doc": "connections/parallel-api.md"},
    "searchapi": {"url": "https://www.searchapi.io/mcp", "key": "SEARCHAPI_KEY",
                  "header": "X-MCP-Token: {}", "oauth": True, "doc": "connections/searchapi.md"},
    "stripe": {"url": "https://mcp.stripe.com", "key": "STRIPE_AGENT_KEY",
               "header": "Authorization: Bearer {}", "oauth": True, "prefer_oauth": True,
               "doc": "connections/stripe-mcp.md"},
    "elevenlabs": {"url": "https://api.elevenlabs.io/v1/mcp", "oauth_only": True,
                   "doc": "connections/elevenlabs-api.md"},
    "higgsfield": {"url": "https://mcp.higgsfield.ai/mcp", "oauth_only": True,
                   "doc": "connections/higgsfield.md"},
    "playwright": {"stdio": ["npx", "@playwright/mcp@latest", "--user-data-dir",
                             str(pathlib.Path.home() / ".config/marketing-agent-kit/playwright-profile")],
                   "doc": "connections/playwright-mcp.md"},
    "ga4": {"stdio": ["pipx", "run", "--spec", "analytics-mcp>=0.7.0", "analytics-mcp"], "google": True,
            "env": ["GOOGLE_CLOUD_PROJECT"], "doc": "connections/ga4-mcp.md"},
    "google-ads": {"stdio": ["pipx", "run", "--spec", "google-ads-mcp==0.0.4", "google-ads-mcp"], "google": True,
                   "env": ["GOOGLE_CLOUD_PROJECT", "GOOGLE_ADS_LOGIN_CUSTOMER_ID"],
                   "doc": "connections/google-ads-mcp.md"},
}


def cmd_mcp(a) -> None:
    if a.action == "list" or not a.name:
        for n, s in MCP.items():
            how = "stdio" if "stdio" in s else ("OAuth" if s.get("oauth_only") else "key or OAuth")
            print(f"  {n:<16} {how:<13} {s['doc']}")
        print("  bigquery         see connections/bigquery.md (needs your own OAuth client)")
        return
    if a.name not in MCP:
        sys.exit(f"unknown server {a.name!r} — kit.py mcp list")
    s = MCP[a.name]
    vals = read_env()
    cmd, shown = ["mcp", "add", "--scope", a.scope], ["mcp", "add", "--scope", a.scope]

    if "stdio" in s:
        envs = []
        if s.get("google"):
            if not ADC.exists():
                sys.exit(f"Google login missing ({ADC}). Do the login in {s['doc']} first.")
            envs.append(f"GOOGLE_APPLICATION_CREDENTIALS={ADC}")
            if vals.get("GOOGLE_CLOUD_PROJECT"):
                envs.append(f"GOOGLE_PROJECT_ID={vals['GOOGLE_CLOUD_PROJECT']}")
        for k in s.get("env", []):
            if vals.get(k):
                envs.append(f"{k}={vals[k]}")
        # the name goes BEFORE -e: -e takes every following argument until "--"
        cmd += [a.name]
        shown += [a.name]
        for e in envs:
            cmd += ["-e", e]
            shown += ["-e", e]
        cmd += ["--", *s["stdio"]]
        shown += ["--", *s["stdio"]]
    else:
        cmd += ["--transport", "http", a.name, s["url"]]
        shown += ["--transport", "http", a.name, s["url"]]
        key = vals.get(s.get("key", ""))
        use_key = key and not s.get("oauth_only") and not a.oauth and not (s.get("prefer_oauth") and not a.key)
        if use_key and a.scope == "project":
            # project scope writes .mcp.json into the repository, where it gets committed:
            # store a reference that Claude Code fills from the environment, never the key
            ref = s["header"].format("${" + s["key"] + "}")
            cmd += ["--header", ref]
            shown += ["--header", ref]
        elif use_key:
            cmd += ["--header", s["header"].format(key)]
            shown += ["--header", s["header"].format(f"<{s['key']} from the keys file, {len(key)} chars>")]
        elif not s.get("oauth") and not s.get("oauth_only") and not s.get("optional_key"):
            sys.exit(f"{s['key']} is not set in {ENV} — add it first ({s['doc']})")

    cb = claude_bin()
    print("command: claude " + " ".join(f'"{x}"' if " " in x else x for x in shown))
    if a.dry_run:
        return
    if not cb:
        sys.exit("claude CLI not found. In the desktop app open the built-in terminal (Ctrl+`) and run the "
                 "command above, or see connections/README.md.")
    out = subprocess.run([cb, *cmd], capture_output=True, text=True)
    msg = (out.stdout + out.stderr).strip()
    if s.get("header") and vals.get(s.get("key", "")):
        msg = msg.replace(vals[s["key"]], "••••")          # never echo a secret
    print(msg)
    if out.returncode == 0:
        if "stdio" not in s and not ("--header" in cmd):
            print("next: in Claude Code run /mcp → select the server → Authenticate (a browser opens)")
        if a.scope == "project" and "--header" in cmd:
            print(f"the key is not in .mcp.json: Claude Code reads ${{{s['key']}}} from the environment it "
                  f"starts in. Each teammate exports their own {s['key']} in their shell profile — or use "
                  "--scope local to keep the server to yourself.")
        print("restart the session (or the desktop app) so Claude picks the server up")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("init")
    sub.add_parser("open")
    d = sub.add_parser("doctor")
    d.add_argument("--live", action="store_true", help="test keys with free requests")
    m = sub.add_parser("mcp")
    m.add_argument("action", choices=["list", "add"])
    m.add_argument("name", nargs="?")
    m.add_argument("--scope", default="user", choices=["user", "project", "local"],
                   help="user = every project (default; the desktop app reads it). "
                        "project = .mcp.json in the repo, keys written as ${VAR} references")
    m.add_argument("--oauth", action="store_true", help="sign in with OAuth instead of sending the key")
    m.add_argument("--key", action="store_true", help="use the key even where OAuth is recommended (Stripe)")
    m.add_argument("--dry-run", action="store_true", help="print the command, change nothing")
    a = ap.parse_args()
    {"init": cmd_init, "open": cmd_open, "doctor": cmd_doctor, "mcp": cmd_mcp}[a.cmd](a)


if __name__ == "__main__":
    main()
