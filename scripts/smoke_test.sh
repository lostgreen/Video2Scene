#!/usr/bin/env bash
set -euo pipefail

readonly SMCB_REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
readonly SMCB_PYTHON_BIN="${SMCB_PYTHON:-python3}"

if [[ -f "${SMCB_REPO_ROOT}/.env.local" ]]; then
  set -a
  source "${SMCB_REPO_ROOT}/.env.local"
  set +a
fi

PYTHONPATH="${SMCB_REPO_ROOT}/src" "${SMCB_PYTHON_BIN}" -m smcb.cli doctor
printf 'Repository initialization smoke check passed.\n'
