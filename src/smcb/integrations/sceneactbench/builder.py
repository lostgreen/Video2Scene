"""Build and gate a deterministic local SceneAct static source sample."""

from __future__ import annotations

import hashlib
import json
import math
import subprocess
from pathlib import Path
from typing import Any

from smcb.blender.runner import render_scene
from smcb.dsl.io import load_scene, write_scene
from smcb.generation.sampler import load_asset_index
from smcb.integrations.sceneactbench.blueprints import (
    DynamicPlatformStationBlueprint,
    build_platform_station_scene,
    load_platform_station_blueprint,
    resolve_blueprint_slots,
)
from smcb.integrations.sceneactbench.contracts import (
    DynamicRenderInspection,
    DynamicSceneBuildResult,
    StaticRenderInspection,
    StaticSceneBuildResult,
)


def _json_object(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"expected a JSON object: {path}")
    return payload


def _git_commit(project_root: Path) -> str:
    completed = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=project_root,
        capture_output=True,
        text=True,
        check=False,
    )
    return completed.stdout.strip() if completed.returncode == 0 else "unknown"


def inspect_static_render(
    sample_dir: Path, *, min_visible_pixel_ratio: float = 0.0005
) -> StaticRenderInspection:
    """Require every target to stay in view and occupy a measurable image area."""
    sample_dir = sample_dir.expanduser().resolve()
    scene = load_scene(sample_dir / "scene.json")
    failures: list[str] = []
    if scene.animations:
        failures.append("invalid:animations_present")
    if scene.render.fps != 24:
        failures.append(f"invalid:fps:{scene.render.fps}")
    frame_count = scene.render.frame_end - scene.render.frame_start + 1
    if frame_count != 144:
        failures.append(f"invalid:frame_count:{frame_count}")

    visibility_path = sample_dir / "gt" / "visibility.json"
    visibility = _json_object(visibility_path) if visibility_path.is_file() else {}
    if not visibility:
        failures.append("missing:gt/visibility.json")
    ratios: dict[str, float] = {}
    visible_count = 0
    for item in scene.objects:
        if not item.target:
            continue
        record = visibility.get(item.id)
        if not isinstance(record, dict):
            failures.append(f"missing:visibility:{item.id}")
            ratios[item.id] = 0.0
            continue
        frame_ratio = float(record.get("visible_frame_ratio", 0.0))
        pixel_ratio = float(record.get("max_pixel_ratio", 0.0))
        ratios[item.id] = pixel_ratio
        if frame_ratio < 1.0:
            failures.append(f"visibility_frame_ratio:{item.id}:{frame_ratio:.6f}")
        if pixel_ratio < min_visible_pixel_ratio:
            failures.append(f"visibility_pixel_ratio:{item.id}:{pixel_ratio:.6f}")
        if frame_ratio >= 1.0 and pixel_ratio >= min_visible_pixel_ratio:
            visible_count += 1
    return StaticRenderInspection(
        sample_id=scene.sample_id,
        sample_dir=sample_dir,
        object_count=sum(item.target for item in scene.objects),
        visible_object_count=visible_count,
        min_visible_pixel_ratio=min_visible_pixel_ratio,
        object_pixel_ratios=ratios,
        failures=failures,
        passed=not failures,
    )


