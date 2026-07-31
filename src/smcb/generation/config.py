"""Dataset generation configuration models."""

from __future__ import annotations

from pathlib import Path

import yaml
from pydantic import BaseModel, ConfigDict, Field, model_validator


class ConfigModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class DatasetSection(ConfigModel):
    name: str
    num_samples: int = Field(gt=0)
    output_subdir: str


class AssetsSection(ConfigModel):
    pack: str
    normalized_subdir: str = "normalized"
    candidate_library_size: int = Field(default=20, ge=1)


class CountRange(ConfigModel):
    min: int = Field(ge=1)
    max: int = Field(ge=1)

    @model_validator(mode="after")
    def ordered(self) -> CountRange:
        if self.max < self.min:
            raise ValueError("range max must be >= min")
        return self


class SceneSection(ConfigModel):
    object_count: CountRange


class DurationRange(ConfigModel):
    min: int = Field(ge=1)
    max: int = Field(ge=1)

    @model_validator(mode="after")
    def ordered(self) -> DurationRange:
        if self.max < self.min:
            raise ValueError("duration max must be >= min")
        return self


class VideoSection(ConfigModel):
    width: int = Field(ge=32)
    height: int = Field(ge=32)
    fps: int = Field(gt=0)
    duration_seconds: DurationRange


class RenderSection(ConfigModel):
    engine: str = "BLENDER_EEVEE_NEXT"
    samples: int = Field(default=16, gt=0)


class QualityControlSection(ConfigModel):
    min_visible_frame_ratio: float = Field(ge=0, le=1)
    min_visible_pixels: int = Field(ge=1)
    max_pairwise_screen_iou: float = Field(ge=0, le=1)
    min_motion_distance: float = Field(ge=0)
    max_resample_attempts: int = Field(ge=1)


class DatasetConfig(ConfigModel):
    dataset: DatasetSection
    assets: AssetsSection
    scene: SceneSection
    templates: dict[str, float]
    video: VideoSection
    render: RenderSection
    quality_control: QualityControlSection
    seed: int

    @model_validator(mode="after")
    def validate_templates(self) -> DatasetConfig:
        expected = {"static_orbit", "moving_object", "moving_camera", "parent_motion"}
        if set(self.templates) != expected:
            raise ValueError(f"templates must contain exactly {sorted(expected)}")
        if (
            any(weight < 0 for weight in self.templates.values())
            or sum(self.templates.values()) <= 0
        ):
            raise ValueError("template weights must be non-negative with a positive sum")
        if self.scene.object_count.max > 5:
            raise ValueError("Scene Program v0.1 supports at most five objects")
        return self


def load_dataset_config(path: Path) -> DatasetConfig:
    """Read one YAML config through the typed contract."""
    payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    return DatasetConfig.model_validate(payload)
