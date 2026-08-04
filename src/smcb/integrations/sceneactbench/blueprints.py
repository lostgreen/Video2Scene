"""Deterministic Scene Program construction from private SceneAct blueprints."""

from __future__ import annotations

import math
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, model_validator

from smcb.assets.models import AssetIndex, AssetIndexEntry
from smcb.dsl.models import (
    CameraSpec,
    LightingSpec,
    ObjectSpec,
    RenderSpec,
    SceneProgram,
    Transform,
    Vector3,
)


class BlueprintModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class BlueprintSlot(BlueprintModel):
    id: str = Field(min_length=1, pattern=r"^[A-Za-z0-9_-]+$")
    role: str = Field(min_length=1)
    source_name: str = Field(min_length=1)
    relation: str = Field(min_length=1)
    position: Vector3
    rotation_z_degrees: float = 0.0
    uniform_scale: float = Field(gt=0)
    target: bool = True


class PlatformStationBlueprint(BlueprintModel):
    schema_version: Literal["1.0"] = "1.0"
    sample_id: str = Field(min_length=1)
    template: Literal["platform_station_static"]
    seed: int
    render: RenderSpec
    camera: CameraSpec
    lighting: LightingSpec
    slots: list[BlueprintSlot] = Field(min_length=6, max_length=10)

    @model_validator(mode="after")
    def validate_static_contract(self) -> PlatformStationBlueprint:
        slot_ids = [slot.id for slot in self.slots]
        if len(slot_ids) != len(set(slot_ids)):
            raise ValueError("blueprint slot ids must be unique")
        frame_count = self.render.frame_end - self.render.frame_start + 1
        if self.render.fps != 24 or frame_count != 144:
            raise ValueError("SceneAct static blueprints require 24 fps and 144 frames")
        return self


@dataclass(frozen=True)
class ResolvedBlueprintSlot:
    slot: BlueprintSlot
    asset: AssetIndexEntry


def load_platform_station_blueprint(path: Path) -> PlatformStationBlueprint:
    """Load a strict private blueprint; semantic roles never enter public filenames."""
    payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    return PlatformStationBlueprint.model_validate(payload)


def _source_stem(entry: AssetIndexEntry) -> str:
    return Path(entry.source_relative_path).stem.casefold()


def resolve_blueprint_slots(
    blueprint: PlatformStationBlueprint, asset_index: AssetIndex
) -> tuple[ResolvedBlueprintSlot, ...]:
    """Resolve source stems instead of embedding machine-specific asset hashes."""
    resolved: list[ResolvedBlueprintSlot] = []
    for slot in blueprint.slots:
        matches = [
            entry
            for entry in asset_index.assets
            if _source_stem(entry) == slot.source_name.casefold()
        ]
        if len(matches) != 1:
            raise ValueError(
                f"blueprint asset {slot.source_name!r} resolved to {len(matches)} index entries"
            )
        resolved.append(ResolvedBlueprintSlot(slot=slot, asset=matches[0]))
    return tuple(resolved)


def _z_rotation(degrees: float) -> tuple[float, float, float, float]:
    half_angle = math.radians(degrees) / 2.0
    return (0.0, 0.0, math.sin(half_angle), math.cos(half_angle))


def build_platform_station_scene(
    blueprint: PlatformStationBlueprint, asset_index: AssetIndex
) -> SceneProgram:
    """Compile the explicit platform-station layout into Scene Program v0.1."""
    objects = []
    for resolved in resolve_blueprint_slots(blueprint, asset_index):
        slot = resolved.slot
        scale = (slot.uniform_scale,) * 3
        objects.append(
            ObjectSpec(
                id=slot.id,
                asset_id=resolved.asset.asset_id,
                target=slot.target,
                transform=Transform(
                    position=slot.position,
                    rotation=_z_rotation(slot.rotation_z_degrees),
                    scale=scale,
                ),
            )
        )
    return SceneProgram(
        sample_id=blueprint.sample_id,
        seed=blueprint.seed,
        template=blueprint.template,
        objects=objects,
        camera=blueprint.camera,
        lighting=blueprint.lighting,
        animations=[],
        render=blueprint.render,
    )
