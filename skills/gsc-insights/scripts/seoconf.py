"""Shared helpers for the SEO skills: site config, secrets, credentials, query classifiers.

gsc-insights, seo-tech-audit and ahrefs each ship an identical copy of this file, so each skill also works when it
is installed alone. Change all three copies together.

A site config is a TOML file in ~/.config/marketing-agent-kit/seo/<site>.toml (override the folder with
SEO_SKILLS_CONFIG_DIR). Pick the site with --site <name|path> or SEO_SITE; if the folder holds a single config, it
is used. Secrets never go in the config: a real environment variable wins, then the keys file named in
[credentials].env_file, by default the kit's keys file ~/.config/marketing-agent-kit/.env (override with
MARKETING_KIT_ENV).
"""
from __future__ import annotations

import glob
import os
import re
import sys
import tomllib

CONF_DIR = os.path.expanduser(os.environ.get("SEO_SKILLS_CONFIG_DIR", "~/.config/marketing-agent-kit/seo"))
KIT_ENV = os.environ.get("MARKETING_KIT_ENV", "~/.config/marketing-agent-kit/.env")
_ENV_FILE = [KIT_ENV]  # the keys file actually used, for error messages


def expand(p: str | None) -> str | None:
    return os.path.expanduser(p) if p else p


def env_value(raw: str) -> str:
    """Value of KEY=value: drop an inline comment (a # at the start or after a space), then quotes."""
    return re.split(r"(?:^|\s)#", raw.strip(), maxsplit=1)[0].strip().strip('"').strip("'")


def load(site: str | None = None) -> dict:
    site = site or os.environ.get("SEO_SITE")
    if site:
        path = site if site.endswith(".toml") else os.path.join(CONF_DIR, site + ".toml")
    else:
        files = sorted(glob.glob(os.path.join(CONF_DIR, "*.toml")))
        if not files:
            sys.exit(f"No site config in {CONF_DIR}. Create <site>.toml as described in "
                     "gsc-insights references/config.md (guide: connections/search-console.md).")
        if len(files) > 1:
            sys.exit(f"Pass --site: found {len(files)} configs in {CONF_DIR}")
        path = files[0]
    if not os.path.exists(path):
        sys.exit(f"Site config not found: {path}")
    with open(path, "rb") as f:
        cfg = tomllib.load(f)
    cfg["_path"] = path
    _ENV_FILE[0] = cfg.get("credentials", {}).get("env_file") or KIT_ENV
    _load_env(expand(_ENV_FILE[0]))
    return cfg


def _load_env(path: str | None) -> None:
    """KEY=value lines into os.environ; a variable that is already set wins."""
    if not path or not os.path.exists(path):
        return
    for line in open(path):
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        v = env_value(v)
        if v:
            os.environ.setdefault(k.strip(), v)


def need_key(name: str, guide: str) -> str:
    """The value of a required key, or exit with a message that names the key, the keys file and the guide."""
    v = os.environ.get(name)
    if v:
        return v
    sys.exit(f"{name} not found. Set it in the environment or add {name}=... to {expand(_ENV_FILE[0])} "
             f"(guide: connections/{guide}).")


def redact(text: str | None) -> str:
    """Remove secrets from text that may be printed or saved: env values named *KEY*/*TOKEN*/*SECRET*/*WEBHOOK*/
    *PASSWORD* (any length), and key-like URL parameters. All known values are matched in one pass against the
    original text, longest first, so a short value can never break the match of a longer one (R212-01)."""
    text = str(text or "")
    vals = sorted({v for k, v in os.environ.items() if v and re.search(r"KEY|TOKEN|SECRET|WEBHOOK|PASSWORD", k, re.I)},
                  key=len, reverse=True)
    if vals:
        text = re.sub("|".join(re.escape(v) for v in vals), "[redacted]", text)
    return re.sub(r"(?i)\b(api_?key|key|token|access_token|secret)=([^&\s\"']+)", r"\1=[redacted]", text)


def data_dir(cfg: dict, *sub: str) -> str:
    d = os.path.join(expand(cfg["data"]["dir"]), *sub)
    os.makedirs(d, exist_ok=True)
    return d


def service_account_session(cfg: dict, scopes: list[str]):
    """requests-compatible session authorised as the site's service account."""
    from google.auth.transport.requests import AuthorizedSession
    from google.oauth2 import service_account

    path = expand(cfg.get("credentials", {}).get("gsc_service_account"))
    if not path:
        sys.exit("[credentials].gsc_service_account is not set in the site config (guide: connections/search-console.md).")
    if not os.path.exists(path):
        sys.exit(f"Service account key not found: {path} (guide: connections/search-console.md)")
    creds = service_account.Credentials.from_service_account_file(path, scopes=scopes)
    return AuthorizedSession(creds)


class BrandClassifier:
    """brand / ambiguous / non-brand / anonymized (empty query)."""

    def __init__(self, cfg: dict):
        b = cfg.get("brand", {})
        self.brand = [re.compile(p, re.I) for p in b.get("patterns", [])]
        self.ambiguous = [re.compile(p, re.I) for p in b.get("ambiguous", [])]

    def __call__(self, q: str | None) -> str:
        if not q:
            return "anonymized"
        if any(p.search(q) for p in self.brand):
            return "brand"
        if any(p.search(q) for p in self.ambiguous):
            return "ambiguous"
        return "non-brand"


_SCRIPTS = [
    ("arabic", re.compile(r"[؀-ۿݐ-ݿ]")),
    ("hebrew", re.compile(r"[֐-׿]")),
    ("cyrillic", re.compile(r"[Ѐ-ӿ]")),
    ("hangul", re.compile(r"[가-힯]")),
    ("kana", re.compile(r"[぀-ヿ]")),
    ("han", re.compile(r"[一-鿿]")),
    ("thai", re.compile(r"[฀-๿]")),
    ("devanagari", re.compile(r"[ऀ-ॿ]")),
    ("greek", re.compile(r"[Ͱ-Ͽ]")),
]


def script_of(q: str | None) -> str:
    """Writing system of a query. A cheap proxy for language; Latin needs a real detector."""
    if not q:
        return "unknown"
    for name, rx in _SCRIPTS:
        if rx.search(q):
            return name
    return "latin" if re.search(r"[A-Za-zÀ-ɏ]", q) else "other"


def locale_of(url: str | None, locales: list[str]) -> str:
    """Locale from the first path segment (/es, /es/..., /es?x=1); default 'default' (R69F-06)."""
    if not url:
        return "default"
    import urllib.parse
    seg = urllib.parse.urlsplit(url).path.strip("/").split("/")[0].lower()
    return seg if seg and seg in locales else "default"


QUESTION_RX = re.compile(
    r"(?i)^\s*(how|what|why|when|where|which|who|can|does|do|is|are|should"
    r"|qu[eé]|c[oó]mo|cu[aá]nto|por\s*qu[eé]|d[oó]nde"            # es
    r"|como|quanto|porque|onde"                                     # pt
    r"|comment|pourquoi|quel|quelle|est-ce"                         # fr
    r"|wie|was|warum|welche"                                        # de
    r"|apa|bagaimana|mengapa|kapan|berapa|bisakah|cara)\b"          # id
    r"|^\s*(كيف|هل|ما|ماذا|لماذا|كم|أين)(\s|$)"                     # ar
    r"|\?\s*$|？\s*$"
)
