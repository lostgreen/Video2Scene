"""Scene Program v0.1 and deterministic sampler tests."""

from pathlib import Path

import pytest
from pydantic import ValidationError

from smcb.assets.models import AssetIndex, AssetIndexEntry
from smcb.dsl.models import ObjectSpec, SceneProgram
from smcb.generation.config import load_dataset_config
from smcb.generation.sampler import TEMPLATE_ORDER, candidate_library, sample_scene

ROOT = Path(__file__).parents[2]


def asset_index(count: int = 24) -> AssetIndex:
    entries = [
        AssetIndexEntry(
            asset_id=f"asset_{index:03d}",
            glb_path=f"/assets/asset_{index:03d}.glb",
            metadata_path=f"/assets/asset_{index:03d}.json",
            source_relative_path=f"Category/glTF/asset_{index:03d}.gltf",
            dimensions=(1.0 + index * 0.01, 1.0, 1.2),
            animation_clips=[],
        )
        for index in range(count)
    ]
    return AssetIndex(
        pack_id="test_pack",
        source_inventory_sha256="0" * 64,
        asset_manifest_hash="1" * 64,
        assets=entries,
    )


@pytest.mark.parametrize("template", TEMPLATE_ORDER)
def test_all_templates_are_valid_and_deterministic(template: str) -> None:
    config = load_dataset_config(ROOT / "configs" / "dataset" / "smoke.yaml")
    first = sample_scene(
        config=config,
        asset_index=asset_index(),
        seed=42,
        sample_id="sample_000001",
        template=template,
    )
    second = sample_scene(
        config=config,
        asset_index=asset_index(),
        seed=42,
        sample_id="sample_000001",
        template=template,
    )
    assert first.model_dump(mode="json") == second.model_dump(mode="json")
    assert first.coordinate_system.quaternion_order == "xyzw"
    assert all(track.interpolation == "linear" for track in first.animations)
    if template == "parent_motion":
        assert first.objects[1].parent_id == first.objects[0].id


def test_candidate_library_contains_targets() -> None:
    config = load_dataset_config(ROOT / "configs" / "dataset" / "smoke.yaml")
    index = asset_index()
    scene = sample_scene(
        config=config,
        asset_index=index,
        seed=7,
        sample_id="sample_000001",
        template="moving_object",
    )
    candidates = candidate_library(scene, index, size=20, seed=7)
    assert len(candidates) == 20
    assert {item.asset_id for item in scene.objects}.issubset(candidates)


def test_unknown_parent_is_rejected() -> None:
    config = load_dataset_config(ROOT / "configs" / "dataset" / "scene_smoke.yaml")
    scene = sample_scene(
        config=config,
        asset_index=asset_index(),
        seed=3,
        sample_id="sample_000001",
        template="moving_object",
    )
    payload = scene.model_dump(mode="json")
    payload["objects"] = [
        ObjectSpec.model_validate(payload["objects"][0])
        .model_copy(update={"parent_id": "missing"})
        .model_dump(mode="json")
    ]
    with pytest.raises(ValidationError, match="unknown parent_id"):
        SceneProgram.model_validate(payload)
