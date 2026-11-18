#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
PYTHON="${PYTHON:-python3}"
VENV="$ROOT/emulation/.venv-simulator"
if [[ ! -x "$VENV/bin/python" ]]; then
  "$PYTHON" -m venv "$VENV"
fi
if ! "$VENV/bin/python" -c 'import PIL' >/dev/null 2>&1; then
  "$VENV/bin/python" -m pip install -r "$ROOT/emulation/requirements-simulator.txt"
fi
exec "$VENV/bin/python" "$ROOT/emulation/firmware_runtime.py" "$@"
