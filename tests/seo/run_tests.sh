#!/bin/sh
# Runs every test_*.py next to this script, each file in its own Python process: later round files re-execute
# earlier files' module loaders, so collecting them in one process makes their monkeypatches target different
# module instances. Exit code is non-zero when any file fails.
# Python: $PYTHON if set, else ./.venv/bin/python or python3, whichever has pytest (see README.md).
cd "$(dirname "$0")"
if [ -z "$PYTHON" ]; then
  for c in .venv/bin/python python3; do
    if command -v "$c" >/dev/null 2>&1 && "$c" -c 'import pytest' >/dev/null 2>&1; then PYTHON=$c; break; fi
  done
fi
PY=${PYTHON:-python3}
status=0
for f in test_*.py; do
  echo "== $f"
  out=$("$PY" -m pytest -q -p no:cacheprovider "$f" 2>&1); rc=$?   # keep pytest's own exit code (R958-09)
  printf '%s\n' "$out" | tail -1
  [ $rc -eq 0 ] || { status=1; printf '%s\n' "$out" | grep -E '^(FAILED|ERROR)' | head -20; }
done
exit $status
