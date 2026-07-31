"""Asset source, normalization, and index contracts."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class AssetModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class DownloadSpec(AssetModel):
    kind: Literal["google_drive_folder"]
    folder_id: str


class LicenseSpec(AssetModel):
    spdx: str
    name: str
    source_claim: str
    upstream_license_glob: str


class AssetSourceManifest(AssetModel):
    manifest_version: Literal["1.0"]
    pack_id: str
    display_name: str
    publisher: str
    source_page: str
    download: DownloadSpec
    license: LicenseSpec
    preferred_formats: list[str]
    excluded_globs: list[str] = Field(default_factory=list)
    expected_model_count: int = Field(gt=0)
    inventory_sha256: str | None = None
    notes: str


class AnimationClip(AssetModel):
    name: str
    frame_start: float
    frame_end: float


class AssetMetadata(AssetModel):
    schema_version: Literal["1.0"] = "1.0"
    asset_id: str
    source_pack: str
    source_name: str
    source_relative_path: str
    source_sha256: str
    normalized_glb_sha256: str
    canonical_transform: dict[str, Any]
    dimensions: tuple[float, float, float]
    bbox_min: tuple[float, float, float]
    bbox_max: tuple[float, float, float]
    ground_offset: float
    animation_clips: list[AnimationClip]
    tags_private: list[str]
    preview_files: list[str]


class AssetIndexEntry(AssetModel):
    asset_id: str
    glb_path: str
    metadata_path: str
    source_relative_path: str
    dimensions: tuple[float, float, float]
    animation_clips: list[str]


class AssetIndex(AssetModel):
    schema_version: Literal["1.0"] = "1.0"
    pack_id: str
    source_inventory_sha256: str
    asset_manifest_hash: str
    assets: list[AssetIndexEntry]
