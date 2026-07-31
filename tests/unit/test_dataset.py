"""Generated sample contract validation tests."""

import json
from pathlib import Path

from smcb.assets.models import AssetIndex, AssetIndexEntry
from smcb.dsl.io import write_scene
from smcb.generation.config import load_dataset_config
from smcb.generation.sampler import sample_scene
from smcb.storage.dataset import validate_dataset

ROOT = Path(__file__).parents[2]


def test_validate_dataset_accepts_complete_sample(tmp_path: Path) -> None:
    config = load_dataset_config(ROOT / "configs" / "dataset" / "scene_smoke.yaml")
    index = AssetIndex(
        pack_id="test",
        source_inventory_sha256="0" * 64,
        asset_manifest_hash="1" * 64,
        assets=[
            AssetIndexEntry(
                asset_id="asset_001",
                glb_path="/asset.glb",
                metadata_path="/asset.json",
                source_relative_path="asset.gltf",
                dimensions=(1.0, 1.0, 1.0),
                animation_clips=[],
            )
        ],
    )
    scene = sample_scene(
        config=config,
        asset_index=index,
        seed=42,
        sample_id="sample_000001",
        template="moving_object",
    )
    sample = tmp_path / "sample_000001"
    (sample / "gt").mkdir(parents=True)
    (sample / "debug").mkdir()
    (sample / "frames").mkdir()
    write_scene(scene, sample / "scene.json")
    for name in (
        "metadata.json",
        "input.mp4",
        "scene.blend",
        "scene.glb",
        "gt/camera.json",
        "gt/trajectories.json",
        "gt/visibility.json",
        "gt/candidates.json",
        "debug/preview.png",
    ):
        (sample / name).write_text("{}", encoding="utf-8")
    (sample / "qc.json").write_text(json.dumps({"passed": True}), encoding="utf-8")
    for frame in range(scene.render.frame_start, scene.render.frame_end + 1):
        (sample / "frames" / f"frame_{frame:04d}.png").touch()
    result = validate_dataset(tmp_path)
    assert result["passed"] is True
    assert result["valid_count"] == 1
