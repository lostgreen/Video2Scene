#!/usr/bin/env bash
set -euo pipefail

readonly SMCB_REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

if [[ -f "${SMCB_REPO_ROOT}/.env.local" ]]; then
  set -a
  source "${SMCB_REPO_ROOT}/.env.local"
  set +a
fi

readonly SMCB_PYTHON_BIN="${SMCB_PYTHON:-python3}"
readonly SMCB_BLENDER_BIN="${BLENDER_BIN:-blender}"
readonly SMCB_GPU_BACKEND="${BLENDER_GPU_BACKEND:-opengl}"
readonly SMCB_SMOKE_ENGINE_VALUE="${SMCB_SMOKE_ENGINE:-BLENDER_EEVEE_NEXT}"

PYTHONPATH="${SMCB_REPO_ROOT}/src" "${SMCB_PYTHON_BIN}" -m smcb.cli doctor
"${SMCB_BLENDER_BIN}" \
  --background \
  --factory-startup \
  --gpu-backend "${SMCB_GPU_BACKEND}" \
  -P "${SMCB_REPO_ROOT}/blender_scripts/smoke_render.py" \
  -- \
  --engine "${SMCB_SMOKE_ENGINE_VALUE}" \
  --output "${SMCB_REPO_ROOT}/artifacts/smoke/render.png"
printf 'Repository Blender smoke check passed.\n'
