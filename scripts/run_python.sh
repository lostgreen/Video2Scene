#!/usr/bin/env bash
set -euo pipefail

readonly V2S_REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

if [[ -f "${V2S_REPO_ROOT}/.env.local" ]]; then
  set -a
  source "${V2S_REPO_ROOT}/.env.local"
  set +a
fi

readonly V2S_PYTHON_BIN="${SMCB_PYTHON:-python3}"
export PYTHONPATH="${V2S_REPO_ROOT}/src${PYTHONPATH:+:${PYTHONPATH}}"
exec "${V2S_PYTHON_BIN}" "$@"
