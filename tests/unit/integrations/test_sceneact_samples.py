"""Official Dynamic sample acquisition and contract tests."""

import json
from pathlib import Path
from typing import Any

import pytest

import smcb.integrations.sceneactbench.samples as sceneact_samples
import smcb.integrations.sceneactbench.scorer as sceneact_scorer
from smcb.integrations.sceneactbench.attribution import (
    SCENEACT_DATASET_REVISION,
    SCENEACT_PINNED_COMMIT,
)

SCENE_ID = "t6l1_platformer_001"


def _write_sample(output_root: Path, *, provenance: bool) -> Path:
    sample = output_root / "benchmark_t6_final" / SCENE_ID
    (sample / "gt").mkdir(parents=True)
    (sample / "meta.json").write_text(
        json.dumps({"sample_id": SCENE_ID, "fps": 24, "n_frames": 2}), encoding="utf-8"
    )
    (sample / "layout_gt.json").write_text(
        json.dumps({"objects": [{"name": "platform", "location": [0, 0, 0]}]}),
        encoding="utf-8",
    )
    (sample / "gt" / "trajectory.json").write_text(
        json.dumps(
            {
                "Hero": [
                    {"f": 1, "loc": [0, 0, 0]},
                    {"f": 2, "loc": [1, 0, 0]},
                ],
                "coins": [{"coin": "coin_1", "pos": [0, 0, 1]}],
            }
        ),
        encoding="utf-8",
    )
    (sample / "camera.json").write_text("{}", encoding="utf-8")
    (sample / "gt" / "gt_scene.glb").write_bytes(b"glb fixture")
    (sample / "preview.png").write_bytes(b"png fixture")
    (sample / "reference.mp4").write_bytes(b"mp4 fixture")
    if provenance:
        (sample / "LICENSE_DATASET.txt").write_text("CC-BY-NC-4.0\n", encoding="utf-8")
        (sample / "source.json").write_text("{}\n", encoding="utf-8")
    return sample


def test_fetch_oracle_profile_is_scoped_and_writes_provenance(
    tmp_path: Path, monkeypatch: object
) -> None:
    captured: dict[str, Any] = {}

    def fake_snapshot_download(**kwargs: Any) -> str:
        captured.update(kwargs)
        output_root = Path(kwargs["local_dir"])
        _write_sample(output_root, provenance=False)
        return str(output_root)

    monkeypatch.setattr(  # type: ignore[attr-defined]
        sceneact_samples, "_snapshot_download", fake_snapshot_download
    )

    result = sceneact_samples.fetch_dynamic_sample(
        scene_id=SCENE_ID,
        output_root=tmp_path,
        profile="oracle",
    )

    assert result.dataset_revision == SCENEACT_DATASET_REVISION
    assert result.downloaded_file_count == 7
    assert captured["revision"] == SCENEACT_DATASET_REVISION
    assert len(captured["allow_patterns"]) == 7
    sample = Path(result.sample_dir)
    source = json.loads((sample / "source.json").read_text(encoding="utf-8"))
    assert source["profile"] == "oracle"
    assert (sample / "LICENSE_DATASET.txt").is_file()


def test_inspect_filters_non_mover_trajectory_entries(tmp_path: Path) -> None:
    sample = _write_sample(tmp_path, provenance=True)

    inspection = sceneact_samples.inspect_dynamic_sample(sample)

    assert inspection.passed
    assert inspection.mover_names == ["Hero"]
    assert inspection.trajectory_frame_counts == {"Hero": 2}
    assert inspection.static_object_count == 1


@pytest.mark.parametrize("scene_id", ["../escape", "t6/scene", "platformer_001", ""])
def test_scene_id_rejects_arbitrary_paths(scene_id: str) -> None:
    with pytest.raises(ValueError):
        sceneact_samples.validate_scene_id(scene_id)


def test_oracle_uses_pinned_upstream_entrypoint(tmp_path: Path, monkeypatch: object) -> None:
    sample = _write_sample(tmp_path, provenance=True)
    upstream = tmp_path / "sceneactbench"
    metrics = upstream / "src" / "harness" / "metrics_t6.py"
    metrics.parent.mkdir(parents=True)
    metrics.write_text(
        "def evaluate_t6(agent_glb, sample_dir):\n"
        "    return {'agent_glb': agent_glb, 'sample_dir': sample_dir, 'oracle': True}\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(  # type: ignore[attr-defined]
        sceneact_scorer, "sceneact_commit", lambda _root: SCENEACT_PINNED_COMMIT
    )

    score = sceneact_scorer.score_dynamic_oracle(
        sceneact_root=upstream,
        sample_dir=sample,
    )

    assert score["oracle"] is True
    assert score["agent_glb"] == str(sample / "gt" / "gt_scene.glb")
