"""Typed summaries for official SceneActBench Dynamic samples."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

FetchProfile = Literal["oracle", "full"]


class DynamicSampleInspection(BaseModel):
    """Compact validation result for one official Dynamic scene."""

    scene_id: str
    sample_dir: str
    fps: int = Field(ge=0)
    frame_count: int = Field(ge=0)
    mover_names: list[str]
    trajectory_frame_counts: dict[str, int]
    static_object_count: int = Field(ge=0)
    reference_video: str
    gt_scene_glb: str
    license_found: bool
    source_metadata_found: bool
    failures: list[str]
    passed: bool


class DynamicFetchResult(BaseModel):
    """Files and immutable provenance emitted by a scoped dataset fetch."""

    scene_id: str
    profile: FetchProfile
    sample_dir: str
    dataset_revision: str
    downloaded_file_count: int = Field(ge=0)
    downloaded_bytes: int = Field(ge=0)
