"""robots.txt matching with the semantics search engines use (RFC 9309 + Google's documented behaviour).

- Groups are chosen by the most specific user-agent token that matches (case-insensitive substring of the
  product token); otherwise the '*' group. Several groups for the same agent are merged.
- Rules support '*' (any sequence) and a trailing '$' (end of URL). The longest matching pattern wins;
  on a tie between Allow and Disallow, Allow wins. An empty Disallow allows everything.
- /robots.txt itself is always allowed.
"""
from __future__ import annotations

import re
import urllib.parse

_UNRESERVED = set("ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-._~")


def normalize(path: str) -> str:
    """Comparable form of a path or rule (RA35-04): non-ASCII -> UTF-8 %XX, %XX of unreserved characters decoded,
    other escapes upper-cased. Reserved characters such as %2F stay encoded, so /a%2Fb never equals /a/b."""
    path = "".join(c if ord(c) < 128 else "".join(f"%{b:02X}" for b in c.encode("utf-8")) for c in path)
    return re.sub(r"%([0-9A-Fa-f]{2})",
                  lambda m: chr(int(m.group(1), 16)) if chr(int(m.group(1), 16)) in _UNRESERVED else f"%{m.group(1).upper()}",
                  path)


class Robots:
    def __init__(self, text: str | None):
        self.groups: list[tuple[list[str], list[tuple[bool, str]]]] = []
        agents: list[str] = []
        rules: list[tuple[bool, str]] = []
        last_was_rule = False
        for raw in (text or "").splitlines():
            line = raw.split("#", 1)[0].strip()
            if ":" not in line:
                continue
            k, v = (x.strip() for x in line.split(":", 1))
            k = k.lower()
            if k == "user-agent":
                if last_was_rule:
                    self.groups.append((agents, rules))
                    agents, rules = [], []
                agents.append(v.lower())
                last_was_rule = False
            elif k in ("allow", "disallow") and agents:
                rules.append((k == "allow", v))
                last_was_rule = True
        if agents:
            self.groups.append((agents, rules))

    def _rules_for(self, agent: str) -> list[tuple[bool, str]]:
        agent = agent.lower()
        best, best_len, merged = None, -1, []
        for agents, rules in self.groups:
            for a in agents:
                if a != "*" and a in agent and len(a) > best_len:
                    best, best_len = a, len(a)
        if best is not None:
            for agents, rules in self.groups:
                if best in agents:
                    merged += rules
            return merged
        for agents, rules in self.groups:
            if "*" in agents:
                merged += rules
        return merged

    @staticmethod
    def _match(pattern: str, path: str) -> bool:
        if not pattern:
            return False
        anchored = pattern.endswith("$")
        body = normalize(pattern[:-1] if anchored else pattern)
        rx = "^" + ".*".join(re.escape(part) for part in body.split("*")) + ("$" if anchored else "")
        return re.match(rx, path) is not None

    def allowed(self, agent: str, url: str) -> bool:
        u = urllib.parse.urlsplit(url)
        path = normalize((u.path or "/") + (f"?{u.query}" if u.query else ""))
        if path == "/robots.txt":
            return True
        best_len, verdict = -1, True
        for allow, pattern in self._rules_for(agent):
            if pattern == "" and not allow:
                continue  # "Disallow:" with no value allows everything
            if self._match(pattern, path):
                ln = len(normalize(pattern))  # specificity in the same normalized form used for matching (R958-02)
                if ln > best_len or (ln == best_len and allow):
                    best_len, verdict = ln, allow
        return verdict
