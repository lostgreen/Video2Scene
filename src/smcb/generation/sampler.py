"""Deterministic Scene Program sampler for the four MVP templates."""

from __future__ import annotations

import json
import math
import random
from pathlib import Path

from smcb.assets.models import AssetIndex, AssetIndexEntry
from smcb.dsl.models import (
    AnimationTrack,
    CameraSpec,
    Keyframe,
    LightingSpec,
    LightSpec,
    ObjectSpec,
    RenderSpec,
    SceneProgram,
    Transform,
    WorldSpec,
)
from smcb.generation.config import DatasetConfig

TEMPLATE_ORDER = ("static_orbit", "moving_object", "moving_camera", "parent_motion")


def load_asset_index(path: Path) -> AssetIndex:
    return AssetIndex.model_validate_json(path.read_text(encoding="utf-8"))


def choose_template(config: DatasetConfig, rng: random.Random, sample_index: int) -> str:
    """Cycle the four-template smoke set; use configured weights otherwise."""
    if config.dataset.num_samples == 4 and all(
        config.templates[name] > 0 for name in TEMPLATE_ORDER
    ):
        return TEMPLATE_ORDER[sample_index % len(TEMPLATE_ORDER)]
    weights = [config.templates[name] for name in TEMPLATE_ORDER]
    return rng.choices(TEMPLATE_ORDER, weights=weights, k=1)[0]


def _instance_scale(asset: AssetIndexEntry) -> float:
    max_dimension = max(asset.dimensions)
    if max_dimension <= 1e-6:
        return 1.0
    return min(2.0, max(0.15, 1.4 / max_dimension))


def _base_objects(
    assets: list[AssetIndexEntry], rng: random.Random, template: str
) -> list[ObjectSpec]:
    count = len(assets)
    spacing = 2.4
    start_x = -spacing * (count - 1) / 2
    objects: list[ObjectSpec] = []
    for index, asset in enumerate(assets):
        scale = _instance_scale(asset)
        objects.append(
            ObjectSpec(
                id=f"object_{index + 1:03d}",
                asset_id=asset.asset_id,
                transform=Transform(
                    position=(start_x + index * spacing, rng.uniform(-0.35, 0.35), 0.0),
                    scale=(scale, scale, scale),
                ),
            )
        )
    if template == "parent_motion" and len(objects) >= 2:
        parent = objects[0]
        child_asset = assets[1]
        parent_height = assets[0].dimensions[2] * parent.transform.scale[2]
        child_scale = _instance_scale(child_asset) * 0.7
        objects[1] = objects[1].model_copy(
            update={
                "parent_id": parent.id,
                "transform": Transform(
                    position=(0.0, 0.0, max(0.25, parent_height + 0.05)),
                    scale=(child_scale, child_scale, child_scale),
                ),
            }
        )
    return objects


def _fixed_lighting() -> LightingSpec:
    return LightingSpec(
        world=WorldSpec(color=(0.055, 0.065, 0.08), strength=0.8),
        lights=[
            LightSpec(
                id="sun",
                type="SUN",
                rotation=(math.radians(25), math.radians(-20), math.radians(-35)),
                energy=2.2,
            ),
            LightSpec(
                id="key",
                type="AREA",
                position=(4.5, -5.5, 8.0),
                rotation=(math.radians(18), 0.0, math.radians(38)),
                energy=850.0,
                size=5.0,
            ),
        ],
    )


def _camera() -> CameraSpec:
    return CameraSpec(
        type="perspective",
        transform=Transform(position=(7.0, -14.0, 7.2)),
        look_at=(0.0, 0.0, 0.8),
        focal_length_mm=48.0,
    )


def _animations(template: str, objects: list[ObjectSpec], frame_end: int) -> list[AnimationTrack]:
    mid = max(2, (frame_end + 1) // 2)
    if template == "static_orbit":
        quarter = max(2, frame_end // 4)
        frames = sorted({1, quarter, frame_end // 2, quarter * 3, frame_end})
        positions = (
            (7.0, -14.0, 7.2),
            (14.5, 1.0, 7.2),
            (0.0, 15.0, 7.2),
            (-14.5, 1.0, 7.2),
            (5.0, -14.4, 7.2),
        )
        return [
            AnimationTrack(
                target_id="camera",
                property="position",
                space="world",
                keyframes=[
                    Keyframe(frame=frame, value=value)
                    for frame, value in zip(frames, positions, strict=True)
                ],
            )
        ]
    if template == "moving_camera":
        return [
            AnimationTrack(
                target_id="camera",
                property="position",
                space="world",
                keyframes=[
                    Keyframe(frame=1, value=(-8.0, -10.5, 5.6)),
                    Keyframe(frame=frame_end, value=(8.0, -14.0, 7.4)),
                ],
            )
        ]
    target = objects[0]
    start = target.transform.position
    if template == "parent_motion":
        values = (
            (start[0] - 1.4, start[1], start[2]),
            (start[0] + 1.4, start[1], start[2]),
            (start[0] + 0.7, start[1], start[2]),
        )
        target_id = target.id
    else:
        values = (
            (start[0], start[1] - 1.25, start[2]),
            (start[0], start[1] + 1.25, start[2]),
            (start[0], start[1] + 0.55, start[2]),
        )
        target_id = target.id
    return [
        AnimationTrack(
            target_id=target_id,
            property="position",
            keyframes=[
                Keyframe(frame=1, value=values[0]),
                Keyframe(frame=mid, value=values[1]),
                Keyframe(frame=frame_end, value=values[2]),
            ],
        )
    ]


def sample_scene(
    *,
    config: DatasetConfig,
    asset_index: AssetIndex,
    seed: int,
    sample_id: str,
    sample_index: int = 0,
    template: str | None = None,
) -> SceneProgram:
    """Build one fully validated Scene Program from a seed."""
    rng = random.Random(seed)
    selected_template = template or choose_template(config, rng, sample_index)
    object_count = rng.randint(config.scene.object_count.min, config.scene.object_count.max)
    if len(asset_index.assets) < object_count:
        raise ValueError(
            f"asset index has {len(asset_index.assets)} assets but scene needs {object_count}"
        )
    selected_assets = rng.sample(asset_index.assets, object_count)
    objects = _base_objects(selected_assets, rng, selected_template)
    duration = rng.randint(config.video.duration_seconds.min, config.video.duration_seconds.max)
    frame_end = duration * config.video.fps
    return SceneProgram(
        sample_id=sample_id,
        seed=seed,
        template=selected_template,  # type: ignore[arg-type]
        objects=objects,
        camera=_camera(),
        lighting=_fixed_lighting(),
        animations=_animations(selected_template, objects, frame_end),
        render=RenderSpec(
            engine="BLENDER_EEVEE_NEXT",
            width=config.video.width,
            height=config.video.height,
            fps=config.video.fps,
            frame_end=frame_end,
            samples=config.render.samples,
        ),
    )


def candidate_library(
    scene: SceneProgram, asset_index: AssetIndex, size: int, seed: int
) -> list[str]:
    """Return targets plus reproducible random distractors."""
    targets = [item.asset_id for item in scene.objects]
    remaining = [item.asset_id for item in asset_index.assets if item.asset_id not in targets]
    rng = random.Random(seed ^ 0xC0FFEE)
    distractors = rng.sample(remaining, min(max(0, size - len(targets)), len(remaining)))
    result = targets + distractors
    rng.shuffle(result)
    return result


def write_candidates(candidates: list[str], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(candidates, indent=2) + "\n", encoding="utf-8")
