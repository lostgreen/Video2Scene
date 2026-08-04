"""Export and validate SceneAct-compatible local scene packages."""

from __future__ import annotations

import hashlib
import json
import math
import os
import re
import shutil
import struct
from collections import Counter
from pathlib import Path
from typing import Any

from smcb.dsl.io import load_scene
from smcb.generation.sampler import load_asset_index
from smcb.integrations.sceneactbench.builder import (
    inspect_dynamic_render,
    inspect_static_render,
)
from smcb.integrations.sceneactbench.contracts import (
    DynamicSceneActPackageInspection,
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
    dynamic_gt_scene = scene_dir / "gt" / "gt_scene.glb"
    return SceneActDynamicPackage(
        scene_id=str(meta.get("sample_id", scene_dir.name)),
        fps=int(meta.get("fps", 0)),
        frame_count=int(meta.get("n_frames", 0)),
        components_dir=scene_dir / "components",
        reference_dir=scene_dir / "reference",
        reference_video=scene_dir / "reference.mp4",
        gt_scene_glb=(
            dynamic_gt_scene if dynamic_gt_scene.is_file() else scene_dir / "gt" / "scene.glb"
        ),
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


def _read_glb_json(path: Path) -> dict[str, Any]:
    with path.open("rb") as handle:
        header = handle.read(20)
        if len(header) != 20:
            raise ValueError("truncated GLB header")
        magic, version, total_length = struct.unpack("<4sII", header[:12])
        chunk_length, chunk_type = struct.unpack("<I4s", header[12:20])
        if magic != b"glTF" or version != 2 or total_length != path.stat().st_size:
            raise ValueError("invalid GLB header")
        if chunk_type != b"JSON":
            raise ValueError("first GLB chunk is not JSON")
        payload = json.loads(handle.read(chunk_length).decode("utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("GLB JSON chunk is not an object")
    return payload


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

    component_gltfs: list[dict[str, Any]] = []
    for path in components:
        try:
            component_gltfs.append(_read_glb_json(path))
        except (OSError, ValueError, json.JSONDecodeError):
            failures.append(f"invalid:glb:{path.relative_to(scene_dir)}")
    scene_gltf: dict[str, Any] = {}
    scene_glb = scene_dir / "gt" / "scene.glb"
    if scene_glb.is_file():
        try:
            scene_gltf = _read_glb_json(scene_glb)
        except (OSError, ValueError, json.JSONDecodeError):
            failures.append("invalid:glb:gt/scene.glb")
    if scene_gltf.get("animations"):
        failures.append(f"invalid:static_animations:{len(scene_gltf['animations'])}")
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

    if scene_gltf and isinstance(component_meta, list):
        expected_root_names = {
            str(item.get("object_id")) for item in component_meta if isinstance(item, dict)
        }
        nodes = scene_gltf.get("nodes", [])
        scenes = scene_gltf.get("scenes", [])
        scene_index = int(scene_gltf.get("scene", 0))
        if (
            not isinstance(nodes, list)
            or not isinstance(scenes, list)
            or scene_index >= len(scenes)
        ):
            failures.append("invalid:glb_scene_graph")
        else:
            root_indices = scenes[scene_index].get("nodes", [])
            root_names = {
                str(nodes[index].get("name", ""))
                for index in root_indices
                if isinstance(index, int) and 0 <= index < len(nodes)
            }
            missing_roots = sorted(expected_root_names - root_names)
            if missing_roots:
                failures.append(f"missing:stable_glb_roots:{','.join(missing_roots)}")

            def subtree_has_mesh(node_index: int) -> bool:
                node = nodes[node_index]
                if "mesh" in node:
                    return True
                return any(
                    subtree_has_mesh(child)
                    for child in node.get("children", [])
                    if isinstance(child, int) and 0 <= child < len(nodes)
                )

            extra_mesh_roots = sorted(
                str(nodes[index].get("name", ""))
                for index in root_indices
                if isinstance(index, int)
                and 0 <= index < len(nodes)
                and str(nodes[index].get("name", "")) not in expected_root_names
                and subtree_has_mesh(index)
            )
            if extra_mesh_roots:
                failures.append(f"invalid:extra_mesh_roots:{','.join(extra_mesh_roots)}")

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


def export_dynamic_package(
    *,
    sample_dir: Path,
    output_dir: Path,
    min_visible_pixel_ratio: float = 0.0005,
) -> SceneActDynamicPackage:
    """Export the two-mover canonical master in the pinned Dynamic contract."""
    sample_dir = sample_dir.expanduser().resolve()
    output_dir = output_dir.expanduser().resolve()
    if output_dir.exists():
        raise FileExistsError(f"SceneAct package output already exists: {output_dir}")
    scene_id = validate_scene_id(output_dir.name)
    scene = load_scene(sample_dir / "scene.json")
    if scene.schema_version != "0.2" or scene.template != "platform_station_dynamic":
        raise ValueError("dynamic package export requires platform_station_dynamic v0.2")
    mover_ids = sorted(
        track.target_id
        for track in scene.animations
        if getattr(track, "scoring_role", None) == "mover"
    )
    if len(mover_ids) != 2:
        raise ValueError("dynamic package export requires exactly two scoring movers")
    inspection = inspect_dynamic_render(sample_dir, min_visible_pixel_ratio=min_visible_pixel_ratio)
    if not inspection.passed:
        raise ValueError(f"dynamic render failed gate: {inspection.failures}")

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
    frame_count = scene.render.frame_end - scene.render.frame_start + 1
    if len(source_frames) != frame_count:
        raise ValueError(f"source frame count mismatch: {len(source_frames)} != {frame_count}")

    output_dir.mkdir(parents=True)
    components_dir = output_dir / "components"
    reference_dir = output_dir / "reference"
    gt_dir = output_dir / "gt"
    components_dir.mkdir()
    reference_dir.mkdir()
    gt_dir.mkdir()
    component_meta: list[dict[str, Any]] = []
    for index, object_spec in enumerate(scene.objects, start=1):
        asset = assets_by_id[object_spec.asset_id]
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
                "scoring_role": slot.get("scoring_role", "static"),
            }
        )
    for source in source_frames:
        _link_or_copy(source, reference_dir / source.name)
    _copy(sample_dir / "input.mp4", output_dir / "reference.mp4")
    _copy(sample_dir / "scene.glb", gt_dir / "scene.glb")
    _link_or_copy(gt_dir / "scene.glb", gt_dir / "gt_scene.glb")
    _copy(sample_dir / "debug" / "preview.png", output_dir / "preview.png")
    _copy(sample_dir / "gt" / "camera_sceneact.json", output_dir / "camera.json")

    dense_trajectories = _json_object(sample_dir / "gt" / "trajectories.json")
    trajectory_payload: dict[str, list[dict[str, Any]]] = {}
    for mover_id in mover_ids:
        records = dense_trajectories.get(mover_id)
        if not isinstance(records, list) or len(records) != frame_count:
            raise ValueError(f"invalid dense mover trajectory: {mover_id}")
        trajectory_payload[mover_id] = [
            {"f": int(record["frame"]), "loc": record["centroid"]} for record in records
        ]
    (gt_dir / "trajectory.json").write_text(
        json.dumps(trajectory_payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )

    layout_source = _json_object(sample_dir / "gt" / "layout.json")
    source_objects = layout_source.get("objects")
    if not isinstance(source_objects, list):
        raise ValueError("compiled gt/layout.json does not contain an objects list")
    source_by_name = {str(item["name"]): item for item in source_objects if isinstance(item, dict)}
    layout_objects: list[dict[str, Any]] = []
    for object_spec in scene.objects:
        if object_spec.id in mover_ids:
            continue
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
    (output_dir / "layout_gt.json").write_text(
        json.dumps(
            {
                "sample_id": scene_id,
                "n_static_objects": len(layout_objects),
                "type_counts": dict(sorted(type_counts.items())),
                "objects": layout_objects,
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    meta = {
        "schema_version": "1.0",
        "sample_id": scene_id,
        "source_sample_id": scene.sample_id,
        "task": "task6_anim",
        "level": 1,
        "level_name": "local_platform_station_dynamic",
        "scene": scene.template,
        "n_frames": frame_count,
        "fps": scene.render.fps,
        "coordinate_system": scene.coordinate_system.model_dump(mode="json"),
        "movers": mover_ids,
        "static_decor": [item.id for item in scene.objects if item.id not in mover_ids],
        "evaluation": {"static_only": False, "sceneact_dynamic_scorer_ready": True},
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
    package_inspection = validate_dynamic_package(output_dir)
    if not package_inspection.passed:
        raise RuntimeError(
            f"exported Dynamic package failed validation: {', '.join(package_inspection.failures)}"
        )
    return package


def _animated_top_level_roots(gltf: dict[str, Any]) -> set[str]:
    nodes = gltf.get("nodes", [])
    scenes = gltf.get("scenes", [])
    scene_index = int(gltf.get("scene", 0))
    if not isinstance(nodes, list) or not isinstance(scenes, list) or scene_index >= len(scenes):
        return set()
    root_indices = set(scenes[scene_index].get("nodes", []))
    parents: dict[int, int] = {}
    for parent_index, node in enumerate(nodes):
        for child in node.get("children", []):
            if isinstance(child, int):
                parents[child] = parent_index
    driven: set[int] = set()
    for animation in gltf.get("animations", []):
        for channel in animation.get("channels", []):
            node_index = channel.get("target", {}).get("node")
            if isinstance(node_index, int):
                while node_index not in root_indices and node_index in parents:
                    node_index = parents[node_index]
                if node_index in root_indices:
                    driven.add(node_index)
    return {str(nodes[index].get("name", "")) for index in driven}


def validate_dynamic_package(scene_dir: Path) -> DynamicSceneActPackageInspection:
    """Validate the exact two-mover SceneAct package without invoking Blender."""
    scene_dir = scene_dir.expanduser().resolve()
    failures: list[str] = []
    try:
        meta = _json_object(scene_dir / "meta.json")
    except (OSError, ValueError, json.JSONDecodeError) as error:
        meta = {}
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
    required = (
        "reference.mp4",
        "gt/scene.glb",
        "gt/gt_scene.glb",
        "gt/trajectory.json",
        "camera.json",
        "layout_gt.json",
        "meta.json",
        "preview.png",
    )
    failures.extend(
        f"missing:{relative}" for relative in required if not (scene_dir / relative).is_file()
    )
    components = sorted((scene_dir / "components").glob("*.glb"))
    references = sorted((scene_dir / "reference").glob("*.png"))
    if not 6 <= len(components) <= 20:
        failures.append(f"component_count:{len(components)}")
    if [path.name for path in components] != [
        f"asset_{index:04d}.glb" for index in range(1, len(components) + 1)
    ]:
        failures.append("invalid:component_names")
    if [path.name for path in references] != [
        f"frame_{frame:04d}.png" for frame in range(1, frame_count + 1)
    ]:
        failures.append(f"reference_frame_count:{len(references)}:{frame_count}")

    scene_gltf: dict[str, Any] = {}
    try:
        scene_gltf = _read_glb_json(scene_dir / "gt" / "scene.glb")
    except (OSError, ValueError, json.JSONDecodeError):
        failures.append("invalid:glb:gt/scene.glb")
    animation_count = len(scene_gltf.get("animations", []))
    if animation_count == 0:
        failures.append("invalid:no_animations")
    animated_roots = sorted(_animated_top_level_roots(scene_gltf))
    mover_ids = sorted(str(item) for item in meta.get("movers", []))
    if animated_roots != mover_ids:
        failures.append(f"animated_root_mismatch:{','.join(animated_roots)}:{','.join(mover_ids)}")

    try:
        trajectory = _json_object(scene_dir / "gt" / "trajectory.json")
        layout = _json_object(scene_dir / "layout_gt.json")
        camera = _json_object(scene_dir / "camera.json")
    except (OSError, ValueError, json.JSONDecodeError) as error:
        trajectory, layout, camera = {}, {}, {}
        failures.append(f"invalid:package_json:{type(error).__name__}")
    trajectory_counts: dict[str, int] = {}
    if sorted(trajectory) != mover_ids or len(mover_ids) != 2:
        failures.append("invalid:mover_trajectory_names")
    for mover_id, records in trajectory.items():
        if not isinstance(records, list):
            failures.append(f"invalid:trajectory:{mover_id}")
            continue
        trajectory_counts[mover_id] = len(records)
        frames = [record.get("f") for record in records if isinstance(record, dict)]
        if frames != list(range(1, frame_count + 1)):
            failures.append(f"trajectory_frame_count:{mover_id}:{len(records)}")
        if any(
            not isinstance(record.get("loc"), list) or len(record["loc"]) != 3
            for record in records
            if isinstance(record, dict)
        ):
            failures.append(f"invalid:trajectory_location:{mover_id}")
    layout_objects = layout.get("objects", [])
    if not isinstance(layout_objects, list):
        layout_objects = []
        failures.append("invalid:layout_objects")
    if len(layout_objects) != len(components) - len(mover_ids):
        failures.append(
            f"layout_object_count:{len(layout_objects)}:{len(components) - len(mover_ids)}"
        )
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
    if (scene_dir / "gt" / "scene.glb").is_file() and (scene_dir / "gt" / "gt_scene.glb").is_file():
        if _sha256(scene_dir / "gt" / "scene.glb") != _sha256(scene_dir / "gt" / "gt_scene.glb"):
            failures.append("invalid:gt_scene_alias")
    return DynamicSceneActPackageInspection(
        scene_id=scene_id,
        scene_dir=scene_dir,
        fps=fps,
        frame_count=frame_count,
        component_count=len(components),
        reference_frame_count=len(references),
        layout_object_count=len(layout_objects),
        mover_count=len(trajectory),
        animation_count=animation_count,
        animated_root_names=animated_roots,
        trajectory_frame_counts=trajectory_counts,
        failures=failures,
        passed=not failures,
    )
