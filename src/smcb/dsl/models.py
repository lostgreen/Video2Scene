"""Validated Scene Program v0.1 models."""

from __future__ import annotations

import math
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

Vector3 = tuple[float, float, float]
Quaternion = tuple[float, float, float, float]


class StrictModel(BaseModel):
    """Base class for versioned, typo-resistant data contracts."""

    model_config = ConfigDict(extra="forbid")


class CoordinateSystem(StrictModel):
    handedness: Literal["right"] = "right"
    up: Literal["Z"] = "Z"
    forward: Literal["-Y"] = "-Y"
    units: Literal["meters"] = "meters"
    quaternion_order: Literal["xyzw"] = "xyzw"


class Transform(StrictModel):
    position: Vector3 = (0.0, 0.0, 0.0)
    rotation: Quaternion = (0.0, 0.0, 0.0, 1.0)
    scale: Vector3 = (1.0, 1.0, 1.0)

    @model_validator(mode="after")
    def finite_values(self) -> Transform:
        values = (*self.position, *self.rotation, *self.scale)
        if not all(math.isfinite(value) for value in values):
            raise ValueError("transform values must be finite")
        if any(value <= 0 for value in self.scale):
            raise ValueError("scale components must be positive")
        norm = math.sqrt(sum(value * value for value in self.rotation))
        if norm < 1e-8:
            raise ValueError("rotation quaternion must be non-zero")
        return self


class ObjectSpec(StrictModel):
    id: str = Field(min_length=1, pattern=r"^[A-Za-z0-9_-]+$")
    asset_id: str = Field(min_length=1)
    transform: Transform = Field(default_factory=Transform)
    parent_id: str | None = None
    target: bool = True


class CameraSpec(StrictModel):
    id: str = "camera"
    type: Literal["perspective", "orthographic"] = "perspective"
    transform: Transform
    look_at: Vector3 = (0.0, 0.0, 0.8)
    focal_length_mm: float = Field(default=50.0, gt=0)
    ortho_scale: float = Field(default=6.0, gt=0)
    clip_start: float = Field(default=0.05, gt=0)
    clip_end: float = Field(default=100.0, gt=0)


class WorldSpec(StrictModel):
    color: Vector3 = (0.055, 0.065, 0.08)
    strength: float = Field(default=0.8, ge=0)


class LightSpec(StrictModel):
    id: str
    type: Literal["SUN", "AREA"]
    position: Vector3 = (0.0, 0.0, 5.0)
    rotation: Vector3 = (0.0, 0.0, 0.0)
    energy: float = Field(gt=0)
    size: float = Field(default=5.0, gt=0)


class LightingSpec(StrictModel):
    world: WorldSpec = Field(default_factory=WorldSpec)
    lights: list[LightSpec] = Field(min_length=1)


class Keyframe(StrictModel):
    frame: int = Field(ge=1)
    value: tuple[float, ...]


class AnimationTrack(StrictModel):
    target_id: str
    property: Literal["position", "rotation"]
    interpolation: Literal["linear"] = "linear"
    space: Literal["local", "world"] = "local"
    keyframes: list[Keyframe] = Field(min_length=2)

    @model_validator(mode="after")
    def validate_keyframes(self) -> AnimationTrack:
        expected = 3 if self.property == "position" else 4
        if any(len(keyframe.value) != expected for keyframe in self.keyframes):
            raise ValueError(f"{self.property} keyframes require {expected} values")
        frames = [keyframe.frame for keyframe in self.keyframes]
        if frames != sorted(set(frames)):
            raise ValueError("keyframe frames must be unique and increasing")
        if not all(math.isfinite(value) for keyframe in self.keyframes for value in keyframe.value):
            raise ValueError("keyframe values must be finite")
        return self


class RenderSpec(StrictModel):
    engine: Literal["BLENDER_EEVEE_NEXT"] = "BLENDER_EEVEE_NEXT"
    width: int = Field(ge=32, le=4096)
    height: int = Field(ge=32, le=4096)
    fps: int = Field(ge=1, le=120)
    frame_start: int = Field(default=1, ge=1)
    frame_end: int = Field(ge=1)
    samples: int = Field(default=16, ge=1, le=256)

    @model_validator(mode="after")
    def frame_range(self) -> RenderSpec:
        if self.frame_end < self.frame_start:
            raise ValueError("frame_end must not precede frame_start")
        return self


class SceneProgram(StrictModel):
    schema_version: Literal["0.1"] = "0.1"
    sample_id: str
    seed: int
    template: Literal[
        "static_orbit",
        "moving_object",
        "moving_camera",
        "parent_motion",
        "platform_station_static",
    ]
    coordinate_system: CoordinateSystem = Field(default_factory=CoordinateSystem)
    objects: list[ObjectSpec] = Field(min_length=1, max_length=20)
    camera: CameraSpec
    lighting: LightingSpec
    animations: list[AnimationTrack] = Field(default_factory=list)
    render: RenderSpec

    @model_validator(mode="after")
    def validate_references(self) -> SceneProgram:
        object_ids = [item.id for item in self.objects]
        if len(object_ids) != len(set(object_ids)):
            raise ValueError("object ids must be unique")
        known_ids = set(object_ids) | {self.camera.id}
        for item in self.objects:
            if item.parent_id is not None and item.parent_id not in object_ids:
                raise ValueError(f"unknown parent_id: {item.parent_id}")
            if item.parent_id == item.id:
                raise ValueError("an object cannot parent itself")
        for track in self.animations:
            if track.target_id not in known_ids:
                raise ValueError(f"unknown animation target: {track.target_id}")
            if track.keyframes[-1].frame > self.render.frame_end:
                raise ValueError("animation keyframe lies beyond render range")
        return self
