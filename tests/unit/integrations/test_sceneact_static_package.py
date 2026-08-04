"""Static platform-station blueprint and SceneAct package tests."""

from __future__ import annotations

import json
import os
import struct
from pathlib import Path

import pytest

from smcb.assets.models import AssetIndex, AssetIndexEntry
from smcb.dsl.io import write_scene
from smcb.integrations.sceneactbench.blueprints import (
    DynamicPlatformStationBlueprint,
    build_platform_station_scene,
    load_platform_station_blueprint,
)
from smcb.integrations.sceneactbench.packages import (
    export_dynamic_package,
    export_static_package,
    validate_dynamic_package,
    validate_static_package,
)

ROOT = Path(__file__).parents[3]
BLUEPRINT = ROOT / "configs" / "sceneact" / "platform_station_static.yaml"
DYNAMIC_BLUEPRINT = ROOT / "configs" / "sceneact" / "platform_station_dynamic.yaml"
SOURCE_NAMES = (
    "Bridge_Modular_Center",
    "Bridge_Modular",
    "Bridge_Small",
    "Door",
    "Goal_Flag",
    "Cannon",
    "Chest",
    "Bouncer",
    "Fence_Middle",
    "Fence_Corner",
)


def _glb_bytes(
    *,
    root_names: tuple[str, ...] = ("asset",),
    animated: bool = False,
    mesh_root_names: tuple[str, ...] = (),
    animated_root_names: tuple[str, ...] = (),
) -> bytes:
    payload: dict[str, object] = {
        "asset": {"version": "2.0"},
        "scene": 0,
        "scenes": [{"nodes": list(range(len(root_names)))}],
        "nodes": [
            {"name": name, **({"mesh": 0} if name in mesh_root_names else {})}
            for name in root_names
        ],
    }
    driven_names = animated_root_names or ((root_names[0],) if animated else ())
    if driven_names:
        payload["animations"] = [
            {
                "name": f"animation_{name}",
                "channels": [{"target": {"node": root_names.index(name)}}],
            }
            for name in driven_names
        ]
    encoded = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    encoded += b" " * ((-len(encoded)) % 4)
    total_length = 12 + 8 + len(encoded)
    return (
        struct.pack("<4sII", b"glTF", 2, total_length)
        + struct.pack("<I4s", len(encoded), b"JSON")
        + encoded
    )


def _asset_index(root: Path) -> tuple[AssetIndex, Path]:
    normalized = root / "normalized"
    normalized.mkdir(parents=True)
    assets: list[AssetIndexEntry] = []
    for index, source_name in enumerate(SOURCE_NAMES, start=1):
        asset_id = f"asset_hash_{index:04d}"
        glb_path = normalized / f"{asset_id}.glb"
        glb_path.write_bytes(_glb_bytes(root_names=(source_name,)))
        metadata_path = normalized / f"{asset_id}.json"
        metadata_path.write_text("{}\n", encoding="utf-8")
        assets.append(
            AssetIndexEntry(
                asset_id=asset_id,
                glb_path=str(glb_path),
                metadata_path=str(metadata_path),
                source_relative_path=f"Platformer/glTF/{source_name}.gltf",
                dimensions=(2.0, 2.0, 2.0),
                animation_clips=[],
            )
        )
    asset_index = AssetIndex(
        pack_id="fixture_pack",
        source_inventory_sha256="0" * 64,
        asset_manifest_hash="1" * 64,
        assets=assets,
    )
    index_path = normalized / "index.json"
    index_path.write_text(asset_index.model_dump_json(indent=2) + "\n", encoding="utf-8")
    return asset_index, index_path


def _dynamic_asset_index(root: Path) -> tuple[AssetIndex, Path]:
    asset_index, index_path = _asset_index(root)
    dynamic_assets = []
    for source_name in ("Bomb", "Cube_Exclamation"):
        asset_id = f"asset_hash_{source_name.casefold()}"
        glb_path = index_path.parent / f"{asset_id}.glb"
        glb_path.write_bytes(_glb_bytes(root_names=(source_name,)))
        metadata_path = index_path.parent / f"{asset_id}.json"
        metadata_path.write_text("{}\n", encoding="utf-8")
        dynamic_assets.append(
            AssetIndexEntry(
                asset_id=asset_id,
                glb_path=str(glb_path),
                metadata_path=str(metadata_path),
                source_relative_path=f"Platformer/glTF/{source_name}.gltf",
                dimensions=(2.0, 2.0, 2.0),
                animation_clips=[],
            )
        )
    asset_index = asset_index.model_copy(update={"assets": [*asset_index.assets, *dynamic_assets]})
    index_path.write_text(asset_index.model_dump_json(indent=2) + "\n", encoding="utf-8")
    return asset_index, index_path


