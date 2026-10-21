#!/usr/bin/env python3
"""Ahrefs API v3 caller (stdlib only): scripted pulls with an API v3 key.

The Ahrefs MCP server is the default way to use Ahrefs from Claude. Use this script when you have an API v3 key
(AHREFS_API_KEY) and want repeatable pulls saved to files. Do NOT point scripts at the MCP endpoint: Ahrefs' terms
do not permit custom scripts or standalone JSON-RPC clients there. Scripted access goes through API v3.

Usage:
  ahrefs_api.py ENDPOINT [key=value ...] [--out FILE] [--body JSON]
  ahrefs_api.py site-explorer/domain-rating target=example.com date=2026-09-30
  ahrefs_api.py site-explorer-organic-keywords target=example.com date=2026-09-30 \\
      select=keyword,sum_traffic,best_position limit=100 order_by=sum_traffic:desc --out raw/seo/kw.json
  ahrefs_api.py keywords-explorer/overview country=us keywords="crm,crm software" select=keyword,volume
  ahrefs_api.py subscription-info/limits-and-usage           # free: units left this month
  ahrefs_api.py endpoints [WORD]                             # list API v3 endpoints (public spec, no key, no units)
  ahrefs_api.py params ENDPOINT                              # parameters of one endpoint

ENDPOINT is an API v3 path (site-explorer/organic-keywords) or an MCP tool name (site-explorer-organic-keywords):
the tool name is converted with the group table below, e.g. serp-overview -> serp-overview/serp-overview,
site-explorer-referring-domains -> site-explorer/refdomains. Every key=value pair becomes a query parameter;
--body sends a JSON body with POST (batch-analysis and some brand-radar endpoints).
Each call's unit cost (response header x-api-units-cost-total-actual) is printed and appended to the unit log
(AHREFS_UNITS_LOG, default ~/.local/share/marketing-agent-kit/seo/ahrefs_units.jsonl), which kw.py budget reads.
Key: AHREFS_API_KEY (environment first, then ~/.config/marketing-agent-kit/.env or MARKETING_KIT_ENV).
Reference: https://docs.ahrefs.com/api/reference · units: https://docs.ahrefs.com/api/docs/limits-consumption
"""
from __future__ import annotations

import datetime as dt
import json
import os
import pathlib
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

BASE = "https://api.ahrefs.com/v3/"
SPEC_URL = "https://docs.ahrefs.com/openapi.json"
KIT_ENV = os.environ.get("MARKETING_KIT_ENV", "~/.config/marketing-agent-kit/.env")
UNITS_LOG = os.environ.get("AHREFS_UNITS_LOG") or os.path.expanduser(
    "~/.local/share/marketing-agent-kit/seo/ahrefs_units.jsonl")
# API v3 path groups, longest first. An MCP tool name is "<group>-<endpoint>"; a tool equal to its group
# (serp-overview, batch-analysis) maps to "<group>/<group>".
GROUPS = ("competitive-analysis", "keywords-explorer", "subscription-info", "content-helper", "batch-analysis",
          "serp-overview", "site-explorer", "web-analytics", "rank-tracker", "social-media", "brand-radar",
          "management", "site-audit", "public", "gsc")
ALIASES = {"site-explorer-referring-domains": "site-explorer/refdomains",
           "site-explorer-linked-domains": "site-explorer/linkeddomains"}
_sleep = time.sleep  # replaced in tests


def env_value(raw: str) -> str:
    """Value of KEY=value: drop an inline comment (a # at the start or after a space), then quotes."""
    return re.split(r"(?:^|\s)#", raw.strip(), maxsplit=1)[0].strip().strip('"').strip("'")


def api_key(required: bool = True) -> str | None:
    """AHREFS_API_KEY: the environment first, then the kit's keys file."""
    v = os.environ.get("AHREFS_API_KEY")
    if v:
        return v
    envp = os.path.expanduser(KIT_ENV)
    if os.path.exists(envp):
        for line in open(envp):
            k, _, val = line.strip().partition("=")
            if k.strip() == "AHREFS_API_KEY" and env_value(val):
                return env_value(val)
    if not required:
        return None
    raise SystemExit(f"AHREFS_API_KEY not found. Set it in the environment or add AHREFS_API_KEY=... to {envp} "
                     "(guide: connections/ahrefs-mcp.md). Paid Ahrefs plans from Lite up include API v3 keys "
                     "(Account settings → API keys); without one, use the Ahrefs MCP tools instead.")


