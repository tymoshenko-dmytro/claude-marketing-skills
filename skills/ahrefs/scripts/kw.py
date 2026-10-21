#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = ["google-auth>=2.30", "requests>=2.31"]
# ///
"""Staged keyword research on Ahrefs with a unit budget, SERP-overlap clustering and a GSC join.

Projects live in <data>/keywords/<project>/. Every Ahrefs response is cached and its unit cost is appended to
<data>/ahrefs_units.jsonl. Stages (run in order, inspect the output between them):

  discover   --project P --seeds "a,b" [--country us] [--per-seed 200] [--related] [--from-gsc]
             Cheap candidate list: matching terms (+ related terms) with select=keyword only (~1 unit/row),
             plus our own GSC queries containing a seed (free). No volumes yet.
  price      --project P [--country us] [--fields volume,difficulty,parent_topic,intents] [--min-volume 10] [--max N]
             Metrics for the candidates via keywords-explorer-overview in small batches (~10 units per paid field
             per row; keywords with no data cost nothing). A batch that 500s is split to find the bad keyword.
  serp       --project P [--country us] [--top 60] [--min-volume 50]
             Top-10 SERP for the biggest priced keywords (~50+ units each), cached for 14 days.
  cluster    --project P [--min-shared 3]
             Groups keywords whose top-10 organic results share >= N URLs (one page can rank for the whole group);
             summarises each SERP: page types, AI Overview, app stores, our own position.
  prioritize --project P [--sheet]
             Joins our GSC archive (current position, page, impressions) and writes report.md / clusters.csv with a
             suggested action per cluster. --sheet writes the table to the report Google Sheet.
  import     --project P [--call ID | --tool T --args JSON] FILE [FILE ...]
             Loads results of Ahrefs MCP tool calls made by the agent (see --via mcp).
  budget     Units spent this month (from the logs) and, with an API key, the account limits.

Two transports, chosen with --via (default auto: api when AHREFS_API_KEY is set, otherwise mcp):
  api  discover / price / serp call Ahrefs API v3 (AHREFS_API_KEY) themselves.
  mcp  discover / price / serp use fresh cached answers and write the calls still needed to <project>/mcp_plan.json.
       The agent makes each call with the Ahrefs MCP tool, saves the output to a file and runs
       `kw.py import --project P --call ID FILE`. Then it re-runs the stage (nothing left to plan) or moves on.
cluster and prioritize are the same for both.

Usage: kw.py STAGE [--site S] ...
"""
from __future__ import annotations

import argparse
import contextlib
import csv
import datetime as dt
import fcntl
import hashlib
import json
import os
import re
import sqlite3
import sys
import urllib.parse
from collections import Counter, defaultdict

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ahrefs_api  # noqa: E402
import seoconf  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
# Ahrefs uses ISO 3166-1 alpha-2, Search Console alpha-3 (lowercase).
GSC_COUNTRY = dict(x.split(":") for x in (
    "us:usa gb:gbr ca:can au:aus nz:nzl ie:irl in:ind pk:pak bd:bgd lk:lka np:npl id:idn my:mys sg:sgp ph:phl th:tha "
    "vn:vnm kh:khm mm:mmr jp:jpn kr:kor cn:chn tw:twn hk:hkg mo:mac mn:mng kz:kaz uz:uzb kg:kgz tj:tjk tm:tkm "
    "az:aze am:arm ge:geo tr:tur ir:irn iq:irq sy:syr lb:lbn jo:jor il:isr ps:pse sa:sau ae:are qa:qat kw:kwt "
    "bh:bhr om:omn ye:yem eg:egy ly:lby tn:tun dz:dza ma:mar sd:sdn ss:ssd et:eth ke:ken tz:tza ug:uga rw:rwa "
    "ng:nga gh:gha ci:civ sn:sen cm:cmr ao:ago za:zaf zw:zwe zm:zmb mz:moz mg:mdg so:som "
    "de:deu at:aut ch:che fr:fra be:bel nl:nld lu:lux es:esp pt:prt it:ita mt:mlt gr:grc cy:cyp "
    "pl:pol cz:cze sk:svk hu:hun ro:rou bg:bgr si:svn hr:hrv rs:srb ba:bih me:mne mk:mkd al:alb xk:xkx "
    "ua:ukr by:blr md:mda ru:rus lt:ltu lv:lva ee:est fi:fin se:swe no:nor dk:dnk is:isl "
    "mx:mex gt:gtm hn:hnd sv:slv ni:nic cr:cri pa:pan cu:cub do:dom pr:pri jm:jam ht:hti "
    "co:col ve:ven ec:ecu pe:per bo:bol cl:chl ar:arg uy:ury py:pry br:bra").split())

APP_STORES = ("apps.apple.com", "play.google.com", "microsoft.com/store", "chromewebstore.google.com", "chrome.google.com")


# ---------- Ahrefs transport (API v3, see ahrefs_api.py) ----------

EXPECTED = {  # tool -> collection that must be a list in a successful response
    "keywords-explorer-matching-terms": "keywords", "keywords-explorer-related-terms": "keywords",
    "keywords-explorer-overview": "keywords", "serp-overview": "positions"}


NUMERIC = ("volume", "global_volume", "difficulty", "traffic_potential", "parent_volume", "position", "domain_rating")
PAID_FIELDS = ("volume", "global_volume", "difficulty", "traffic_potential", "parent_volume", "intents")


