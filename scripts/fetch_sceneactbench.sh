#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
submodule_path="$repo_root/third_party/sceneactbench"
expected_commit="5b01037454c2ef96c4dea4006b927d27da9d5447"

if git -C "$submodule_path" rev-parse --is-inside-work-tree >/dev/null 2>&1; then
  actual_commit="$(git -C "$submodule_path" rev-parse HEAD)"
else
  git -C "$repo_root" submodule update --init --recursive third_party/sceneactbench
  actual_commit="$(git -C "$submodule_path" rev-parse HEAD)"
fi

if [[ "$actual_commit" != "$expected_commit" ]]; then
  echo "SceneActBench commit mismatch: expected $expected_commit, found $actual_commit" >&2
  exit 1
fi

echo "SceneActBench ready at $actual_commit"
