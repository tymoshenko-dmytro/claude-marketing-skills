# Tests

Offline test suites for the kit's scripts. No network, no API keys, no browser: every HTTP call, BigQuery job,
Sheets write and browser session is a stand-in. Run them before you send a change to a script (see
`CONTRIBUTING.md`).

## SEO skills (`tests/seo`)

Covers the scripts of `skills/gsc-insights`, `skills/seo-tech-audit` and `skills/ahrefs`.

| File | What it covers |
|---|---|
| `test_cli_round1.py` … `test_cli_round4.py` | The command-line entry points of all three skills: GSC pull and archive, the 12 recipes, the weekly report, crawl, robots.txt rules, audit rules and tickets, URL Inspection, CrUX, Bing, render check, the keyword-research stages (`kw.py`), secret redaction and the test runner itself. Four rounds of review findings; later rounds load the fixtures of earlier ones. |
| `test_ahrefs_transport.py` | Ahrefs API v3 transport (endpoint paths, unit headers, key lookup, 401/429 handling, `ahrefs_api.py`) and the MCP path of `kw.py` (plan → import → cluster → prioritize). |
| `test_digest_backlog.py` | `weekly_digest.py` and the audit backlog (`backlog.py`) in the Russian output language. |

Needs Python 3.11 or newer.

```bash
python3 -m venv tests/seo/.venv
tests/seo/.venv/bin/pip install -r tests/seo/requirements.txt
sh tests/seo/run_tests.sh
```

With `uv`: `uv venv tests/seo/.venv && uv pip install --python tests/seo/.venv/bin/python -r tests/seo/requirements.txt`.

`run_tests.sh` uses `$PYTHON` if set (a path to an interpreter that has the packages above), otherwise
`tests/seo/.venv/bin/python` or `python3`, whichever has pytest.

It runs each file in its own Python process and prints one summary line per file; the exit code is non-zero when any
file fails. Do not run `pytest tests/seo` in one process: the round files re-load each other's modules, and their
monkeypatches would then hit different module copies. One file at a time is fine:

```bash
cd tests/seo && .venv/bin/python -m pytest -q test_ahrefs_transport.py
```