def valid_rows(kind, rows) -> bool:
    """Rows must be objects; keyword rows need a string keyword; metric fields must be numbers or null."""
    if not isinstance(rows, list):
        return False
    for r in rows:
        if not isinstance(r, dict):
            return False
        if kind == "keywords" and not isinstance(r.get("keyword"), str):
            return False
        if kind == "positions" and not isinstance(r.get("position"), (int, float)):
            return False
        # every field a later stage consumes must have the right type, or be null (R212-02)
        if kind == "positions" and (
                not (r.get("type") is None or (isinstance(r["type"], list) and all(isinstance(t, str) for t in r["type"])))
                or any(r.get(f) is not None and not isinstance(r[f], str) for f in ("url", "page_type", "title"))):
            return False
        if kind == "keywords" and (
                not (r.get("intents") is None or (isinstance(r["intents"], dict)
                                                  and all(isinstance(v, (bool, int)) for v in r["intents"].values())))
                or (r.get("parent_topic") is not None and not isinstance(r["parent_topic"], str))):
            return False
        if any(f in r and r[f] is not None and (isinstance(r[f], bool) or not isinstance(r[f], (int, float)))
               for f in NUMERIC):
            return False
    return True


def bad_shape(tool, data) -> bool:
    want = EXPECTED.get(tool)
    return not isinstance(data, dict) or bool(want and not valid_rows(want, data.get(want)))


def estimate_units(args, rows) -> int:
    """Documented cost model: max(50, per-row cost x rows); per row = the fields in select and where, 10 units for
    volume-type fields and intents, 1 for the rest. Used only when Ahrefs did not report the units."""
    fields = set(f for f in str(args.get("select", "")).split(",") if f)
    try:
        w = json.loads(args["where"]) if isinstance(args.get("where"), str) else args.get("where")
        fields |= {w["field"]} if isinstance(w, dict) and "field" in w else set()
    except ValueError:
        pass
    per_row = sum(10 if f in PAID_FIELDS else 1 for f in fields) or 1
    return max(50, per_row * rows)


