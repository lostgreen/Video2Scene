"""Upstream asset acquisition and source checks."""

from __future__ import annotations

import json
from fnmatch import fnmatch
from pathlib import Path
from typing import NamedTuple, cast

from gdown.download import download
from gdown.download_folder import download_folder
from gdown.exceptions import DownloadError

from smcb.assets.inventory import build_inventory
from smcb.assets.models import AssetSourceManifest


class DriveFile(NamedTuple):
    id: str
    path: str
    local_path: str


def load_source_manifest(path: Path) -> AssetSourceManifest:
    return AssetSourceManifest.model_validate_json(path.read_text(encoding="utf-8"))


def _is_excluded(path: str, patterns: list[str]) -> bool:
    return any(fnmatch(path, pattern) for pattern in patterns)


def fetch_source(manifest_path: Path, asset_root: Path) -> dict[str, object]:
    """Selectively download and inventory the compiler-facing source payload."""
    manifest = load_source_manifest(manifest_path)
    raw_dir = asset_root / "raw" / manifest.pack_id
    raw_dir.mkdir(parents=True, exist_ok=True)
    url = f"https://drive.google.com/drive/folders/{manifest.download.folder_id}"
    listing = cast(
        list[DriveFile],
        download_folder(
            url=url,
            output=f"{raw_dir}/",
            quiet=True,
            skip_download=True,
        ),
    )
    selected = [
        item
        for item in listing
        if Path(item.path).suffix.lower() in set(manifest.download_suffixes)
    ]
    failures: list[str] = []
    for item in selected:
        target = Path(item.local_path)
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.is_file():
            continue
        try:
            result = download(
                id=item.id,
                output=str(target),
                quiet=True,
                resume=True,
            )
        except (DownloadError, OSError):
            result = None
        if result is None:
            failures.append(item.path)

    eligible_gltf_count = sum(
        1
        for item in selected
        if item.path.lower().endswith(".gltf")
        and not _is_excluded(item.path, manifest.excluded_globs)
        and Path(item.local_path).is_file()
    )
    report = {
        "schema_version": "1.0",
        "selected_file_count": len(selected),
        "failed_files": failures,
        "eligible_gltf_count": eligible_gltf_count,
    }
    (raw_dir / "download_report.json").write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    if eligible_gltf_count < manifest.minimum_required_assets:
        raise RuntimeError(
            f"only {eligible_gltf_count} eligible glTF assets are available; "
            f"need {manifest.minimum_required_assets}"
        )
    inventory = build_inventory(raw_dir, raw_dir / "source_inventory.json")
    return {
        "pack_id": manifest.pack_id,
        "raw_dir": str(raw_dir),
        "file_count": inventory["file_count"],
        "eligible_gltf_count": eligible_gltf_count,
        "failed_file_count": len(failures),
        "inventory_sha256": inventory["inventory_sha256"],
    }


def source_status(manifest_path: Path, asset_root: Path) -> dict[str, object]:
    """Return compact asset readiness information without mutating the source."""
    manifest = load_source_manifest(manifest_path)
    raw_dir = asset_root / "raw" / manifest.pack_id
    gltf_paths = list(raw_dir.rglob("*.gltf")) if raw_dir.exists() else []
    eligible_count = sum(
        1
        for path in gltf_paths
        if not _is_excluded(path.relative_to(raw_dir).as_posix(), manifest.excluded_globs)
    )
    index_path = asset_root / "normalized" / "index.json"
    normalized_count = 0
    if index_path.is_file():
        normalized_count = len(json.loads(index_path.read_text(encoding="utf-8")).get("assets", []))
    return {
        "pack_id": manifest.pack_id,
        "raw_dir": str(raw_dir),
        "raw_exists": raw_dir.is_dir(),
        "gltf_count": len(gltf_paths),
        "eligible_gltf_count": eligible_count,
        "expected_model_count": manifest.expected_model_count,
        "normalized_count": normalized_count,
        "ready": eligible_count >= manifest.minimum_required_assets and normalized_count >= 30,
    }
