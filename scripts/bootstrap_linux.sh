#!/usr/bin/env bash
set -euo pipefail

readonly SMCB_BLENDER_VERSION="${BLENDER_VERSION:-4.5.12}"
readonly SMCB_BLENDER_PLATFORM="linux-x64"
readonly SMCB_BLENDER_SHA256="95e3a2dfedba3bd32ca54fc355eac6b15a11986954ccb02815a07535d0120a25"
readonly SMCB_BLENDER_ARCHIVE="blender-${SMCB_BLENDER_VERSION}-${SMCB_BLENDER_PLATFORM}.tar.xz"
readonly SMCB_BLENDER_URL="https://download.blender.org/release/Blender4.5/${SMCB_BLENDER_ARCHIVE}"
readonly SMCB_INSTALL_ROOT="${BLENDER_ROOT:-${HOME}/.local/opt/video2scene}"
readonly SMCB_CACHE_ROOT="${XDG_CACHE_HOME:-${HOME}/.cache}/video2scene"
readonly SMCB_TARGET="${SMCB_INSTALL_ROOT}/blender-${SMCB_BLENDER_VERSION}"
readonly SMCB_LINK="${SMCB_INSTALL_ROOT}/blender"
readonly SMCB_ARCHIVE_PATH="${SMCB_CACHE_ROOT}/${SMCB_BLENDER_ARCHIVE}"

if [[ "$(uname -m)" != "x86_64" ]]; then
  printf 'Unsupported architecture: %s (expected x86_64)\n' "$(uname -m)" >&2
  exit 2
fi

for SMCB_TOOL in curl tar sha256sum mktemp; do
  if ! command -v "${SMCB_TOOL}" >/dev/null 2>&1; then
    printf 'Missing required tool: %s\n' "${SMCB_TOOL}" >&2
    exit 2
  fi
done

mkdir -p "${SMCB_INSTALL_ROOT}" "${SMCB_CACHE_ROOT}"

if [[ ! -x "${SMCB_TARGET}/blender" ]]; then
  if [[ ! -f "${SMCB_ARCHIVE_PATH}" ]]; then
    curl --fail --location --retry 3 --output "${SMCB_ARCHIVE_PATH}" "${SMCB_BLENDER_URL}"
  fi
  printf '%s  %s\n' "${SMCB_BLENDER_SHA256}" "${SMCB_ARCHIVE_PATH}" | sha256sum --check -
  SMCB_TEMP_DIR="$(mktemp -d "${SMCB_INSTALL_ROOT}/.blender-install.XXXXXX")"
  tar -xJf "${SMCB_ARCHIVE_PATH}" -C "${SMCB_TEMP_DIR}"
  mv "${SMCB_TEMP_DIR}/blender-${SMCB_BLENDER_VERSION}-${SMCB_BLENDER_PLATFORM}" "${SMCB_TARGET}"
  rmdir "${SMCB_TEMP_DIR}"
fi

if [[ -L "${SMCB_LINK}" ]]; then
  ln -sfn "${SMCB_TARGET}" "${SMCB_LINK}"
elif [[ -e "${SMCB_LINK}" ]]; then
  printf 'Refusing to replace existing non-symlink: %s\n' "${SMCB_LINK}" >&2
  exit 2
else
  ln -s "${SMCB_TARGET}" "${SMCB_LINK}"
fi

"${SMCB_LINK}/blender" --version | sed -n '1p'
printf 'BLENDER_BIN=%s\n' "${SMCB_LINK}/blender"
