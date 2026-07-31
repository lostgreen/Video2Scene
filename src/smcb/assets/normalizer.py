"""Blender-backed asset normalization orchestration."""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
from pathlib import Path

from PIL import Image, ImageOps

from smcb.assets.inventory import build_inventory, stable_asset_id
from smcb.assets.models import AssetIndex, AssetIndexEntry, AssetMetadata
from smcb.assets.source import load_source_manifest


def _contact_sheet(image_paths: list[Path], output_path: Path) -> None:
    images = [Image.open(path).convert("RGB") for path in image_paths]
    try:
        size = (256, 256)
        canvas = Image.new("RGB", (size[0] * 3, size[1] * 2), (24, 26, 30))
        for index, image in enumerate(images):
            tile = ImageOps.fit(image, size, method=Image.Resampling.LANCZOS)
            canvas.paste(tile, ((index % 3) * size[0], (index // 3) * size[1]))
        output_path.parent.mkdir(parents=True, exist_ok=True)
        canvas.save(output_path, quality=92)
    finally:
        for image in images:
            image.close()


def _manifest_hash(entries: list[AssetIndexEntry]) -> str:
    payload = json.dumps(
        [entry.model_dump(mode="json") for entry in entries],
        sort_keys=True,
        separators=(",", ":"),
    ).encode()
    return hashlib.sha256(payload).hexdigest()


def normalize_library(
    *,
    source: Path,
    output: Path,
    previews: Path,
    manifest_path: Path,
    blender_bin: str,
    blender_script: Path,
    limit: int | None = None,
) -> AssetIndex:
    """Normalize a deterministic slice of a source library and rebuild its index."""
    manifest = load_source_manifest(manifest_path)
    source = source.resolve()
    output.mkdir(parents=True, exist_ok=True)
    previews.mkdir(parents=True, exist_ok=True)
    logs_dir = output / "logs"
    logs_dir.mkdir(parents=True, exist_ok=True)

    candidates = sorted(path for path in source.rglob("*.gltf") if path.is_file())
    if limit is not None:
        candidates = candidates[:limit]
    if not candidates:
        raise FileNotFoundError(f"no glTF assets found below {source}")

    for source_path in candidates:
        relative = source_path.relative_to(source).as_posix()
        asset_id = stable_asset_id(manifest.pack_id, relative)
        glb_path = output / f"{asset_id}.glb"
        metadata_path = output / f"{asset_id}.json"
        preview_dir = previews / asset_id
        expected_previews = [
            preview_dir / f"{name}.png"
            for name in ("front", "back", "left", "right", "top", "isometric")
        ]
        if (
            glb_path.is_file()
            and metadata_path.is_file()
            and all(path.is_file() for path in expected_previews)
        ):
            if not (preview_dir / "contact_sheet.jpg").is_file():
                _contact_sheet(expected_previews, preview_dir / "contact_sheet.jpg")
            continue

        command = [
            blender_bin,
            "--background",
            "--factory-startup",
            "--gpu-backend",
            os.environ.get("BLENDER_GPU_BACKEND", "opengl"),
            "--python",
            str(blender_script),
            "--",
            "--source",
            str(source_path),
            "--source-relative",
            relative,
            "--source-pack",
            manifest.pack_id,
            "--asset-id",
            asset_id,
            "--output-glb",
            str(glb_path),
            "--output-metadata",
            str(metadata_path),
            "--preview-dir",
            str(preview_dir),
        ]
        with (logs_dir / f"{asset_id}.log").open("w", encoding="utf-8") as log:
            result = subprocess.run(command, stdout=log, stderr=subprocess.STDOUT, check=False)
        if result.returncode != 0:
            raise RuntimeError(
                f"Blender normalization failed for {relative}; see {logs_dir / f'{asset_id}.log'}"
            )
        _contact_sheet(expected_previews, preview_dir / "contact_sheet.jpg")

    entries: list[AssetIndexEntry] = []
    for metadata_path in sorted(output.glob(f"{manifest.pack_id}_*.json")):
        metadata = AssetMetadata.model_validate_json(metadata_path.read_text(encoding="utf-8"))
        glb_path = output / f"{metadata.asset_id}.glb"
        if not glb_path.is_file():
            continue
        entries.append(
            AssetIndexEntry(
                asset_id=metadata.asset_id,
                glb_path=str(glb_path.resolve()),
                metadata_path=str(metadata_path.resolve()),
                source_relative_path=metadata.source_relative_path,
                dimensions=metadata.dimensions,
                animation_clips=[clip.name for clip in metadata.animation_clips],
            )
        )
    raw_inventory_path = source / "source_inventory.json"
    if raw_inventory_path.is_file():
        raw_inventory = json.loads(raw_inventory_path.read_text(encoding="utf-8"))
    else:
        raw_inventory = build_inventory(source, raw_inventory_path)
    index = AssetIndex(
        pack_id=manifest.pack_id,
        source_inventory_sha256=str(raw_inventory["inventory_sha256"]),
        asset_manifest_hash=_manifest_hash(entries),
        assets=entries,
    )
    (output / "index.json").write_text(
        json.dumps(index.model_dump(mode="json"), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return index