class Ahrefs:
    def __init__(self, cfg):
        self.cfg = cfg
        self.log = os.path.join(seoconf.data_dir(cfg), "ahrefs_units.jsonl")
        self.cache = sqlite3.connect(os.path.join(seoconf.data_dir(cfg), "ahrefs_cache.sqlite"))
        self.cache.execute("CREATE TABLE IF NOT EXISTS c(k TEXT PRIMARY KEY, day TEXT, body TEXT)")

    def month_units(self):
        if not os.path.exists(self.log):
            return 0
        m = dt.date.today().strftime("%Y-%m")
        return sum(j.get("units", 0) for j in map(json.loads, open(self.log)) if j.get("ts", "").startswith(m))

    def _log(self, tool, args, units, error=None, reported=True, **extra):
        ahrefs_api.log_units(tool, args, units, reported, path=self.log,
                             **({"error": error[:200]} if error else {}), **extra)

    def key(self, tool, args):
        return tool + json.dumps(args, sort_keys=True)

    def fresh(self, k, max_age_days=30):
        row = self.cache.execute("SELECT day FROM c WHERE k=?", (k,)).fetchone()
        return bool(row) and (dt.date.today() - dt.date.fromisoformat(row[0])).days <= max_age_days

    def cached(self, tool, args, max_age_days=30):
        """The cached answer for exactly this request when it is fresh, else None. Costs nothing."""
        row = self.cache.execute("SELECT day, body FROM c WHERE k=?", (self.key(tool, args),)).fetchone()
        if row and (dt.date.today() - dt.date.fromisoformat(row[0])).days <= max_age_days:
            return json.loads(row[1])
        return None

    def store(self, k, data):
        self.cache.execute("INSERT OR REPLACE INTO c VALUES(?,?,?)", (k, dt.date.today().isoformat(), json.dumps(data)))
        self.cache.commit()

    @contextlib.contextmanager
    def _ledger(self):
        """Exclusive lock over the unit log and the open reservations (works across threads and processes)."""
        with open(self.log + ".lock", "a") as lk:
            fcntl.flock(lk, fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(lk, fcntl.LOCK_UN)

    def _reservations(self):
        p = self.log + ".reserved"
        return json.load(open(p)) if os.path.exists(p) else {}

    def _set_reservations(self, r):
        json.dump(r, open(self.log + ".reserved", "w"))

    def cap(self):
        return int(self.cfg.get("keywords", {}).get("monthly_unit_cap", 0) or 0)

    def check_cap(self, est, what="this call"):
        """Exit when the monthly cap cannot take `est` more units. Returns (used, reserved)."""
        used, pending = self.month_units(), sum(self._reservations().values())
        if self.cap() and est and used + pending + est > self.cap():
            sys.exit(f"Ahrefs unit cap: {used} used + {pending} reserved + ~{est} for {what} > {self.cap()}. "
                     "Raise [keywords].monthly_unit_cap or shrink the request.")
        return used, pending

    def reserve(self, est):
        """Atomically reserve `est` units against the monthly cap before dispatch (RA35-19). Returns a token."""
        if not self.cap() or not est:
            return None
        with self._ledger():
            self.check_cap(est)
            res = self._reservations()
            tok = f"{os.getpid()}-{id(object())}-{dt.datetime.now().timestamp()}"
            res[tok] = est
            self._set_reservations(res)
            return tok

    def release(self, tok):
        if tok is None:
            return
        with self._ledger():
            res = self._reservations()
            res.pop(tok, None)
            self._set_reservations(res)

    def call(self, tool, args, max_age_days=30, est=50):
        """Cached, budgeted API v3 call. `est` = conservative cost reserved before dispatch; 0 for free tools (RA35-24)."""
        k = self.key(tool, args)
        hit = self.cached(tool, args, max_age_days)
        if hit is not None:
            return hit
        key = ahrefs_api.api_key()
        tok = self.reserve(est)
        try:
            r = ahrefs_api.call(tool, args, key=key)
            units, reported = r.units()
            data = None
            if r.ok:
                try:
                    data = json.loads(r.text)
                except ValueError:
                    data = None
            # the expected collection must be a list of well-formed rows (RA35-20, R958-04)
            if not r.ok or bad_shape(tool, data):
                err = seoconf.redact(r.error() if not r.ok else r.text)[:300] or "no data"
                with self._ledger():
                    self._log(tool, args, units, error=err, reported=reported)  # billed failures still count (R69F-35)
                raise RuntimeError(f"{tool}: {err}")  # never cached as data (R69F-36)
            with self._ledger():
                self._log(tool, args, units, reported=reported)
            self.store(k, data)
            return data
        finally:
            self.release(tok)


def transport(a):
    """'api' or 'mcp' for this run; auto picks api when an API v3 key is available."""
    via = a.via
    if via == "auto":
        via = "api" if ahrefs_api.api_key(required=False) else "mcp"
        print(f"Ahrefs transport: {'API v3 (AHREFS_API_KEY)' if via == 'api' else 'MCP plan (no AHREFS_API_KEY)'}",
              file=sys.stderr)
    return via


# ---------- MCP plan ----------

def plan_file(d):
    return os.path.join(d, "mcp_plan.json")


def write_plan(ah, d, stage, calls, project):
    """Replace this stage's calls in <project>/mcp_plan.json and print what the agent should do next."""
    if not calls:
        return
    est = sum(c["est"] for c in calls)
    used, _ = ah.check_cap(est, f"this plan ({len(calls)} calls)")
    plan = {c["id"]: c for c in load(plan_file(d), {}).get("calls", []) if not c["id"].startswith(stage + "-")}
    for i, c in enumerate(calls, 1):
        c["id"] = f"{stage}-{i:03d}"
        plan[c["id"]] = c
    save(plan_file(d), {"updated": dt.datetime.now().isoformat(timespec="seconds"), "calls": list(plan.values())})
    print(f"\nMCP plan: {len(calls)} {stage} call(s), worst case ~{est} units (logged this month: {used}). "
          f"Saved to {plan_file(d)}.\nFor each call: run the Ahrefs MCP tool (mcp__ahrefs__<tool>) with exactly these "
          f"arguments, one call at a time, save its JSON output to a file, then run:\n"
          f"  kw.py import --project {project} --call <id> <file>\nThen re-run `{stage}` (it finds the answers in "
          f"the cache) and continue.")
    for c in calls[:30]:
        print(f"  {c['id']}  {c['tool']}  {json.dumps(c['arguments'], ensure_ascii=False)}")
    if len(calls) > 30:
        print(f"  ... {len(calls) - 30} more in the plan file")


def mcp_call(tool, args, est):
    return {"tool": tool, "arguments": args, "est": est}


# ---------- project files ----------

def pdir(cfg, project):
    return seoconf.data_dir(cfg, "keywords", re.sub(r"[^\w.-]+", "-", project))


def load(path, default):
    return json.load(open(path)) if os.path.exists(path) else default


def save(path, obj):
    json.dump(obj, open(path, "w"), ensure_ascii=False, indent=1)


def gsc_db(cfg):
    p = os.path.join(seoconf.expand(cfg["data"]["dir"]), "gsc.sqlite")
    return sqlite3.connect(p) if os.path.exists(p) else None


# ---------- applying answers (shared by both transports) ----------

def add_candidates(cand, data, source):
    for k in data.get("keywords", []):
        cand.setdefault(k["keyword"], {"sources": []})["sources"].append(source)


def overview_args(batch, country, fields, where):
    args = {"keywords": ",".join(batch), "country": country, "select": ",".join(["keyword"] + fields)}
    if where:
        args["where"] = where
    return args


def apply_overview(priced, batch, rows, ck, req, country):
    got = {r["keyword"]: r for r in rows}
    for kw in batch:
        if kw in got:
            priced[f"{kw}|{country}"] = {**got[kw], "_req": req, "_ck": ck}
        else:  # no data or below the floor
            priced[f"{kw}|{country}"] = {"keyword": kw, "no_data_or_below_floor": True, "_req": req, "_ck": ck}


def serp_args(keyword, country):
    return {"keyword": keyword, "country": country, "top_positions": 10,
            "select": "position,url,title,page_type,domain_rating,type"}


# ---------- stages ----------

def discover(cfg, a):
    ah = Ahrefs(cfg)
    via = transport(a)
    d = pdir(cfg, a.project)
    cand = load(os.path.join(d, "candidates.json"), {})
    seeds = [s.strip() for s in a.seeds.split(",") if s.strip()]
    plan = []
    for s in seeds:
        calls = [("keywords-explorer-matching-terms", "matching",
                  {"keywords": s, "country": a.country, "limit": a.per_seed, "select": "keyword"})]
        if a.related:
            calls.append(("keywords-explorer-related-terms", "related",
                          {"keywords": s, "country": a.country, "limit": a.per_seed, "select": "keyword", "terms": "all"}))
        for tool, label, args in calls:
            r = ah.call(tool, args, est=max(50, a.per_seed)) if via == "api" else ah.cached(tool, args)
            if r is None:
                plan.append(mcp_call(tool, args, max(50, a.per_seed)))
                continue
            add_candidates(cand, r, f"{label}:{s}")
        cand.setdefault(s, {"sources": []})["sources"].append("seed")
    con = gsc_db(cfg)
    if a.from_gsc and con:
        rx = re.compile("|".join(re.escape(s) for s in seeds), re.I)
        c3 = GSC_COUNTRY.get(a.country)
        if not c3:  # never fall back to worldwide queries (RA35-22)
            print(f"--from-gsc skipped: market '{a.country}' has no Search Console country mapping", file=sys.stderr)
        for (q,) in (con.execute("SELECT DISTINCT query FROM query_daily WHERE date >= date('now','-90 days') AND country=?",
                                 (c3,)) if c3 else []):
            if rx.search(q):
                cand.setdefault(q, {"sources": []})["sources"].append("gsc")
    for v in cand.values():
        v["sources"] = sorted(set(v["sources"]))
    save(os.path.join(d, "candidates.json"), cand)
    print(f"{len(cand)} candidates in {d}/candidates.json; units this month: {ah.month_units()}")
    write_plan(ah, d, "discover", plan, a.project)


def is_poison(e) -> bool:
    """Only Ahrefs' keyword-specific 500 isolates a keyword. Operational errors win: rate limits, auth, timeouts and
    other statuses stay retryable even when their text contains '500' (RA35-21)."""
    t = str(e).lower()
    if re.search(r"\b(429|401|403|408|502|503|504)\b|too many requests|rate limit|timeout|timed out|unauthori[sz]ed|forbidden", t):
        return False
    return "internal server error" in t or re.search(r"(^|http error |status[: ]+)500\b", t.strip()) is not None


def price(cfg, a):
    ah = Ahrefs(cfg)
    via = transport(a)
    d = pdir(cfg, a.project)
    cand = load(os.path.join(d, "candidates.json"), {}) or sys.exit("Run discover first.")
    priced = load(os.path.join(d, "priced.json"), {})
    fields = [f for f in a.fields.split(",") if f]

    def stale(k):  # re-price when fields were added or the floor was lowered (R69F-32)
        e = priced.get(f"{k}|{a.country}")
        if not e:
            return True
        req = e.get("_req", {"fields": [], "floor": 0})
        if set(fields) - set(req["fields"]):
            return True
        if not ah.fresh(e.get("_ck", ""), 30):  # metrics expire with the transport cache (RA35-18)
            return True
        return bool(e.get("no_data_or_below_floor")) and a.min_volume < req.get("floor", 0)
    rank = lambda k: min({"seed": 0, "gsc": 1}.get(x.split(":")[0], 2) for x in cand[k]["sources"] or ["x"])  # noqa: E731
    todo = sorted((k for k in cand if stale(k)), key=rank)[: a.max or None]
    per_row = sum(10 if f in PAID_FIELDS else 1 for f in fields) + 1
    print(f"Pricing {len(todo)} keywords ({a.country}); worst case ~{per_row * len(todo)} units "
          f"(only keywords with data are billed). Units this month so far: {ah.month_units()}")
    if a.dry_run:
        return
    where = json.dumps({"field": "volume", "is": ["gte", a.min_volume]}) if a.min_volume and "volume" in fields else None
    bad = []
    req = {"fields": sorted(fields), "floor": a.min_volume}
    size = a.batch or (20 if via == "api" else 5)

    if via == "mcp":  # fresh cached batches apply now; the rest become the plan
        plan = []
        for i in range(0, len(todo), size):
            batch = todo[i:i + size]
            args = overview_args(batch, a.country, fields, where)
            hit = ah.cached("keywords-explorer-overview", args)
            if hit is None:
                plan.append(mcp_call("keywords-explorer-overview", args, max(50, per_row * len(batch))))
            else:
                apply_overview(priced, batch, hit.get("keywords", []), ah.key("keywords-explorer-overview", args), req,
                               a.country)
        save(os.path.join(d, "priced.json"), priced)
        write_plan(ah, d, "price", plan, a.project)
        return

    def run(batch):
        """{keyword: (row or None, cache key of the request that answered it, poison)} (R958-05)."""
        args = overview_args(batch, a.country, fields, where)
        k = ah.key("keywords-explorer-overview", args)
        try:
            rows = ah.call("keywords-explorer-overview", args, est=max(50, per_row * len(batch))).get("keywords", [])
        except SystemExit:
            raise
        except Exception as e:  # noqa: BLE001
            if not is_poison(e):
                raise
            if len(batch) == 1:
                bad.append(batch[0])
                return {batch[0]: (None, k, True)}
            mid = len(batch) // 2
            return {**run(batch[:mid]), **run(batch[mid:])}
        got = {r["keyword"]: r for r in rows}
        return {kw: (got.get(kw), k, False) for kw in batch}

    try:
        for i in range(0, len(todo), size):
            batch = todo[i:i + size]
            for k, (row, key, poison) in run(batch).items():
                if row is not None:
                    priced[f"{k}|{a.country}"] = {**row, "_req": req, "_ck": key}
                else:  # no data, below the floor, or an isolated poison keyword
                    priced[f"{k}|{a.country}"] = {"keyword": k, "no_data_or_below_floor": True, "_req": req, "_ck": key,
                                                  **({"poison": True} if poison else {})}
            if (i // size) % 10 == 0:
                print(f"  {min(i + size, len(todo))}/{len(todo)}", flush=True)
    finally:
        save(os.path.join(d, "priced.json"), priced)  # keep finished batches even when a later one fails
    n = sum(1 for v in priced.values() if not v.get("no_data_or_below_floor"))
    print(f"Priced: {n} with data. Poison keywords skipped: {bad[:10]}. Units this month: {ah.month_units()}")


def classify_serp(positions, hosts):
    org = [p for p in positions if "organic" in (p.get("type") or []) and p.get("url")]
    org = sorted(org, key=lambda p: p["position"])[:10]
    types = Counter()
    for p in org:
        pt = (p.get("page_type") or "").split(",")[0]
        root = pt.split("/")[1] if pt.startswith("/") and len(pt.split("/")) > 1 else "Unknown"
        u = p["url"]
        if any(s in u for s in APP_STORES):
            root = "App_Store"
        types[root] += 1
    ours = [p for p in org if urllib.parse.urlsplit(p["url"]).netloc in hosts]
    return {"no_serp": not positions, "urls": [p["url"] for p in org], "page_types": dict(types.most_common()),
            "ai_overview": any("ai_overview" in (p.get("type") or []) for p in positions),
            "our_position": ours[0]["position"] if ours else None, "our_url": ours[0]["url"] if ours else None}


def serp(cfg, a):
    ah = Ahrefs(cfg)
    via = transport(a)
    d = pdir(cfg, a.project)
    priced = load(os.path.join(d, "priced.json"), {}) or sys.exit("Run price first.")
    serps = load(os.path.join(d, "serps.json"), {})
    rows = [v for k, v in priced.items() if k.endswith(f"|{a.country}") and (v.get("volume") or 0) >= a.min_volume]
    rows.sort(key=lambda r: -(r.get("volume") or 0))
    todo = [r["keyword"] for r in rows[: a.top]]  # every SERP goes through the 14-day cache (R69F-33)
    print(f"{len(todo)} SERPs (fresh ones come from the 14-day cache for free, others ~50-60 units each). "
          f"Units this month so far: {ah.month_units()}")
    if a.dry_run:
        return
    hosts = set(cfg["site"]["hosts"])
    plan = []
    for i, k in enumerate(todo, 1):
        args = serp_args(k, a.country)
        r = ah.call("serp-overview", args, max_age_days=14, est=60) if via == "api" else ah.cached("serp-overview", args, 14)
        if r is None:
            plan.append(mcp_call("serp-overview", args, 60))
            continue
        serps[f"{k}|{a.country}"] = {**classify_serp(r.get("positions", []), hosts), "fetched": dt.date.today().isoformat()}
        if i % 10 == 0:
            save(os.path.join(d, "serps.json"), serps)
            print(f"  {i}/{len(todo)}", flush=True)
    save(os.path.join(d, "serps.json"), serps)
    print(f"{len(serps)} SERPs stored. Units this month: {ah.month_units()}")
    write_plan(ah, d, "serp", plan, a.project)


def cluster(cfg, a):
    d = pdir(cfg, a.project)
    serps = load(os.path.join(d, "serps.json"), {}) or sys.exit("Run serp first.")
    priced = load(os.path.join(d, "priced.json"), {})
    nodata = [k for k in serps if (serps[k].get("no_serp") or not serps[k]["urls"])]
    keys = [k for k in serps if k not in nodata]
    if nodata:
        print(f"{len(nodata)} keywords have no SERP in Ahrefs (too little data); kept as single rows: "
              f"{[k.split('|')[0] for k in nodata][:10]}")
    parent = {k: k for k in keys}

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x
    sets = {k: set(serps[k]["urls"]) for k in keys}
    country = lambda k: k.rsplit("|", 1)[1]  # noqa: E731
    for i, x in enumerate(keys):
        for y in keys[i + 1:]:
            if country(x) == country(y) and len(sets[x] & sets[y]) >= a.min_shared:  # never across markets (R69F-38)
                parent[find(x)] = find(y)
    groups = defaultdict(list)
    for k in keys:
        groups[find(k)].append(k)
    vol = lambda k: priced.get(k, {}).get("volume") or 0  # noqa: E731
    out = []
    for members in groups.values():
        members.sort(key=lambda k: -vol(k))
        head = members[0]
        pt = Counter()
        for k in members:
            pt.update(serps[k]["page_types"])
        kd = [priced.get(k, {}).get("difficulty") for k in members if priced.get(k, {}).get("difficulty") is not None]
        intents = Counter()
        for k in members:
            for name, on in (priced.get(k, {}).get("intents") or {}).items():
                intents[name] += int(bool(on))
        ranked = [(serps[k]["our_position"], serps[k]["our_url"]) for k in members if serps[k].get("our_position")]
        best = min(ranked) if ranked else (None, None)  # position and URL from the same ranking (R69F-43)
        out.append({"head": head.rsplit("|", 1)[0], "country": country(head), "keywords": [k.rsplit("|", 1)[0] for k in members],
                    "volume": sum(vol(k) for k in members), "kd_avg": round(sum(kd) / len(kd)) if kd else None,
                    "serp_page_types": dict(pt.most_common()),  # full distribution; truncate only for display (R69F-42)
                    "ai_overview": any(serps[k]["ai_overview"] for k in members),
                    "intents": dict(intents.most_common()), "our_position": best[0], "our_url": best[1]})
    for k in nodata:  # demand without an Ahrefs SERP stays in the report as a singleton
        pv = priced.get(k, {})
        out.append({"head": k.rsplit("|", 1)[0], "country": country(k), "keywords": [k.rsplit("|", 1)[0]],
                    "volume": pv.get("volume") or 0, "kd_avg": pv.get("difficulty"), "serp_page_types": {},
                    "ai_overview": False, "no_serp": True,
                    "intents": {n: int(bool(v)) for n, v in (pv.get("intents") or {}).items()},
                    "our_position": None, "our_url": None})
    out.sort(key=lambda c: -c["volume"])
    save(os.path.join(d, "clusters.json"), out)
    print(f"{len(out)} clusters from {len(keys)} SERPs (shared top-10 URLs >= {a.min_shared}). {d}/clusters.json")


def action(c):
    pt = c["serp_page_types"]
    total = sum(pt.values()) or 1
    top, n = (max(pt.items(), key=lambda x: x[1]) if pt else ("Unknown", 0))
    if pt.get("App_Store", 0) / total >= 0.5:
        return "skip: SERP is app stores"
    if c.get("gsc_position") and c["gsc_position"] <= 3:
        return "hold: we already rank top 3"
    if c.get("gsc_position") and c["gsc_position"] <= 20:
        return f"improve existing page ({c.get('gsc_page')})"
    if c.get("our_position"):
        return f"improve existing page ({c.get('our_url')})"
    if c.get("no_serp"):
        return "no SERP in Ahrefs: check Google by hand"
    if top == "Article":
        return "new article"
    if top in ("Landing_Page", "Product_Page", "Homepage"):
        return "landing page (new or extend a solution page)"
    return f"check SERP manually (mostly {top})"


def prioritize(cfg, a):
    d = pdir(cfg, a.project)
    cl = load(os.path.join(d, "clusters.json"), []) or sys.exit("Run cluster first.")
    con = gsc_db(cfg)
    for c in cl:
        c["gsc_position"] = c["gsc_page"] = c["gsc_impressions_90d"] = None
        c["gsc_complete"], c["gsc_note"] = None, None
        if con and not GSC_COUNTRY.get(c.get("country", "")):
            c["gsc_note"] = f"market '{c.get('country')}' has no Search Console country mapping; GSC join withheld"
        elif con:
            qs = c["keywords"]
            last = con.execute("SELECT MAX(date) FROM pull_log WHERE final=1").fetchone()[0]
            c3 = GSC_COUNTRY[c["country"]]
            nfin = con.execute("SELECT COUNT(*) FROM pull_log WHERE final=1 AND date > date(?, '-90 days') AND date <= ?",
                               (last, last)).fetchone()[0] if last else 0
            c["gsc_complete"] = nfin == 90  # RA35-23
            if not c["gsc_complete"]:
                c["gsc_note"] = f"partial GSC history: {nfin}/90 final days"
            # exactly 90 final days, in the cluster's market (R69F-39, R69F-40)
            r = con.execute(f"""SELECT page, SUM(impressions), SUM(pos_x_impr)/SUM(impressions) FROM query_daily
                                WHERE date > date(?, '-90 days') AND date <= ?
                                  AND date IN (SELECT date FROM pull_log WHERE final=1)
                                  AND country=?
                                  AND query IN ({','.join('?' * len(qs))})
                                GROUP BY page ORDER BY SUM(impressions) DESC LIMIT 1""",
                            [last, last, c3] + qs).fetchone() if last else None
            if r:
                c["gsc_page"], c["gsc_impressions_90d"], c["gsc_position"] = r[0], r[1], round(r[2], 1)
        commercial = (c["intents"].get("commercial", 0) + c["intents"].get("transactional", 0)) > 0
        ease = 1 - (50 if c["kd_avg"] is None else c["kd_avg"]) / 100  # KD 0 is real, not missing (R69F-41)
        c["score"] = round(c["volume"] * ease * (1.0 if commercial else 0.5))
        c["action"] = action(c)
    cl.sort(key=lambda c: -c["score"])
    save(os.path.join(d, "clusters.json"), cl)
    cols = ["head", "country", "volume", "kd_avg", "score", "action", "serp_page_types", "ai_overview", "intents",
            "gsc_position", "gsc_page", "gsc_impressions_90d", "gsc_note", "keywords"]
    with open(os.path.join(d, "clusters.csv"), "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(cols)
        for c in cl:
            w.writerow([json.dumps(c[k], ensure_ascii=False) if isinstance(c[k], (dict, list)) else c[k] for k in cols])
    L = [f"# Keyword clusters · {a.project}", "",
         "score = cluster volume x (1 - avg KD/100) x (1.0 commercial/transactional, 0.5 otherwise). It ranks, it does not "
         "forecast traffic. Actions are suggestions from the SERP page types and our GSC position; check each SERP before writing. "
         "* = GSC position from partial history or withheld (see gsc_note in clusters.csv).", "",
         "| Head keyword | Vol | KD | Score | Action | SERP types | AIO | Our GSC pos | Keywords |", "|---|---|---|---|---|---|---|---|---|"]
    for c in cl[:60]:
        L.append(f"| {c['head']} | {c['volume']} | {c['kd_avg']} | {c['score']} | {c['action']} | "
                 f"{', '.join(f'{k} {v}' for k, v in list(c['serp_page_types'].items())[:4])} | {'yes' if c['ai_overview'] else ''} | "
                 f"{c['gsc_position'] or ''}{' *' if c.get('gsc_note') else ''} | {len(c['keywords'])} |")
    open(os.path.join(d, "report.md"), "w").write("\n".join(L) + "\n")
    print(f"{d}/report.md and clusters.csv ({len(cl)} clusters)")
    if a.sheet and cfg.get("report", {}).get("sheet_id"):
        sys.path.insert(0, os.path.join(HERE, "..", "..", "gsc-insights", "scripts"))
        from sheets import Sheet  # noqa: PLC0415
        rows = [cols] + [[json.dumps(c[k], ensure_ascii=False) if isinstance(c[k], (dict, list)) else ("" if c[k] is None else c[k])
                          for k in cols] for c in cl]
        Sheet(cfg, cfg["report"]["sheet_id"]).overwrite(f"KW {a.project}"[:90], rows)
        print("Sheet tab written:", f"KW {a.project}")


def _json_values(text):
    """Every JSON value in a text that holds one or more JSON documents (MCP outputs often hold two)."""
    dec, i, out = json.JSONDecoder(), 0, []
    while i < len(text):
        while i < len(text) and text[i] in " \t\r\n,":
            i += 1
        if i >= len(text):
            break
        try:
            v, i = dec.raw_decode(text, i)
        except ValueError:
            return out
        out.append(v)
    return out


def read_result(path):
    """(wrapper or None, data, units reported by Ahrefs or None, error text or None) from a saved MCP tool output.

    Accepted: the bare JSON the tool returned ({"keywords": [...]} or {"positions": [...]}), the raw MCP result
    ({"content": [{"type": "text", "text": "..."}]}) or a list of its content blocks, text with several JSON
    documents (data + {"apiUsageCosts": ...}), or a wrapper {"tool": ..., "arguments": {...}, "result": ...}."""
    found = {"wrapper": None, "data": None, "units": None, "error": None}

    def visit(o):
        if isinstance(o, str):
            for v in _json_values(o):
                visit(v)
        elif isinstance(o, list):
            for v in o:
                visit(v)
        elif isinstance(o, dict):
            if "result" in o and ("tool" in o or "arguments" in o):
                found["wrapper"] = o
                visit(o["result"])
            elif "apiUsageCosts" in o:
                u = (o["apiUsageCosts"] or {}).get("units-cost-total-actual")
                found["units"] = u if isinstance(u, (int, float)) and not isinstance(u, bool) else found["units"]
            elif isinstance(o.get("content"), list):
                if o.get("isError"):
                    found["error"] = json.dumps(o["content"])[:300]
                visit(o["content"])
            elif o.get("type") == "text" and isinstance(o.get("text"), str):
                visit(o["text"])
            elif found["data"] is None and ("keywords" in o or "positions" in o):
                found["data"] = o
            elif "error" in o and found["data"] is None:
                found["error"] = str(o["error"])[:300]
    with open(path, encoding="utf-8") as f:
        visit(f.read())
    return found["wrapper"], found["data"], found["units"], found["error"]


def import_results(cfg, a):
    """Load saved Ahrefs MCP outputs into the project exactly as if the API transport had fetched them."""
    if not a.files:
        sys.exit("import needs one or more saved MCP outputs: kw.py import --project P --call ID FILE")
    if a.call and len(a.files) > 1:
        sys.exit("--call names one planned call: import its file alone")
    ah = Ahrefs(cfg)
    d = pdir(cfg, a.project)
    plan = {c["id"]: c for c in load(plan_file(d), {}).get("calls", [])}
    done = load(os.path.join(d, "imported.json"), {})
    cand = load(os.path.join(d, "candidates.json"), {})
    priced = load(os.path.join(d, "priced.json"), {})
    serps = load(os.path.join(d, "serps.json"), {})
    counts = Counter()
    for path in a.files:
        digest = hashlib.sha256(open(path, "rb").read()).hexdigest()
        if digest in done:
            print(f"{path}: already imported ({done[digest]['call'] or done[digest]['tool']}), skipped")
            continue
        wrapper, data, units, error = read_result(path)
        planned = plan.get(a.call) if a.call else None
        if a.call and not planned:
            sys.exit(f"--call {a.call} is not in {plan_file(d)}; re-run the stage to write the plan")
        tool = (wrapper or {}).get("tool") or (planned or {}).get("tool") or a.tool
        args = (wrapper or {}).get("arguments") or (planned or {}).get("arguments") or (json.loads(a.args) if a.args else None)
        tool = (tool or "").removeprefix("mcp__ahrefs__")
        if tool not in EXPECTED or not isinstance(args, dict):
            sys.exit(f"{path}: say which call this is: --call ID from the plan, or --tool "
                     f"({', '.join(EXPECTED)}) with --args '<the JSON arguments you sent>'")
        if error or bad_shape(tool, data):
            sys.exit(f"{path}: not a usable {tool} result ({seoconf.redact(error) if error else 'unexpected shape'}); "
                     "nothing imported. Re-run the call, or for a pricing batch that failed with an internal server "
                     "error, re-plan with a smaller --batch.")
        rows = data[EXPECTED[tool]]
        country = str(args.get("country", a.country)).lower()
        if units is None:
            units_est = estimate_units(args, len(rows))
            with ah._ledger():
                ah._log(tool, args, units_est, reported=False, via="mcp-import", units_estimated=True)
        else:
            with ah._ledger():
                ah._log(tool, args, int(units), via="mcp-import")
        ck = ah.key(tool, args)
        ah.store(ck, data)  # the stage re-run finds it fresh; API runs reuse it too
        if tool in ("keywords-explorer-matching-terms", "keywords-explorer-related-terms"):
            label = "matching" if tool.endswith("matching-terms") else "related"
            for s in [s.strip() for s in str(args.get("keywords", "")).split(",") if s.strip()]:
                add_candidates(cand, data, f"{label}:{s}")
                cand.setdefault(s, {"sources": []})["sources"].append("seed")
            counts["candidates"] += len(rows)
        elif tool == "keywords-explorer-overview":
            fields = [f for f in str(args.get("select", "")).split(",") if f and f != "keyword"]
            floor = 0
            try:
                w = json.loads(args["where"]) if isinstance(args.get("where"), str) else args.get("where")
                if isinstance(w, dict) and w.get("field") == "volume" and (w.get("is") or [None])[0] == "gte":
                    floor = int(w["is"][1])
            except (ValueError, TypeError, IndexError):
                pass
            batch = [k.strip() for k in str(args.get("keywords", "")).split(",") if k.strip()]
            apply_overview(priced, batch, rows, ck, {"fields": sorted(fields), "floor": floor}, country)
            counts["priced"] += len(batch)
        else:
            kw = str(args.get("keyword", ""))
            serps[f"{kw}|{country}"] = {**classify_serp(rows, set(cfg["site"]["hosts"])),
                                        "fetched": dt.date.today().isoformat()}
            counts["serps"] += 1
        done[digest] = {"file": os.path.basename(path), "call": a.call, "tool": tool,
                        "ts": dt.datetime.now().isoformat(timespec="seconds")}
        print(f"{path}: {tool}, {len(rows)} rows, "
              + (f"{units} units" if units is not None else f"~{estimate_units(args, len(rows))} units (estimated: "
                 "the saved output has no apiUsageCosts)"))
    for v in cand.values():
        v["sources"] = sorted(set(v["sources"]))
    save(os.path.join(d, "candidates.json"), cand)
    save(os.path.join(d, "priced.json"), priced)
    save(os.path.join(d, "serps.json"), serps)
    save(os.path.join(d, "imported.json"), done)
    print(f"Imported: {dict(counts) or 'nothing new'}. Units this month: {ah.month_units()}")


def budget(cfg, a):
    ah = Ahrefs(cfg)
    by_tool = Counter()
    m = dt.date.today().strftime("%Y-%m")
    if os.path.exists(ah.log):
        for l in open(ah.log):
            j = json.loads(l)
            if j["ts"].startswith(m):
                by_tool[j["tool"]] += j["units"]
    raw = ahrefs_api.UNITS_LOG
    if os.path.exists(raw):
        for l in open(raw):
            j = json.loads(l)
            if j.get("ts", "").startswith(m):
                by_tool[j["tool"] + " (raw)"] += j.get("units", 0)
    print(f"Units logged this month ({m}): {sum(by_tool.values())}  {dict(by_tool)}")
    if not ahrefs_api.api_key(required=False):
        print("No AHREFS_API_KEY: check the account's units with the free MCP tool subscription-info-limits-and-usage.")
        return
    r = ah.call("subscription-info-limits-and-usage", {}, max_age_days=0, est=0)  # free tool, never capped (RA35-24)
    print(json.dumps(r, indent=1))


STAGES = {"discover": discover, "price": price, "serp": serp, "cluster": cluster, "prioritize": prioritize,
          "import": import_results, "budget": budget}


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("stage", choices=list(STAGES))
    ap.add_argument("files", nargs="*", help="import: saved MCP outputs")
    ap.add_argument("--site")
    ap.add_argument("--project")
    ap.add_argument("--via", choices=["auto", "api", "mcp"], default="auto")
    ap.add_argument("--seeds", default="")
    ap.add_argument("--country")
    ap.add_argument("--per-seed", type=int, default=200)
    ap.add_argument("--related", action="store_true")
    ap.add_argument("--from-gsc", action="store_true")
    ap.add_argument("--fields", default="volume,difficulty,parent_topic,intents")
    ap.add_argument("--min-volume", type=int, default=10)
    ap.add_argument("--max", type=int, default=0)
    ap.add_argument("--batch", type=int, help="keywords per pricing call (default 20 via api, 5 via mcp)")
    ap.add_argument("--top", type=int, default=60)
    ap.add_argument("--min-shared", type=int, default=3)
    ap.add_argument("--sheet", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--call", help="import: the plan id of the call this file answers")
    ap.add_argument("--tool", help="import: the tool name when the file is not from the plan")
    ap.add_argument("--args", help="import: the JSON arguments sent, when the file is not from the plan")
    a = ap.parse_args()
    if a.files and a.stage != "import":
        ap.error(f"unexpected arguments for {a.stage}: {' '.join(a.files)}")
    cfg = seoconf.load(a.site)
    a.country = (a.country or cfg.get("keywords", {}).get("default_country", "us")).lower()
    if a.stage != "budget" and not a.project:
        sys.exit("--project is required")
    STAGES[a.stage](cfg, a)


if __name__ == "__main__":
    main()
