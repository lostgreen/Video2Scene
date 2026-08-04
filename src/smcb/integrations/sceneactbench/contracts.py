"""Typed summaries for official SceneActBench Dynamic samples."""

from __future__ import annotations

from pathlib import Path
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


class StaticRenderInspection(BaseModel):
    """Visibility gate for one locally rendered static Scene Program."""

    sample_id: str
    sample_dir: Path
    object_count: int = Field(ge=0)
    visible_object_count: int = Field(ge=0)
    min_visible_pixel_ratio: float = Field(ge=0)
    object_pixel_ratios: dict[str, float]
    failures: list[str]
    passed: bool


class StaticSceneBuildResult(BaseModel):
    """Artifacts emitted before SceneAct package conversion."""

    sample_id: str
    sample_dir: Path
    scene_program: Path
    reference_video: Path
    preview: Path
    inspection: StaticRenderInspection


class DynamicRenderInspection(StaticRenderInspection):
    """Visibility and motion gate for the two-mover canonical master."""

    mover_ids: list[str]
    mover_motion_distances: dict[str, float]


class DynamicSceneBuildResult(BaseModel):
    sample_id: str
    sample_dir: Path
    scene_program: Path
    reference_video: Path
    preview: Path
    inspection: DynamicRenderInspection


class SceneActDynamicPackage(BaseModel):
    """Filesystem contract shared by static M2 and later dynamic scenes."""

    scene_id: str
    fps: int = Field(gt=0)
    frame_count: int = Field(gt=0)
    components_dir: Path
    reference_dir: Path
    reference_video: Path
    gt_scene_glb: Path
    trajectory_json: Path
    layout_gt_json: Path
    camera_json: Path
    meta_json: Path
    preview_png: Path


class SceneActPackageInspection(BaseModel):
    """Strict, non-Blender validation result for one local SceneAct package."""

    scene_id: str
    scene_dir: Path
    fps: int = Field(ge=0)
    frame_count: int = Field(ge=0)
    component_count: int = Field(ge=0)
    reference_frame_count: int = Field(ge=0)
    layout_object_count: int = Field(ge=0)
    mover_count: int = Field(ge=0)
    failures: list[str]
    passed: bool


class DynamicSceneActPackageInspection(SceneActPackageInspection):
    animation_count: int = Field(ge=0)
    animated_root_names: list[str]
    trajectory_frame_counts: dict[str, int]