def inspect_dynamic_render(
    sample_dir: Path, *, min_visible_pixel_ratio: float = 0.0005
) -> DynamicRenderInspection:
    """Require two visible scoring movers with non-trivial canonical motion."""
    sample_dir = sample_dir.expanduser().resolve()
    scene = load_scene(sample_dir / "scene.json")
    failures: list[str] = []
    if scene.schema_version != "0.2":
        failures.append(f"invalid:schema_version:{scene.schema_version}")
    mover_ids = sorted(
        track.target_id
        for track in scene.animations
        if getattr(track, "scoring_role", None) == "mover"
    )
    if len(mover_ids) != 2:
        failures.append(f"invalid:mover_count:{len(mover_ids)}")
    if scene.render.fps != 24:
        failures.append(f"invalid:fps:{scene.render.fps}")
    frame_count = scene.render.frame_end - scene.render.frame_start + 1
    if frame_count != 144:
        failures.append(f"invalid:frame_count:{frame_count}")

    visibility = _json_object(sample_dir / "gt" / "visibility.json")
    trajectories = _json_object(sample_dir / "gt" / "trajectories.json")
    ratios: dict[str, float] = {}
    visible_count = 0
    for item in scene.objects:
        if not item.target:
            continue
        record = visibility.get(item.id)
        if not isinstance(record, dict):
            failures.append(f"missing:visibility:{item.id}")
            ratios[item.id] = 0.0
            continue
        frame_ratio = float(record.get("visible_frame_ratio", 0.0))
        pixel_ratio = float(record.get("max_pixel_ratio", 0.0))
        ratios[item.id] = pixel_ratio
        if frame_ratio < 1.0:
            failures.append(f"visibility_frame_ratio:{item.id}:{frame_ratio:.6f}")
        if pixel_ratio < min_visible_pixel_ratio:
            failures.append(f"visibility_pixel_ratio:{item.id}:{pixel_ratio:.6f}")
        if frame_ratio >= 1.0 and pixel_ratio >= min_visible_pixel_ratio:
            visible_count += 1

    motion_distances: dict[str, float] = {}
    for mover_id in mover_ids:
        frames = trajectories.get(mover_id)
        if not isinstance(frames, list) or len(frames) != frame_count:
            failures.append(f"trajectory_frame_count:{mover_id}")
            motion_distances[mover_id] = 0.0
            continue
        positions = [record.get("centroid", record.get("position")) for record in frames]
        if any(not isinstance(position, list) or len(position) != 3 for position in positions):
            failures.append(f"invalid:trajectory_position:{mover_id}")
            motion_distances[mover_id] = 0.0
            continue
        start = positions[0]
        distance = max(
            math.sqrt(sum((float(a) - float(b)) ** 2 for a, b in zip(start, point, strict=True)))
            for point in positions[1:]
        )
        motion_distances[mover_id] = distance
        if distance < 1.0:
            failures.append(f"insufficient_motion:{mover_id}:{distance:.6f}")
    return DynamicRenderInspection(
        sample_id=scene.sample_id,
        sample_dir=sample_dir,
        object_count=sum(item.target for item in scene.objects),
        visible_object_count=visible_count,
        min_visible_pixel_ratio=min_visible_pixel_ratio,
        object_pixel_ratios=ratios,
        mover_ids=mover_ids,
        mover_motion_distances=motion_distances,
        failures=failures,
        passed=not failures,
    )