def test_platform_station_blueprint_is_deterministic_and_structured(tmp_path: Path) -> None:
    index, _ = _asset_index(tmp_path)
    blueprint = load_platform_station_blueprint(BLUEPRINT)

    first = build_platform_station_scene(blueprint, index)
    second = build_platform_station_scene(blueprint, index)

    assert first.model_dump(mode="json") == second.model_dump(mode="json")
    assert first.template == "platform_station_static"
    assert len(first.objects) == 10
    assert not first.animations
    assert first.render.fps == 24
    assert first.render.frame_end - first.render.frame_start + 1 == 144
    positions = [item.transform.position for item in first.objects]
    assert max(point[0] for point in positions) - min(point[0] for point in positions) > 9.0
    assert max(point[1] for point in positions) - min(point[1] for point in positions) > 3.0
    assert {point[2] for point in positions} >= {0.0, 1.92, 1.98}


def test_platform_station_rejects_missing_asset(tmp_path: Path) -> None:
    index, _ = _asset_index(tmp_path)
    index = index.model_copy(update={"assets": index.assets[:-1]})
    blueprint = load_platform_station_blueprint(BLUEPRINT)

    with pytest.raises(ValueError, match="Fence_Corner.*0 index entries"):
        build_platform_station_scene(blueprint, index)


def test_dynamic_blueprint_builds_v02_with_two_scoring_movers(tmp_path: Path) -> None:
    index, _ = _dynamic_asset_index(tmp_path)
    blueprint = load_platform_station_blueprint(DYNAMIC_BLUEPRINT)

    scene = build_platform_station_scene(blueprint, index)

    assert isinstance(blueprint, DynamicPlatformStationBlueprint)
    assert scene.schema_version == "0.2"
    assert scene.template == "platform_station_dynamic"
    assert len(scene.objects) == 11
    assert [track.target_id for track in scene.animations] == [
        "mover_vehicle",
        "mover_platform",
    ]
    assert all(track.scoring_role == "mover" for track in scene.animations)  # type: ignore[union-attr]


def _write_rendered_sample(root: Path) -> Path:
    asset_index, index_path = _asset_index(root / "assets")
    blueprint = load_platform_station_blueprint(BLUEPRINT)
    scene = build_platform_station_scene(blueprint, asset_index)
    sample = root / "sample"
    (sample / "frames").mkdir(parents=True)
    (sample / "gt").mkdir()
    (sample / "debug").mkdir()
    write_scene(scene, sample / "scene.json")

    first_frame = sample / "frames" / "frame_0001.png"
    first_frame.write_bytes(b"\x89PNG\r\n\x1a\nfixture")
    for frame in range(2, 145):
        os.link(first_frame, sample / "frames" / f"frame_{frame:04d}.png")
    (sample / "input.mp4").write_bytes(b"\x00\x00\x00\x18ftypisomfixture")
    (sample / "scene.glb").write_bytes(
        _glb_bytes(root_names=tuple(item.id for item in scene.objects) + ("CameraLookAt",))
    )
    (sample / "debug" / "preview.png").write_bytes(b"\x89PNG\r\n\x1a\npreview")
    (sample / "gt" / "camera_sceneact.json").write_text(
        json.dumps(
            {
                "name": "camera",
                "type": "PERSP",
                "location": [12.0, -19.0, 10.5],
                "rotation_euler_deg": [60.0, 0.0, 30.0],
                "lens_mm": 50.0,
                "matrix_world": [
                    [1.0, 0.0, 0.0, 12.0],
                    [0.0, 1.0, 0.0, -19.0],
                    [0.0, 0.0, 1.0, 10.5],
                    [0.0, 0.0, 0.0, 1.0],
                ],
            }
        ),
        encoding="utf-8",
    )
    (sample / "gt" / "layout.json").write_text(
        json.dumps(
            {
                "sample_id": scene.sample_id,
                "objects": [
                    {"name": item.id, "location": list(item.transform.position)}
                    for item in scene.objects
                ],
            }
        ),
        encoding="utf-8",
    )
    visibility = {
        item.id: {"visible_frame_ratio": 1.0, "max_pixel_ratio": 0.01} for item in scene.objects
    }
    (sample / "gt" / "visibility.json").write_text(json.dumps(visibility), encoding="utf-8")
    slot_by_id = {slot.id: slot for slot in blueprint.slots}
    (sample / "sceneact_build.json").write_text(
        json.dumps(
            {
                "schema_version": "1.0",
                "sample_id": scene.sample_id,
                "template": scene.template,
                "git_commit": "2" * 40,
                "blueprint_sha256": "3" * 64,
                "asset_index_path": str(index_path),
                "slots": [
                    {
                        "object_id": item.id,
                        "role": slot_by_id[item.id].role,
                        "relation": slot_by_id[item.id].relation,
                        "source_name": slot_by_id[item.id].source_name,
                        "asset_id": item.asset_id,
                    }
                    for item in scene.objects
                ],
            }
        ),
        encoding="utf-8",
    )
    return sample


