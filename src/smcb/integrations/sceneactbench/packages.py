"""Export and validate SceneAct-compatible local scene packages."""

from __future__ import annotations

import hashlib
import json
import math
import os
import re
import shutil
from collections import Counter
from pathlib import Path
from typing import Any

from smcb.dsl.io import load_scene
from smcb.generation.sampler import load_asset_index
from smcb.integrations.sceneactbench.builder import inspect_static_render
from smcb.integrations.sceneactbench.contracts import (
    SceneActDynamicPackage,
    SceneActPackageInspection,
)
from smcb.integrations.sceneactbench.samples import validate_scene_id

_ANONYMOUS_COMPONENT = re.compile(r"^asset_[0-9]{4}\.glb$")


def _json_object(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"expected a JSON object: {path}")
    return payload


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _link_or_copy(source: Path, destination: Path) -> None:
    """Use hard links for static frame reuse, with a cross-filesystem fallback."""
    destination.parent.mkdir(parents=True, exist_ok=True)
    try:
        os.link(source, destination)
    except OSError:
        shutil.copy2(source, destination)


def _copy(source: Path, destination: Path) -> None:
    if not source.is_file():
        raise FileNotFoundError(f"required package source is missing: {source}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, destination)


def _yaw_degrees(rotation_xyzw: tuple[float, float, float, float]) -> float:
    x, y, z, w = rotation_xyzw
    sin_yaw = 2.0 * (w * z + x * y)
    cos_yaw = 1.0 - 2.0 * (y * y + z * z)
    return math.degrees(math.atan2(sin_yaw, cos_yaw))


def package_from_scene_dir(scene_dir: Path) -> SceneActDynamicPackage:
    """Resolve typed paths from a package root without reading large payloads."""
    scene_dir = scene_dir.expanduser().resolve()
    meta = _json_object(scene_dir / "meta.json")
    return SceneActDynamicPackage(
        scene_id=str(meta.get("sample_id", scene_dir.name)),
        fps=int(meta.get("fps", 0)),
        frame_count=int(meta.get("n_frames", 0)),
        components_dir=scene_dir / "components",
        reference_dir=scene_dir / "reference",
        reference_video=scene_dir / "reference.mp4",
        gt_scene_glb=scene_dir / "gt" / "scene.glb",
        trajectory_json=scene_dir / "gt" / "trajectory.json",
        layout_gt_json=scene_dir / "layout_gt.json",
        camera_json=scene_dir / "camera.json",
        meta_json=scene_dir / "meta.json",
        preview_png=scene_dir / "preview.png",
    )


def export_static_package(
    *,
    sample_dir: Path,
    output_dir: Path,
    min_visible_pixel_ratio: float = 0.0005,
) -> SceneActDynamicPackage:
    """Convert one gated static render into the M2 SceneAct directory contract."""
    sample_dir = sample_dir.expanduser().resolve()
    output_dir = output_dir.expanduser().resolve()
    if output_dir.exists():
        raise FileExistsError(f"SceneAct package output already exists: {output_dir}")
    scene_id = validate_scene_id(output_dir.name)
    scene = load_scene(sample_dir / "scene.json")
    if scene.template != "platform_station_static" or scene.animations:
        raise ValueError("static package export requires an animation-free platform station")
    if not 6 <= len(scene.objects) <= 10:
        raise ValueError("static package export requires 6-10 component instances")
    inspection = inspect_static_render(sample_dir, min_visible_pixel_ratio=min_visible_pixel_ratio)
    if not inspection.passed:
        raise ValueError(f"static render failed visibility gate: {inspection.failures}")

    build_manifest = _json_object(sample_dir / "sceneact_build.json")
    asset_index = load_asset_index(Path(str(build_manifest["asset_index_path"])))
    assets_by_id = {entry.asset_id: entry for entry in asset_index.assets}
    slot_records = build_manifest.get("slots")
    if not isinstance(slot_records, list):
        raise ValueError("sceneact_build.json does not contain a slots list")
    slots_by_object = {
        str(record["object_id"]): record for record in slot_records if isinstance(record, dict)
    }
    if set(slots_by_object) != {item.id for item in scene.objects}:
        raise ValueError("build manifest slots do not match Scene Program objects")

    source_frames = sorted((sample_dir / "frames").glob("frame_*.png"))
    expected_frames = scene.render.frame_end - scene.render.frame_start + 1
    if len(source_frames) != expected_frames:
        raise ValueError(f"source frame count mismatch: {len(source_frames)} != {expected_frames}")

    output_dir.mkdir(parents=True)
    components_dir = output_dir / "components"
    reference_dir = output_dir / "reference"
    gt_dir = output_dir / "gt"
    components_dir.mkdir()
    reference_dir.mkdir()
    gt_dir.mkdir()

    component_meta: list[dict[str, Any]] = []
    for index, object_spec in enumerate(scene.objects, start=1):
        try:
            asset = assets_by_id[object_spec.asset_id]
        except KeyError as error:
            raise ValueError(
                f"asset missing from recorded index: {object_spec.asset_id}"
            ) from error
        source = Path(asset.glb_path)
        anonymous_name = f"asset_{index:04d}.glb"
        destination = components_dir / anonymous_name
        _copy(source, destination)
        slot = slots_by_object[object_spec.id]
        component_meta.append(
            {
                "file": f"components/{anonymous_name}",
                "sha256": _sha256(destination),
                "object_id": object_spec.id,
                "asset_id": object_spec.asset_id,
                "source_name": slot["source_name"],
                "role": slot["role"],
                "relation": slot["relation"],
            }
        )

    for source in source_frames:
        _link_or_copy(source, reference_dir / source.name)
    _copy(sample_dir / "input.mp4", output_dir / "reference.mp4")
    _copy(sample_dir / "scene.glb", gt_dir / "scene.glb")
    _copy(sample_dir / "debug" / "preview.png", output_dir / "preview.png")
    _copy(sample_dir / "gt" / "camera_sceneact.json", output_dir / "camera.json")
    (gt_dir / "trajectory.json").write_text("{}\n", encoding="utf-8")

    layout_source = _json_object(sample_dir / "gt" / "layout.json")
    source_objects = layout_source.get("objects")
    if not isinstance(source_objects, list):
        raise ValueError("compiled gt/layout.json does not contain an objects list")
    source_by_name = {str(item["name"]): item for item in source_objects if isinstance(item, dict)}
    if set(source_by_name) != {item.id for item in scene.objects}:
        raise ValueError("compiled layout objects do not match Scene Program objects")
    layout_objects: list[dict[str, Any]] = []
    for object_spec in scene.objects:
        slot = slots_by_object[object_spec.id]
        layout_objects.append(
            {
                "name": object_spec.id,
                "type": slot["role"],
                "location": source_by_name[object_spec.id]["location"],
                "scale": object_spec.transform.scale[0],
                "rotZ_deg": round(_yaw_degrees(object_spec.transform.rotation), 6),
            }
        )
    type_counts = Counter(str(item["type"]) for item in layout_objects)
    layout_payload = {
        "sample_id": scene_id,
        "n_static_objects": len(layout_objects),
        "type_counts": dict(sorted(type_counts.items())),
        "objects": layout_objects,
    }
    (output_dir / "layout_gt.json").write_text(
        json.dumps(layout_payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )

    meta = {
        "schema_version": "1.0",
        "sample_id": scene_id,
        "source_sample_id": scene.sample_id,
        "task": "task6_anim",
        "level": 1,
        "level_name": "local_platform_station_static",
        "scene": scene.template,
        "n_frames": expected_frames,
        "fps": scene.render.fps,
        "coordinate_system": scene.coordinate_system.model_dump(mode="json"),
        "movers": [],
        "static_decor": [item.id for item in scene.objects],
        "evaluation": {"static_only": True, "sceneact_dynamic_scorer_ready": False},
        "generator": {
            "git_commit": build_manifest.get("git_commit", "unknown"),
            "blueprint_sha256": build_manifest.get("blueprint_sha256"),
            "asset_pack": asset_index.pack_id,
            "asset_manifest_hash": asset_index.asset_manifest_hash,
        },
        "components_private": component_meta,
    }
    (output_dir / "meta.json").write_text(
        json.dumps(meta, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )

    package = package_from_scene_dir(output_dir)
    package_inspection = validate_static_package(output_dir)
    if not package_inspection.passed:
        raise RuntimeError(
            f"exported SceneAct package failed validation: {', '.join(package_inspection.failures)}"
        )
    return package


def _has_magic(path: Path, magic: bytes, *, offset: int = 0) -> bool:
    if not path.is_file():
        return False
    with path.open("rb") as handle:
        handle.seek(offset)
        return handle.read(len(magic)) == magic


def validate_static_package(scene_dir: Path) -> SceneActPackageInspection:
    """Validate paths, anonymity, cardinalities, metadata, hashes, and file signatures."""
    scene_dir = scene_dir.expanduser().resolve()
    failures: list[str] = []
    meta: dict[str, Any] = {}
    try:
        meta = _json_object(scene_dir / "meta.json")
    except (OSError, ValueError, json.JSONDecodeError) as error:
        failures.append(f"invalid:meta.json:{type(error).__name__}")
    scene_id = str(meta.get("sample_id", scene_dir.name))
    try:
        validate_scene_id(scene_id)
    except ValueError:
        failures.append(f"invalid:scene_id:{scene_id}")
    if scene_id != scene_dir.name:
        failures.append(f"sample_id_mismatch:{scene_id}:{scene_dir.name}")
    fps = int(meta.get("fps", 0))
    frame_count = int(meta.get("n_frames", 0))
    if fps != 24:
        failures.append(f"invalid:fps:{fps}")
    if frame_count != 144:
        failures.append(f"invalid:n_frames:{frame_count}")

    required_files = (
        "reference.mp4",
        "gt/scene.glb",
        "gt/trajectory.json",
        "camera.json",
        "layout_gt.json",
        "meta.json",
        "preview.png",
    )
    failures.extend(
        f"missing:{relative}" for relative in required_files if not (scene_dir / relative).is_file()
    )

    components = sorted((scene_dir / "components").glob("*.glb"))
    references = sorted((scene_dir / "reference").glob("*.png"))
    if not 6 <= len(components) <= 10:
        failures.append(f"component_count:{len(components)}")
    expected_component_names = [f"asset_{index:04d}.glb" for index in range(1, len(components) + 1)]
    if [path.name for path in components] != expected_component_names:
        failures.append("invalid:component_names")
    if any(not _ANONYMOUS_COMPONENT.fullmatch(path.name) for path in components):
        failures.append("invalid:component_anonymity")
    expected_reference_names = [f"frame_{frame:04d}.png" for frame in range(1, frame_count + 1)]
    if [path.name for path in references] != expected_reference_names:
        failures.append(f"reference_frame_count:{len(references)}:{frame_count}")
    if any(path.is_symlink() for path in [*components, *references]):
        failures.append("invalid:symlink_payload")

    for path in [*components, scene_dir / "gt" / "scene.glb"]:
        if path.is_file() and not _has_magic(path, b"glTF"):
            failures.append(f"invalid:glb:{path.relative_to(scene_dir)}")
    for path in references[:1] + [scene_dir / "preview.png"]:
        if path.is_file() and not _has_magic(path, b"\x89PNG\r\n\x1a\n"):
            failures.append(f"invalid:png:{path.relative_to(scene_dir)}")
    video = scene_dir / "reference.mp4"
    if video.is_file() and not _has_magic(video, b"ftyp", offset=4):
        failures.append("invalid:reference.mp4")

    trajectory: dict[str, Any] = {}
    layout: dict[str, Any] = {}
    camera: dict[str, Any] = {}
    try:
        trajectory = _json_object(scene_dir / "gt" / "trajectory.json")
        layout = _json_object(scene_dir / "layout_gt.json")
        camera = _json_object(scene_dir / "camera.json")
    except (OSError, ValueError, json.JSONDecodeError) as error:
        failures.append(f"invalid:package_json:{type(error).__name__}")
    if trajectory:
        failures.append(f"invalid:static_movers:{len(trajectory)}")
    layout_objects = layout.get("objects", [])
    if not isinstance(layout_objects, list):
        failures.append("invalid:layout_objects")
        layout_objects = []
    if len(layout_objects) != len(components):
        failures.append(f"layout_object_count:{len(layout_objects)}:{len(components)}")
    if layout.get("sample_id") != scene_id:
        failures.append("invalid:layout_sample_id")
    camera_keys = {"name", "type", "location", "rotation_euler_deg", "lens_mm", "matrix_world"}
    if not camera_keys.issubset(camera):
        failures.append("invalid:camera_contract")

    component_meta = meta.get("components_private", [])
    if not isinstance(component_meta, list) or len(component_meta) != len(components):
        failures.append("invalid:components_private")
    else:
        for item in component_meta:
            if not isinstance(item, dict):
                failures.append("invalid:component_metadata_record")
                continue
            path = scene_dir / str(item.get("file", ""))
            if not path.is_file() or item.get("sha256") != _sha256(path):
                failures.append(f"component_hash:{item.get('file', '')}")

    return SceneActPackageInspection(
        scene_id=scene_id,
        scene_dir=scene_dir,
        fps=fps,
        frame_count=frame_count,
        component_count=len(components),
        reference_frame_count=len(references),
        layout_object_count=len(layout_objects),
        mover_count=len(trajectory),
        failures=failures,
        passed=not failures,
    )