def api_path(name: str) -> str:
    """API v3 path for an endpoint path or an MCP tool name."""
    name = name.strip().strip("/")
    if name.startswith("v3/"):
        name = name[3:]
    if "/" in name:
        return name
    if name in ALIASES:
        return ALIASES[name]
    for g in GROUPS:
        if name == g:
            return f"{g}/{g}"
        if name.startswith(g + "-"):
            return f"{g}/{name[len(g) + 1:]}"
    raise SystemExit(f"Not an API v3 endpoint: {name}. MCP-only tools (doc, render-*, *-entities) have no API v3 "
                     "equivalent; list endpoints with: ahrefs_api.py endpoints")


def tool_name(path: str) -> str:
    """MCP-style name of an API v3 path, for logs: serp-overview/serp-overview -> serp-overview."""
    g, _, rest = api_path(path).partition("/")
    return g if rest == g else f"{g}-{rest}"


def http(method: str, url: str, headers: dict, body: bytes | None = None, timeout: int = 180):
    """One HTTP exchange -> (status, headers with lower-case names, body text). Error statuses are returned, not raised."""
    req = urllib.request.Request(url, data=body, method=method, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, {k.lower(): v for k, v in r.headers.items()}, r.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        return e.code, {k.lower(): v for k, v in (e.headers or {}).items()}, e.read().decode("utf-8", "replace")


class Response:
    def __init__(self, status: int, headers: dict, text: str, path: str):
        self.status, self.headers, self.text, self.path = status, headers, text, path

    @property
    def ok(self) -> bool:
        return self.status == 200

    def units(self) -> tuple[int, bool]:
        """(units consumed, True if Ahrefs reported it). Documented header: x-api-units-cost-total-actual;
        x-api-units-cost-total (the expected cost) is the fallback. Neither present -> (0, False)."""
        for h in ("x-api-units-cost-total-actual", "x-api-units-cost-total"):
            v = self.headers.get(h)
            if v not in (None, ""):
                try:
                    return int(float(v)), True
                except ValueError:
                    pass
        return 0, False

    def error(self) -> str:
        hint = ""
        if self.status == 401:
            hint = " (wrong key type? MCP keys do not work on API v3, and API v3 keys do not work on MCP)"
        elif self.status == 429:
            hint = " (rate limit: 60 requests per minute by default; wait and re-run)"
        return f"HTTP error {self.status}{hint}: {self.text[:600]}"


def call(endpoint: str, params: dict | None = None, key: str | None = None, body=None, retries: int = 1,
         timeout: int = 180) -> Response:
    """GET (or POST with a JSON body) one API v3 endpoint. A 429 is retried once after Retry-After (max 60 s)."""
    path = api_path(endpoint)
    q = {k: (json.dumps(v) if isinstance(v, (dict, list)) else v) for k, v in (params or {}).items()}
    url = BASE + path + ("?" + urllib.parse.urlencode(q) if q else "")
    headers = {"Authorization": f"Bearer {key or api_key()}", "Accept": "application/json"}
    data = None
    if body is not None:
        headers["Content-Type"] = "application/json"
        data = (body if isinstance(body, str) else json.dumps(body)).encode()
    for attempt in range(retries + 1):
        status, h, text = http("POST" if data is not None else "GET", url, headers, data, timeout)
        if status == 429 and attempt < retries:
            try:
                wait = float(h.get("retry-after") or 10)
            except ValueError:
                wait = 10.0
            _sleep(min(60.0, max(1.0, wait)))
            continue
        return Response(status, h, text, path)
    raise AssertionError("unreachable")


def log_units(tool: str, args: dict, units: int, reported: bool = True, path: str | None = None, **extra) -> None:
    """Append one call to a unit log (JSON lines). The keyword list is left out to keep the log small."""
    path = path or UNITS_LOG
    os.makedirs(os.path.dirname(path), exist_ok=True)
    rec = {"ts": dt.datetime.now().isoformat(timespec="seconds"), "tool": tool, "units": units,
           "args": {k: v for k, v in args.items() if k != "keywords"}, **extra}
    if not reported:
        rec["units_unreported"] = True
    with open(path, "a") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")


def _spec() -> dict:
    """The public OpenAPI spec (no key, no units), cached for 7 days next to the unit log."""
    cache = os.path.join(os.path.dirname(UNITS_LOG), "ahrefs_openapi.json")
    if not (os.path.exists(cache) and time.time() - os.path.getmtime(cache) < 7 * 86400):
        status, _, text = http("GET", SPEC_URL, {"Accept": "application/json"})
        if status != 200:
            raise SystemExit(f"Could not fetch {SPEC_URL}: HTTP {status}")
        os.makedirs(os.path.dirname(cache), exist_ok=True)
        pathlib.Path(cache).write_text(text)
    return json.load(open(cache))


def _endpoints(word: str | None) -> None:
    for p, ops in sorted(_spec()["paths"].items()):
        if not word or word in p:
            methods = ",".join(m.upper() for m in ops if m in ("get", "post", "put", "patch", "delete"))
            summary = next((o.get("summary", "") for o in ops.values() if isinstance(o, dict)), "")
            print(f"{p.strip('/'):55} {methods:10} {summary}")


def _params(endpoint: str) -> None:
    spec = _spec()
    ops = spec["paths"].get("/" + api_path(endpoint)) or sys.exit(f"Unknown endpoint: {endpoint}")
    for m, op in ops.items():
        if not isinstance(op, dict) or "parameters" not in op:
            continue
        print(f"{m.upper()} /{api_path(endpoint)}  {op.get('summary', '')}")
        for prm in op["parameters"]:
            if "$ref" in prm:
                node = spec
                for part in prm["$ref"].lstrip("#/").split("/"):
                    node = node[part]
                prm = node
            desc = (prm.get("description") or "").split("\n")[0][:110]
            print(f"  {prm['name']:28} {'required' if prm.get('required') else '':8} {desc}")


def main(argv: list[str] | None = None) -> None:
    args = list(sys.argv[1:] if argv is None else argv)
    if not args or args[0] in ("-h", "--help"):
        print(__doc__)
        return
    if args[0] == "endpoints":
        return _endpoints(args[1] if len(args) > 1 else None)
    if args[0] == "params":
        return _params(args[1]) if len(args) > 1 else sys.exit("usage: ahrefs_api.py params ENDPOINT")
    endpoint, out, body, params = args[0], None, None, {}
    i = 1
    while i < len(args):
        if args[i] in ("--out", "--body") and i + 1 < len(args):
            out, body = (args[i + 1], body) if args[i] == "--out" else (out, args[i + 1])
            i += 2
        elif "=" in args[i]:
            k, v = args[i].split("=", 1)
            params[k] = v
            i += 1
        else:
            sys.exit(f"unrecognized arg: {args[i]}")
    path = api_path(endpoint)
    r = call(path, params, body=body)
    units, reported = r.units()
    log_units(tool_name(path), params, units, reported, via="ahrefs_api.py", **({} if r.ok else {"error": r.text[:200]}))
    cache = r.headers.get("x-api-cache", "")
    print(f"units: {units}{'' if reported else ' (no unit header in the response)'}"
          + (f" · cache: {cache}" if cache else ""), file=sys.stderr)
    if not r.ok:
        sys.exit(r.error())
    try:
        data = json.loads(r.text)
    except ValueError:
        sys.exit(f"Not JSON: {r.text[:300]}")
    blob = json.dumps(data, ensure_ascii=False, indent=2)
    if out:
        pathlib.Path(out).parent.mkdir(parents=True, exist_ok=True)
        pathlib.Path(out).write_text(blob)
        rows = next((len(v) for v in data.values() if isinstance(v, list)), None) if isinstance(data, dict) else None
        print(f"saved {out}" + (f" | {rows} rows" if rows is not None else ""))
    else:
        print(blob[:8000])


if __name__ == "__main__":
    main()
