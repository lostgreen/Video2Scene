"""Blind task packaging, submission-gate, and report tests."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

from smcb.dsl.io import load_scene, write_scene
from smcb.dsl.models import (
    CameraSpec,
    Keyframe,
    LightingSpec,
    LightSpec,
    MotionTrackV02,
    ObjectSpec,
    RenderSpec,
    SceneProgramV02,
    Transform,
)
from smcb.worldtime.benchmark import (
    build_model_evaluation_task,
    evaluate_model_submission,
    inspect_model_submission,
)
from smcb.worldtime.schema import Timeline, TimelineSegment


def _scene() -> SceneProgramV02:
    return SceneProgramV02(
        sample_id="canonical_platform_station",
        seed=17,
        template="platform_station_dynamic",
        objects=[
            ObjectSpec(id="mover_vehicle", asset_id="asset_vehicle"),
            ObjectSpec(
                id="platform_static",
                asset_id="asset_platform",
                transform=Transform(position=(0.0, 2.0, 0.0)),
            ),
        ],
        camera=CameraSpec(
            transform=Transform(position=(5.0, -8.0, 4.0)),
            look_at=(0.0, 0.0, 0.5),
        ),
        lighting=LightingSpec(lights=[LightSpec(id="sun", type="SUN", energy=2.0)]),
        animations=[
            MotionTrackV02(
                target_id="mover_vehicle",
                property="position",
                space="world",
                scoring_role="mover",
                keyframes=[
                    Keyframe(frame=1, value=(0.0, 0.0, 0.0)),
                    Keyframe(frame=4, value=(1.5, 0.0, 0.0)),
                ],
            )
        ],
        render=RenderSpec(width=64, height=64, fps=2, frame_end=4),
    )


def _timeline() -> Timeline:
    return Timeline(
        fps=2,
        video_frame_count=4,
        world_duration=1.5,
        segments=[
            TimelineSegment(
                video_start_frame=0,
                video_end_frame=1,
                world_start_time=0.0,
                world_end_time=0.5,
            ),
            TimelineSegment(
                video_start_frame=2,
                video_end_frame=3,
                world_start_time=0.0,
                world_end_time=0.5,
            ),
        ],
    )


def _build_task(tmp_path: Path, monkeypatch: object) -> Path:
    canonical = tmp_path / "canonical"
    observation = tmp_path / "observation"
    canonical.mkdir()
    observation.mkdir()
    write_scene(_scene(), canonical / "scene.json")
    (observation / "input.mp4").write_bytes(b"test-video")
    (observation / "timeline.json").write_text(
        _timeline().model_dump_json(indent=2) + "\n",
        encoding="utf-8",
    )
    (observation / "edit_program.json").write_text(
        json.dumps({"preset": "replay"}) + "\n",
        encoding="utf-8",
    )

    def fake_contact_sheet(*, video: Path, output: Path, ffmpeg_bin: str) -> None:
        assert video.name == "input.mp4"
        assert ffmpeg_bin == "ffmpeg-test"
        output.write_bytes(b"test-image")

    monkeypatch.setattr(  # type: ignore[attr-defined]
        "smcb.worldtime.benchmark._make_contact_sheet",
        fake_contact_sheet,
    )
    task_dir = tmp_path / "task"
    build_model_evaluation_task(
        canonical_sample_dir=canonical,
        observation_dir=observation,
        output_dir=task_dir,
        task_id="blind_replay_001",
        ffmpeg_bin="ffmpeg-test",
    )
    return task_dir


def _valid_submission(task_dir: Path, submission_dir: Path) -> None:
    submission_dir.mkdir(parents=True)
    initial = load_scene(task_dir / "public" / "initial_scene.json")
    assert isinstance(initial, SceneProgramV02)
    prediction = initial.model_copy(
        update={
            "animations": [
                MotionTrackV02(
                    target_id="object_0001",
                    property="position",
                    space="world",
                    scoring_role="mover",
                    keyframes=[
                        Keyframe(frame=1, value=(0.0, 0.0, 0.0)),
                        Keyframe(frame=4, value=(1.5, 0.0, 0.0)),
                    ],
                )
            ]
        }
    )
    write_scene(prediction, submission_dir / "scene_program.json")
    shutil.copy2(task_dir / "private" / "timeline.json", submission_dir / "timeline.json")
    (submission_dir / "answer.md").write_text(
        "Detected one replay boundary and one moving object.\n",
        encoding="utf-8",
    )


def _score(*, recall: float, error: float) -> dict[str, float]:
    return {
        "mean_vehicle_err": error,
        "worst_vehicle_err": error,
        "movable_recall": recall,
        "mover_count_err": 1.0 - recall,
        "direction_error_rate": 0.0 if recall else 1.0,
        "path_shape_err": error,
        "scale_error": 0.0,
        "layout_err": 0.01,
    }


def test_task_public_contract_is_anonymous_and_gt_is_private(
    tmp_path: Path, monkeypatch: object
) -> None:
    task_dir = _build_task(tmp_path, monkeypatch)

    public_names = sorted(path.name for path in (task_dir / "public").iterdir())
    assert public_names == [
        "PROMPT.md",
        "initial_scene.json",
        "input.mp4",
        "observation_contact_sheet.jpg",
        "scene_program.schema.json",
        "task.json",
        "timeline.schema.json",
    ]
    public_text = "\n".join(
        path.read_text(encoding="utf-8")
        for path in (task_dir / "public").iterdir()
        if path.suffix in {".json", ".md"}
    )
    assert "mover_vehicle" not in public_text
    assert "platform_static" not in public_text
    assert str(tmp_path) not in public_text
    initial = load_scene(task_dir / "public" / "initial_scene.json")
    assert isinstance(initial, SceneProgramV02)
    assert [item.id for item in initial.objects] == ["object_0001", "object_0002"]
    assert initial.animations == []
    assert (task_dir / "private" / "timeline.json").is_file()
    assert (task_dir / "private" / "object_id_map.json").is_file()


def test_submission_gate_accepts_animation_only_output(tmp_path: Path, monkeypatch: object) -> None:
    task_dir = _build_task(tmp_path, monkeypatch)
    submission = tmp_path / "submission"
    _valid_submission(task_dir, submission)

    inspection = inspect_model_submission(
        task_dir=task_dir,
        submission_dir=submission,
    )

    assert inspection.passed
    assert inspection.rationale_valid
    assert inspection.predicted_mover_ids == ["object_0001"]


def test_submission_gate_rejects_rewriting_known_scene(tmp_path: Path, monkeypatch: object) -> None:
    task_dir = _build_task(tmp_path, monkeypatch)
    submission = tmp_path / "submission"
    _valid_submission(task_dir, submission)
    prediction = load_scene(submission / "scene_program.json")
    assert isinstance(prediction, SceneProgramV02)
    write_scene(
        prediction.model_copy(update={"sample_id": "rewritten"}),
        submission / "scene_program.json",
    )

    inspection = inspect_model_submission(
        task_dir=task_dir,
        submission_dir=submission,
    )

    assert not inspection.passed
    assert "scene_base_fields_changed" in inspection.failures


def test_report_brackets_submission_with_baselines_and_oracles(
    tmp_path: Path, monkeypatch: object
) -> None:
    task_dir = _build_task(tmp_path, monkeypatch)
    submission = tmp_path / "submission"
    _valid_submission(task_dir, submission)
    scores = tmp_path / "scores"
    scores.mkdir()
    for name, payload in (
        ("subagent.json", _score(recall=1.0, error=0.2)),
        ("no_motion.json", _score(recall=0.0, error=1.0)),
        ("oracle.json", _score(recall=1.0, error=0.0)),
    ):
        (scores / name).write_text(json.dumps(payload) + "\n", encoding="utf-8")
    prediction_video = tmp_path / "prediction.mp4"
    reference_video = tmp_path / "reference.mp4"
    prediction_video.write_bytes(b"prediction")
    reference_video.write_bytes(b"reference")

    result = evaluate_model_submission(
        task_dir=task_dir,
        submission_dir=submission,
        output_dir=tmp_path / "report",
        sceneact_score_path=scores / "subagent.json",
        sceneact_baseline_path=scores / "no_motion.json",
        sceneact_oracle_path=scores / "oracle.json",
        prediction_video_path=prediction_video,
        reference_video_path=reference_video,
    )

    evaluation = json.loads(result.evaluation_json.read_text(encoding="utf-8"))
    assert evaluation["worldtime"]["subagent"]["normalized_mae"] == 0.0
    assert evaluation["worldtime"]["identity"]["normalized_mae"] > 0.0
    assert evaluation["sceneact"]["no_motion"]["movable_recall"] == 0.0
    assert evaluation["sceneact"]["subagent"]["movable_recall"] == 1.0
    assert result.timeline_svg is not None
    assert (result.output_dir / "prediction.mp4").is_file()
    assert (result.output_dir / "canonical_reference.mp4").is_file()
    report = result.report_markdown.read_text(encoding="utf-8")
    assert "No-motion" in report
    assert "Capability Diagnosis" in report
    html_report = result.report_html.read_text(encoding="utf-8")
    assert "prediction.mp4" in html_report
    assert "canonical_reference.mp4" in html_report