def build_static_scene(
    *,
    blueprint_path: Path,
    asset_index_path: Path,
    output_dir: Path,
    project_root: Path,
    blender_bin: str,
    blender_script: Path,
    ffmpeg_bin: str | None = None,
    min_visible_pixel_ratio: float = 0.0005,
) -> StaticSceneBuildResult:
    """Render one static blueprint and preserve its private resolution manifest."""
    blueprint_path = blueprint_path.expanduser().resolve()
    asset_index_path = asset_index_path.expanduser().resolve()
    output_dir = output_dir.expanduser().resolve()
    if output_dir.exists():
        raise FileExistsError(f"static scene output already exists: {output_dir}")

    blueprint = load_platform_station_blueprint(blueprint_path)
    if isinstance(blueprint, DynamicPlatformStationBlueprint):
        raise ValueError("build-static requires platform_station_static")
    asset_index = load_asset_index(asset_index_path)
    resolved_slots = resolve_blueprint_slots(blueprint, asset_index)
    scene = build_platform_station_scene(blueprint, asset_index)
    output_dir.mkdir(parents=True)
    scene_path = output_dir / "scene.json"
    write_scene(scene, scene_path)

    result = render_scene(
        scene_path=scene_path,
        asset_index_path=asset_index_path,
        output_dir=output_dir,
        blender_bin=blender_bin,
        blender_script=blender_script,
        ffmpeg_bin=ffmpeg_bin,
    )
    inspection = inspect_static_render(output_dir, min_visible_pixel_ratio=min_visible_pixel_ratio)
    manifest = {
        "schema_version": "1.0",
        "sample_id": scene.sample_id,
        "template": scene.template,
        "git_commit": _git_commit(project_root),
        "blueprint_path": str(blueprint_path),
        "blueprint_sha256": hashlib.sha256(blueprint_path.read_bytes()).hexdigest(),
        "asset_index_path": str(asset_index_path),
        "asset_pack": asset_index.pack_id,
        "asset_manifest_hash": asset_index.asset_manifest_hash,
        "slots": [
            {
                "object_id": resolved.slot.id,
                "role": resolved.slot.role,
                "relation": resolved.slot.relation,
                "source_name": resolved.slot.source_name,
                "asset_id": resolved.asset.asset_id,
            }
            for resolved in resolved_slots
        ],
        "visibility_gate": inspection.model_dump(mode="json"),
    }
    (output_dir / "sceneact_build.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    if not inspection.passed:
        raise RuntimeError(
            f"static scene visibility gate failed; see {output_dir / 'sceneact_build.json'}"
        )
    return StaticSceneBuildResult(
        sample_id=scene.sample_id,
        sample_dir=output_dir,
        scene_program=scene_path,
        reference_video=result.video_path,
        preview=output_dir / "debug" / "preview.png",
        inspection=inspection,
    )


def build_dynamic_scene(
    *,
    blueprint_path: Path,
    asset_index_path: Path,
    output_dir: Path,
    project_root: Path,
    blender_bin: str,
    blender_script: Path,
    ffmpeg_bin: str | None = None,
    min_visible_pixel_ratio: float = 0.0005,
) -> DynamicSceneBuildResult:
    """Render the first two-mover canonical master for SceneAct and World-Time."""
    blueprint_path = blueprint_path.expanduser().resolve()
    asset_index_path = asset_index_path.expanduser().resolve()
    output_dir = output_dir.expanduser().resolve()
    if output_dir.exists():
        raise FileExistsError(f"dynamic scene output already exists: {output_dir}")

    blueprint = load_platform_station_blueprint(blueprint_path)
    if not isinstance(blueprint, DynamicPlatformStationBlueprint):
        raise ValueError("build-dynamic requires platform_station_dynamic")
    asset_index = load_asset_index(asset_index_path)
    resolved_slots = resolve_blueprint_slots(blueprint, asset_index)
    scene = build_platform_station_scene(blueprint, asset_index)
    output_dir.mkdir(parents=True)
    scene_path = output_dir / "scene.json"
    write_scene(scene, scene_path)
    result = render_scene(
        scene_path=scene_path,
        asset_index_path=asset_index_path,
        output_dir=output_dir,
        blender_bin=blender_bin,
        blender_script=blender_script,
        ffmpeg_bin=ffmpeg_bin,
    )
    inspection = inspect_dynamic_render(output_dir, min_visible_pixel_ratio=min_visible_pixel_ratio)
    scoring_roles = {track.target_id: track.scoring_role for track in blueprint.animations}
    manifest = {
        "schema_version": "1.0",
        "sample_id": scene.sample_id,
        "template": scene.template,
        "git_commit": _git_commit(project_root),
        "blueprint_path": str(blueprint_path),
        "blueprint_sha256": hashlib.sha256(blueprint_path.read_bytes()).hexdigest(),
        "asset_index_path": str(asset_index_path),
        "asset_pack": asset_index.pack_id,
        "asset_manifest_hash": asset_index.asset_manifest_hash,
        "slots": [
            {
                "object_id": resolved.slot.id,
                "role": resolved.slot.role,
                "relation": resolved.slot.relation,
                "source_name": resolved.slot.source_name,
                "asset_id": resolved.asset.asset_id,
                "scoring_role": scoring_roles.get(resolved.slot.id, "static"),
            }
            for resolved in resolved_slots
        ],
        "visibility_gate": inspection.model_dump(mode="json"),
    }
    (output_dir / "sceneact_build.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    if not inspection.passed:
        raise RuntimeError(f"dynamic scene gate failed; see {output_dir / 'sceneact_build.json'}")
    return DynamicSceneBuildResult(
        sample_id=scene.sample_id,
        sample_dir=output_dir,
        scene_program=scene_path,
        reference_video=result.video_path,
        preview=output_dir / "debug" / "preview.png",
        inspection=inspection,
    )