def test_export_static_package_is_anonymous_and_self_validating(tmp_path: Path) -> None:
    sample = _write_rendered_sample(tmp_path)
    output = tmp_path / "t6l1_local_static_001"

    package = export_static_package(sample_dir=sample, output_dir=output)
    inspection = validate_static_package(output)

    assert package.scene_id == output.name
    assert inspection.passed
    assert inspection.component_count == 10
    assert inspection.reference_frame_count == 144
    assert inspection.layout_object_count == 10
    assert inspection.mover_count == 0
    assert [path.name for path in sorted(package.components_dir.glob("*.glb"))] == [
        f"asset_{index:04d}.glb" for index in range(1, 11)
    ]
    assert json.loads(package.trajectory_json.read_text(encoding="utf-8")) == {}
    assert not any(path.is_symlink() for path in package.reference_dir.iterdir())


def test_validate_static_package_detects_component_tampering(tmp_path: Path) -> None:
    sample = _write_rendered_sample(tmp_path)
    output = tmp_path / "t6l1_local_static_002"
    export_static_package(sample_dir=sample, output_dir=output)
    (output / "components" / "asset_0001.glb").write_bytes(b"changed")

    inspection = validate_static_package(output)

    assert not inspection.passed
    assert "invalid:glb:components/asset_0001.glb" in inspection.failures
    assert "component_hash:components/asset_0001.glb" in inspection.failures


def test_validate_static_package_rejects_assembled_animations(tmp_path: Path) -> None:
    sample = _write_rendered_sample(tmp_path)
    output = tmp_path / "t6l1_local_static_003"
    export_static_package(sample_dir=sample, output_dir=output)
    meta = json.loads((output / "meta.json").read_text(encoding="utf-8"))
    root_names = tuple(item["object_id"] for item in meta["components_private"])
    (output / "gt" / "scene.glb").write_bytes(_glb_bytes(root_names=root_names, animated=True))

    inspection = validate_static_package(output)

    assert not inspection.passed
    assert "invalid:static_animations:1" in inspection.failures


def test_validate_static_package_rejects_untracked_mesh_root(tmp_path: Path) -> None:
    sample = _write_rendered_sample(tmp_path)
    output = tmp_path / "t6l1_local_static_004"
    export_static_package(sample_dir=sample, output_dir=output)
    meta = json.loads((output / "meta.json").read_text(encoding="utf-8"))
    root_names = tuple(item["object_id"] for item in meta["components_private"]) + ("Ground",)
    (output / "gt" / "scene.glb").write_bytes(
        _glb_bytes(root_names=root_names, mesh_root_names=("Ground",))
    )

    inspection = validate_static_package(output)

    assert not inspection.passed
    assert "invalid:extra_mesh_roots:Ground" in inspection.failures


