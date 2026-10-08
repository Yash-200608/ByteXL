#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
PY=${PY:-.venv/bin/python}
case "${1:-}" in
  api) exec "$PY" -m uvicorn app.api.main:app --host 0.0.0.0 --port "${PORT:-8000}" ;;
  ui) exec "$PY" -m streamlit run ui/app.py --server.port "${UI_PORT:-8501}" ;;
  test) exec "$PY" -m pytest -q ;;
  eval) exec "$PY" scripts/eval.py "${@:2}" ;;
  seed) exec "$PY" scripts/seed.py "${@:2}" ;;
  *) echo "usage: scripts/run.sh {api|ui|test|eval|seed}"; exit 1 ;;
esac
