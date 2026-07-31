"""Upstream asset acquisition and source checks."""

from __future__ import annotations

import json
from pathlib import Path

from gdown.download_folder import download_folder

from smcb.assets.inventory import build_inventory
from smcb.assets.models import AssetSourceManifest


def load_source_manifest(path: Path) -> AssetSourceManifest:
    return AssetSourceManifest.model_validate_json(path.read_text(encoding="utf-8"))


def fetch_source(manifest_path: Path, asset_root: Path) -> dict[str, object]:
    """Download a public source folder once and lock its materialized contents."""
    manifest = load_source_manifest(manifest_path)
    raw_dir = asset_root / "raw" / manifest.pack_id
    raw_dir.mkdir(parents=True, exist_ok=True)
    existing = [path for path in raw_dir.rglob("*") if path.is_file()]
    if not existing:
        url = f"https://drive.google.com/drive/folders/{manifest.download.folder_id}"
        downloaded = download_folder(
            url=url,
            output=f"{raw_dir}/",
            quiet=False,
        )
        if not downloaded:
            raise RuntimeError(f"asset download returned no files for {manifest.pack_id}")
    inventory = build_inventory(raw_dir, raw_dir / "source_inventory.json")
    return {
        "pack_id": manifest.pack_id,
        "raw_dir": str(raw_dir),
        "file_count": inventory["file_count"],
        "inventory_sha256": inventory["inventory_sha256"],
    }


def source_status(manifest_path: Path, asset_root: Path) -> dict[str, object]:
    """Return compact asset readiness information without mutating the source."""
    manifest = load_source_manifest(manifest_path)
    raw_dir = asset_root / "raw" / manifest.pack_id
    gltf_count = (
        sum(1 for path in raw_dir.rglob("*.gltf") if path.is_file()) if raw_dir.exists() else 0
    )
    index_path = asset_root / "normalized" / "index.json"
    normalized_count = 0
    if index_path.is_file():
        normalized_count = len(json.loads(index_path.read_text(encoding="utf-8")).get("assets", []))
    return {
        "pack_id": manifest.pack_id,
        "raw_dir": str(raw_dir),
        "raw_exists": raw_dir.is_dir(),
        "gltf_count": gltf_count,
        "expected_model_count": manifest.expected_model_count,
        "normalized_count": normalized_count,
        "ready": gltf_count > 0 and normalized_count >= 30,
    }
