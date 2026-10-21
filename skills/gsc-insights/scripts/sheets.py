"""Minimal Google Sheets writer authorised as the site's service account.

The service account must have edit access to the spreadsheet (share the sheet with its email).
"""
from __future__ import annotations

import urllib.parse

import seoconf

SCOPE = ["https://www.googleapis.com/auth/spreadsheets"]
API = "https://sheets.googleapis.com/v4/spreadsheets"


class Sheet:
    def __init__(self, cfg: dict, sheet_id: str):
        self.s = seoconf.service_account_session(cfg, SCOPE)
        self.id = sheet_id

    def _check(self, r):
        if r.status_code >= 300:
            raise SystemExit(f"Sheets API {r.status_code}: {r.text[:400]}")
        return r.json() if r.text else {}

    def tabs(self) -> dict[str, int]:
        meta = self._check(self.s.get(f"{API}/{self.id}", params={"fields": "sheets.properties"}))
        return {s["properties"]["title"]: s["properties"]["sheetId"] for s in meta.get("sheets", [])}

    def ensure_tab(self, title: str) -> None:
        if title not in self.tabs():
            self._check(self.s.post(f"{API}/{self.id}:batchUpdate",
                                    json={"requests": [{"addSheet": {"properties": {"title": title}}}]}))

    def read(self, title: str, rng: str = "A1:ZZ") -> list[list]:
        r = self._check(self.s.get(f"{API}/{self.id}/values/{urllib.parse.quote(f'{title}!{rng}')}"))
        return r.get("values", [])

    def overwrite(self, title: str, rows: list[list]) -> None:
        self.ensure_tab(title)
        q = urllib.parse.quote(f"{title}!A1:ZZ")
        self._check(self.s.post(f"{API}/{self.id}/values/{q}:clear", json={}))
        self._check(self.s.put(f"{API}/{self.id}/values/{urllib.parse.quote(f'{title}!A1')}",
                               params={"valueInputOption": "RAW"}, json={"values": rows}))

    def upsert_row(self, title: str, header: list, row: list, key_col: int = 0) -> None:
        """Keep one row per key (e.g. week): update it if present, else append."""
        self.ensure_tab(title)
        cur = self.read(title)
        if not cur or cur[0] != header:
            cur = [header] + [r for r in cur[1:]] if cur else [header]
        body = [r for r in cur[1:] if r and r[key_col] != str(row[key_col])]
        body.append([str(v) if v is not None else "" for v in row])
        body.sort(key=lambda r: r[key_col])
        self.overwrite(title, [header] + body)
