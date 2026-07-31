"""Deterministic raw-source inventory generation."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any


def sha256_file(path: Path) -> str:
    """Hash a file without loading it into memory."""
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def stable_asset_id(pack_id: str, relative_path: str) -> str:
    """Derive an ID that does not change when the source listing is reordered."""
    slug = "".join(char if char.isalnum() else "_" for char in Path(relative_path).stem.lower())
    slug = "_".join(part for part in slug.split("_") if part)[:32] or "asset"
    suffix = hashlib.sha256(relative_path.casefold().encode("utf-8")).hexdigest()[:10]
    return f"{pack_id}_{slug}_{suffix}"


def build_inventory(raw_dir: Path, output_path: Path | None = None) -> dict[str, Any]:
    """Hash the materialized upstream tree and optionally write its lock file."""
    excluded = {"download_report.json", "source_inventory.json"}
    files: list[dict[str, Any]] = []
    aggregate = hashlib.sha256()
    for path in sorted(item for item in raw_dir.rglob("*") if item.is_file()):
        relative = path.relative_to(raw_dir).as_posix()
        if relative in excluded:
            continue
        file_hash = sha256_file(path)
        size = path.stat().st_size
        files.append({"path": relative, "size": size, "sha256": file_hash})
        aggregate.update(f"{relative}\0{size}\0{file_hash}\n".encode())
    payload: dict[str, Any] = {
        "schema_version": "1.0",
        "file_count": len(files),
        "inventory_sha256": aggregate.hexdigest(),
        "files": files,
    }
    if output_path is not None:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(
            json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
    return payload