def _write_dynamic_rendered_sample(root: Path) -> Path:
    asset_index, index_path = _dynamic_asset_index(root / "dynamic_assets")
    blueprint = load_platform_station_blueprint(DYNAMIC_BLUEPRINT)
    assert isinstance(blueprint, DynamicPlatformStationBlueprint)
    scene = build_platform_station_scene(blueprint, asset_index)
    sample = root / "dynamic_sample"
    (sample / "frames").mkdir(parents=True)
    (sample / "gt").mkdir()
    (sample / "debug").mkdir()
    write_scene(scene, sample / "scene.json")
    first_frame = sample / "frames" / "frame_0001.png"
    first_frame.write_bytes(b"\x89PNG\r\n\x1a\ndynamic")
    for frame in range(2, 145):
        os.link(first_frame, sample / "frames" / f"frame_{frame:04d}.png")
    (sample / "input.mp4").write_bytes(b"\x00\x00\x00\x18ftypisomdynamic")
    object_ids = tuple(item.id for item in scene.objects)
    mover_ids = ("mover_vehicle", "mover_platform")
    (sample / "scene.glb").write_bytes(
        _glb_bytes(root_names=object_ids, animated_root_names=mover_ids)
    )
    (sample / "debug" / "preview.png").write_bytes(b"\x89PNG\r\n\x1a\npreview")
    (sample / "gt" / "camera_sceneact.json").write_text(
        json.dumps(
            {
                "name": "camera",
                "type": "PERSP",
                "location": [12.0, -19.0, 10.5],
                "rotation_euler_deg": [60.0, 0.0, 30.0],
                "lens_mm": 50.0,
                "matrix_world": [
                    [1.0, 0.0, 0.0, 12.0],
                    [0.0, 1.0, 0.0, -19.0],
                    [0.0, 0.0, 1.0, 10.5],
                    [0.0, 0.0, 0.0, 1.0],
                ],
            }
        ),
        encoding="utf-8",
    )
    (sample / "gt" / "layout.json").write_text(
        json.dumps(
            {
                "sample_id": scene.sample_id,
                "objects": [
                    {"name": item.id, "location": list(item.transform.position)}
                    for item in scene.objects
                ],
            }
        ),
        encoding="utf-8",
    )
    visibility = {
        item.id: {"visible_frame_ratio": 1.0, "max_pixel_ratio": 0.01} for item in scene.objects
    }
    (sample / "gt" / "visibility.json").write_text(json.dumps(visibility), encoding="utf-8")
    trajectories: dict[str, list[dict[str, object]]] = {}
    for item in scene.objects:
        records = []
        for frame in range(1, 145):
            position = list(item.transform.position)
            if item.id == "mover_vehicle":
                position[0] = -5.3 + 10.5 * (frame - 1) / 143
            if item.id == "mover_platform":
                position[2] = 2.0 * (frame - 1) / 143
            records.append(
                {
                    "frame": frame,
                    "position": position,
                    "centroid": [position[0], position[1], position[2] + 0.25],
                    "rotation_xyzw": [0.0, 0.0, 0.0, 1.0],
                    "scale": list(item.transform.scale),
                }
            )
        trajectories[item.id] = records
    (sample / "gt" / "trajectories.json").write_text(json.dumps(trajectories), encoding="utf-8")
    slot_by_id = {slot.id: slot for slot in blueprint.slots}
    mover_set = set(mover_ids)
    (sample / "sceneact_build.json").write_text(
        json.dumps(
            {
                "schema_version": "1.0",
                "sample_id": scene.sample_id,
                "template": scene.template,
                "git_commit": "4" * 40,
                "blueprint_sha256": "5" * 64,
                "asset_index_path": str(index_path),
                "slots": [
                    {
                        "object_id": item.id,
                        "role": slot_by_id[item.id].role,
                        "relation": slot_by_id[item.id].relation,
                        "source_name": slot_by_id[item.id].source_name,
                        "asset_id": item.asset_id,
                        "scoring_role": "mover" if item.id in mover_set else "static",
                    }
                    for item in scene.objects
                ],
            }
        ),
        encoding="utf-8",
    )
    return sample


def test_export_dynamic_package_has_exact_mover_contract(tmp_path: Path) -> None:
    sample = _write_dynamic_rendered_sample(tmp_path)
    output = tmp_path / "t6l1_local_dynamic_001"

    package = export_dynamic_package(sample_dir=sample, output_dir=output)
    inspection = validate_dynamic_package(output)

    assert inspection.passed
    assert inspection.component_count == 11
    assert inspection.layout_object_count == 9
    assert inspection.mover_count == 2
    assert inspection.animated_root_names == ["mover_platform", "mover_vehicle"]
    assert inspection.trajectory_frame_counts == {
        "mover_platform": 144,
        "mover_vehicle": 144,
    }
    assert (package.gt_scene_glb.parent / "gt_scene.glb").is_file()
