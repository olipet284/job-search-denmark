#!/usr/bin/env bash
# One-time (or occasional) setup for Job Review App
# Creates virtual environment and installs dependencies from requirements.txt
# Usage: ./install.sh [--force]
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="${SCRIPT_DIR}"
VENV_DIR="${PROJECT_ROOT}/.venv"
REQ_FILE="${PROJECT_ROOT}/requirements.txt"
FORCE=0
if [ "${1:-}" = "--force" ]; then FORCE=1; fi
if [ -d "${VENV_DIR}" ] && [ $FORCE -eq 0 ]; then
  echo "[info] Existing venv found at ${VENV_DIR}. Use --force to recreate." >&2
else
  if [ -d "${VENV_DIR}" ]; then
    echo "[info] Recreating venv (force)" >&2
    rm -rf "${VENV_DIR}"
  else
    echo "[info] Creating venv at ${VENV_DIR}" >&2
  fi
  python3 -m venv "${VENV_DIR}" || { echo "[error] Failed to create venv" >&2; exit 1; }
fi
# Activate
# shellcheck disable=SC1091
source "${VENV_DIR}/bin/activate"
python -m pip install --upgrade pip setuptools wheel >/dev/null 2>&1 || true
if [ -f "${REQ_FILE}" ]; then
  echo "[install] Installing from requirements.txt" >&2
  pip install -r "${REQ_FILE}" || { echo "[error] Dependency installation failed" >&2; exit 1; }
else
  echo "[warn] requirements.txt not found, installing minimal deps" >&2
  pip install Flask pandas || { echo "[error] Fallback install failed" >&2; exit 1; }
fi
python -c 'import flask, pandas; print("[verify] Flask", flask.__version__, "pandas", pandas.__version__)'
echo "[done] Installation complete. Launch with: ./run_review.sh start" >&2
