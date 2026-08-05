"""Blind model-task packaging and reporting for the first World-Time case study."""

from __future__ import annotations

import html
import json
import math
import os
import shutil
import subprocess
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field

from smcb.dsl.io import load_scene, write_scene
from smcb.dsl.models import ObjectSpec, SceneProgramV02
from smcb.worldtime.evaluation import (
    WorldTimeScore,
    dense_timeline,
    evaluate_timeline,
    identity_timeline,
)
from smcb.worldtime.schema import Timeline, WorldTimeModel


class EvaluationOutputContract(WorldTimeModel):
    timeline: Literal["timeline.json"] = "timeline.json"
    scene_program: Literal["scene_program.json"] = "scene_program.json"
    rationale: Literal["answer.md"] = "answer.md"


class ModelEvaluationTask(WorldTimeModel):
    schema_version: Literal["0.1"] = "0.1"
    task_id: str = Field(min_length=1, pattern=r"^[A-Za-z0-9_-]+$")
    track: Literal["core_single_observation_v0"] = "core_single_observation_v0"
    observation_video: Literal["input.mp4"] = "input.mp4"
    observation_contact_sheet: Literal["observation_contact_sheet.jpg"] = (
        "observation_contact_sheet.jpg"
    )
    initial_scene: Literal["initial_scene.json"] = "initial_scene.json"
    fps: int = Field(gt=0)
    video_frame_count: int = Field(gt=0)
    canonical_frame_count: int = Field(gt=0)
    world_duration: float = Field(gt=0)
    max_timeline_segments: int = Field(default=4, ge=1, le=16)
    object_count: int = Field(gt=0)
    output: EvaluationOutputContract = Field(default_factory=EvaluationOutputContract)
    assumptions: list[str] = Field(min_length=1)


class ModelEvaluationTaskResult(BaseModel):
    task_dir: Path
    public_dir: Path
    private_dir: Path
    prompt: Path
    observation_video: Path
    initial_scene: Path


class SubmissionInspection(BaseModel):
    task_id: str
    submission_dir: Path
    timeline_valid: bool
    scene_program_valid: bool
    rationale_valid: bool
    animation_track_count: int = Field(ge=0)
    predicted_mover_ids: list[str]
    failures: list[str]
    passed: bool


class ModelEvaluationResult(BaseModel):
    task_id: str
    output_dir: Path
    evaluation_json: Path
    report_markdown: Path
    report_html: Path
    timeline_svg: Path | None
    inspection: SubmissionInspection


def _link_or_copy(source: Path, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    try:
        os.link(source, destination)
    except OSError:
        shutil.copy2(source, destination)


def _json_object(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"expected a JSON object: {path}")
    return payload


def _make_contact_sheet(*, video: Path, output: Path, ffmpeg_bin: str) -> None:
    log_path = output.parent.parent / "private" / "contact_sheet.ffmpeg.log"
    command = [
        ffmpeg_bin,
        "-y",
        "-loglevel",
        "warning",
        "-i",
        str(video),
        "-vf",
        "fps=2,scale=240:-2,tile=4x3:padding=6:margin=6:color=0x20242b",
        "-frames:v",
        "1",
        "-q:v",
        "2",
        str(output),
    ]
    with log_path.open("w", encoding="utf-8") as log:
        completed = subprocess.run(command, stdout=log, stderr=subprocess.STDOUT, check=False)
    if completed.returncode != 0 or not output.is_file():
        raise RuntimeError(f"contact-sheet generation failed; see {log_path}")


def _anonymize_initial_scene(
    scene: SceneProgramV02, *, task_id: str
) -> tuple[SceneProgramV02, dict[str, str]]:
    object_id_map = {
        item.id: f"object_{index:04d}" for index, item in enumerate(scene.objects, start=1)
    }
    objects = [
        ObjectSpec(
            id=object_id_map[item.id],
            asset_id=item.asset_id,
            transform=item.transform,
            parent_id=(object_id_map[item.parent_id] if item.parent_id is not None else None),
            target=item.target,
        )
        for item in scene.objects
    ]
    initial = scene.model_copy(
        update={
            "sample_id": task_id,
            "objects": objects,
            "animations": [],
        }
    )
    return SceneProgramV02.model_validate(initial.model_dump(mode="json")), object_id_map


def _task_prompt(task: ModelEvaluationTask) -> str:
    assumptions = "\n".join(f"- {item}" for item in task.assumptions)
    return f"""# Blind World-Time Core Task

You are the model under evaluation. Read files only from this public task directory and write
files only to your assigned submission directory. Do not inspect any sibling `private` directory,
repository source, prior demo output, or hidden ground truth.

## Input

- `input.mp4`: one temporally edited observation, {task.video_frame_count} frames at {task.fps} fps.
- `observation_contact_sheet.jpg`: uniformly sampled visual aid derived from the same video.
- `initial_scene.json`: anonymous object IDs, known assets, initial transforms, fixed camera,
  lighting, coordinates, and canonical render range. Its `animations` list is intentionally empty.
- `timeline.schema.json` and `scene_program.schema.json`: strict output schemas.

## Assumptions

{assumptions}

## Required output

1. `timeline.json`: a contiguous piecewise-linear mapping from observation frame to canonical
   world time in seconds, using no more than {task.max_timeline_segments} segments.
2. `scene_program.json`: copy every non-animation field from `initial_scene.json` exactly and add
   your best canonical animation tracks. Use `scoring_role: \"mover\"` only for objects you infer
   to move. Keyframe values are world coordinates and frames are 1-based.
3. `answer.md`: briefly explain detected temporal structure, moving objects, uncertainty, and the
   evidence used. The rationale is displayed but is not part of the automatic score.

Do not emit an edit label instead of the mapping. The structured files are the answer.
"""


def build_model_evaluation_task(
    *,
    canonical_sample_dir: Path,
    observation_dir: Path,
    output_dir: Path,
    task_id: str,
    ffmpeg_bin: str,
) -> ModelEvaluationTaskResult:
    """Create one public blind task and a physically separate private GT directory."""
    canonical_sample_dir = canonical_sample_dir.expanduser().resolve()
    observation_dir = observation_dir.expanduser().resolve()
    output_dir = output_dir.expanduser().resolve()
    if output_dir.exists():
        raise FileExistsError(f"evaluation task already exists: {output_dir}")
    scene = load_scene(canonical_sample_dir / "scene.json")
    if not isinstance(scene, SceneProgramV02):
        raise ValueError("model evaluation requires a Scene Program v0.2 canonical sample")
    gt_timeline = Timeline.model_validate_json(
        (observation_dir / "timeline.json").read_text(encoding="utf-8")
    )
    canonical_frame_count = scene.render.frame_end - scene.render.frame_start + 1
    if (
        gt_timeline.fps != scene.render.fps
        or gt_timeline.video_frame_count != canonical_frame_count
    ):
        raise ValueError("canonical scene and observation sampling do not match")

    public_dir = output_dir / "public"
    private_dir = output_dir / "private"
    public_dir.mkdir(parents=True)
    private_dir.mkdir()
    initial_scene, object_id_map = _anonymize_initial_scene(scene, task_id=task_id)
    write_scene(initial_scene, public_dir / "initial_scene.json")
    _link_or_copy(observation_dir / "input.mp4", public_dir / "input.mp4")
    _make_contact_sheet(
        video=public_dir / "input.mp4",
        output=public_dir / "observation_contact_sheet.jpg",
        ffmpeg_bin=ffmpeg_bin,
    )
    (public_dir / "timeline.schema.json").write_text(
        json.dumps(Timeline.model_json_schema(), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    (public_dir / "scene_program.schema.json").write_text(
        json.dumps(SceneProgramV02.model_json_schema(), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    task = ModelEvaluationTask(
        task_id=task_id,
        fps=scene.render.fps,
        video_frame_count=gt_timeline.video_frame_count,
        canonical_frame_count=canonical_frame_count,
        world_duration=gt_timeline.world_duration,
        object_count=len(initial_scene.objects),
        assumptions=[
            "The observation starts at canonical world time 0 seconds.",
            "The canonical world has the declared fixed duration and camera.",
            (
                "Video editing is piecewise linear and may include forward, reverse, "
                "freeze, or replay."
            ),
            (
                "The observation preserves frame count, while temporal edits may omit parts "
                "of the canonical world."
            ),
        ],
    )
    (public_dir / "task.json").write_text(task.model_dump_json(indent=2) + "\n", encoding="utf-8")
    (public_dir / "PROMPT.md").write_text(_task_prompt(task), encoding="utf-8")

    (private_dir / "timeline.json").write_text(
        gt_timeline.model_dump_json(indent=2) + "\n", encoding="utf-8"
    )
    shutil.copy2(canonical_sample_dir / "scene.json", private_dir / "canonical_scene.json")
    if (observation_dir / "edit_program.json").is_file():
        shutil.copy2(observation_dir / "edit_program.json", private_dir / "edit_program.json")
    (private_dir / "object_id_map.json").write_text(
        json.dumps(object_id_map, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    (private_dir / "source_manifest.json").write_text(
        json.dumps(
            {
                "canonical_sample_dir": str(canonical_sample_dir),
                "observation_dir": str(observation_dir),
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    return ModelEvaluationTaskResult(
        task_dir=output_dir,
        public_dir=public_dir,
        private_dir=private_dir,
        prompt=public_dir / "PROMPT.md",
        observation_video=public_dir / "input.mp4",
        initial_scene=public_dir / "initial_scene.json",
    )


def inspect_model_submission(*, task_dir: Path, submission_dir: Path) -> SubmissionInspection:
    """Validate structured output and prove that the known scene was not rewritten."""
    task_dir = task_dir.expanduser().resolve()
    submission_dir = submission_dir.expanduser().resolve()
    task = ModelEvaluationTask.model_validate_json(
        (task_dir / "public" / "task.json").read_text(encoding="utf-8")
    )
    failures: list[str] = []
    timeline_valid = False
    scene_valid = False
    rationale_valid = False
    animation_count = 0
    predicted_movers: list[str] = []

    timeline_path = submission_dir / task.output.timeline
    try:
        timeline = Timeline.model_validate_json(timeline_path.read_text(encoding="utf-8"))
        if (
            timeline.fps != task.fps
            or timeline.video_frame_count != task.video_frame_count
            or not math.isclose(
                timeline.world_duration,
                task.world_duration,
                abs_tol=1e-8,
            )
        ):
            failures.append("timeline_sampling_mismatch")
        elif len(timeline.segments) > task.max_timeline_segments:
            failures.append(f"timeline_segment_count:{len(timeline.segments)}")
        else:
            timeline_valid = True
    except (OSError, ValueError) as error:
        failures.append(f"invalid:timeline.json:{type(error).__name__}")

    scene_path = submission_dir / task.output.scene_program
    try:
        prediction = load_scene(scene_path)
        initial = load_scene(task_dir / "public" / task.initial_scene)
        if not isinstance(prediction, SceneProgramV02) or not isinstance(initial, SceneProgramV02):
            failures.append("invalid:scene_program_version")
        else:
            animation_count = len(prediction.animations)
            predicted_movers = sorted(
                track.target_id for track in prediction.animations if track.scoring_role == "mover"
            )
            initial_payload = initial.model_dump(mode="json")
            prediction_payload = prediction.model_dump(mode="json")
            initial_payload.pop("animations")
            prediction_payload.pop("animations")
            if prediction_payload != initial_payload:
                failures.append("scene_base_fields_changed")
            if not prediction.animations:
                failures.append("missing:animation_tracks")
            if any(track.target_id == prediction.camera.id for track in prediction.animations):
                failures.append("invalid:camera_animation")
            if any(track.scoring_role != "mover" for track in prediction.animations):
                failures.append("invalid:non_mover_track")
            if (
                prediction_payload == initial_payload
                and prediction.animations
                and not any(
                    track.target_id == prediction.camera.id for track in prediction.animations
                )
                and all(track.scoring_role == "mover" for track in prediction.animations)
            ):
                scene_valid = True
    except (OSError, ValueError) as error:
        failures.append(f"invalid:scene_program.json:{type(error).__name__}")

    rationale_path = submission_dir / task.output.rationale
    try:
        if rationale_path.read_text(encoding="utf-8").strip():
            rationale_valid = True
        else:
            failures.append("empty:answer.md")
    except OSError as error:
        failures.append(f"invalid:answer.md:{type(error).__name__}")

    return SubmissionInspection(
        task_id=task.task_id,
        submission_dir=submission_dir,
        timeline_valid=timeline_valid,
        scene_program_valid=scene_valid,
        rationale_valid=rationale_valid,
        animation_track_count=animation_count,
        predicted_mover_ids=predicted_movers,
        failures=failures,
        passed=timeline_valid and scene_valid and rationale_valid and not failures,
    )


def _load_optional_score(path: Path | None) -> dict[str, Any] | None:
    if path is None:
        return None
    return _json_object(path.expanduser().resolve())


def _boundary_metrics(
    *,
    declared: list[int],
    expected: list[int],
    tolerance: int = 2,
) -> dict[str, float]:
    unmatched = set(expected)
    matches = 0
    for boundary in declared:
        candidates = [item for item in unmatched if abs(item - boundary) <= tolerance]
        if candidates:
            matched = min(candidates, key=lambda item: abs(item - boundary))
            unmatched.remove(matched)
            matches += 1
    precision = matches / len(declared) if declared else (1.0 if not expected else 0.0)
    recall = matches / len(expected) if expected else (1.0 if not declared else 0.0)
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    return {"precision": precision, "recall": recall, "f1": f1}


def _invalid_timeline_audit(*, path: Path, gt: Timeline) -> dict[str, Any]:
    """Extract non-scoring evidence from a parseable but contract-invalid timeline."""
    try:
        payload = _json_object(path)
    except (OSError, ValueError, json.JSONDecodeError) as error:
        return {"available": False, "reason": type(error).__name__}
    raw_segments = payload.get("segments")
    if not isinstance(raw_segments, list) or not raw_segments:
        return {"available": False, "reason": "segments_not_a_nonempty_list"}
    segments: list[dict[str, Any]] = []
    for item in raw_segments:
        if not isinstance(item, dict):
            return {"available": False, "reason": "segment_not_an_object"}
        start = item.get("video_start_frame")
        end = item.get("video_end_frame")
        if not isinstance(start, int) or isinstance(start, bool):
            return {"available": False, "reason": "segment_start_not_an_integer"}
        if not isinstance(end, int) or isinstance(end, bool):
            return {"available": False, "reason": "segment_end_not_an_integer"}
        segments.append(item)

    declared_starts = [int(item["video_start_frame"]) for item in segments]
    declared_ends = [int(item["video_end_frame"]) for item in segments]
    declared_world_starts = [item.get("world_start_time") for item in segments]
    declared_world_ends = [item.get("world_end_time") for item in segments]
    expected_starts = [item.video_start_frame for item in gt.segments]
    expected_ends = [item.video_end_frame for item in gt.segments]
    expected_world_starts = [item.world_start_time for item in gt.segments]
    expected_world_ends = [item.world_end_time for item in gt.segments]
    coverage_issues: list[dict[str, int]] = []
    expected_start = 0
    for index, (start, end) in enumerate(zip(declared_starts, declared_ends, strict=True)):
        if start != expected_start:
            coverage_issues.append(
                {
                    "segment_index": index,
                    "expected_start": expected_start,
                    "declared_start": start,
                }
            )
        expected_start = end + 1
    if expected_start != gt.video_frame_count:
        coverage_issues.append(
            {
                "segment_index": len(segments),
                "expected_start": gt.video_frame_count,
                "declared_start": expected_start,
            }
        )

    metadata = {
        "fps_matches": payload.get("fps") == gt.fps,
        "video_frame_count_matches": (payload.get("video_frame_count") == gt.video_frame_count),
        "world_duration_matches": (
            isinstance(payload.get("world_duration"), int | float)
            and not isinstance(payload.get("world_duration"), bool)
            and math.isclose(
                float(payload["world_duration"]),
                gt.world_duration,
                abs_tol=1e-8,
            )
        ),
        "declared_world_duration": payload.get("world_duration"),
        "expected_world_duration": gt.world_duration,
    }
    return {
        "available": True,
        "strict_score_eligible": False,
        "declared_segment_count": len(segments),
        "declared_start_boundaries": declared_starts,
        "declared_end_boundaries": declared_ends,
        "declared_world_start_times": declared_world_starts,
        "declared_world_end_times": declared_world_ends,
        "expected_start_boundaries": expected_starts,
        "expected_end_boundaries": expected_ends,
        "expected_world_start_times": expected_world_starts,
        "expected_world_end_times": expected_world_ends,
        "internal_boundary_metrics": _boundary_metrics(
            declared=declared_starts[1:],
            expected=expected_starts[1:],
        ),
        "inclusive_coverage_issues": coverage_issues,
        "metadata": metadata,
        "note": (
            "Diagnostic only: raw declarations are compared after submission, but the invalid "
            "timeline is neither repaired nor assigned a World-Time score."
        ),
    }


def _timeline_svg(*, gt: Timeline, prediction: Timeline, identity: Timeline) -> str:
    width, height = 920, 500
    left, top, plot_width, plot_height = 72, 36, 810, 390

    def points(timeline: Timeline) -> str:
        values = dense_timeline(timeline)
        coords = []
        for index, value in enumerate(values):
            x = left + plot_width * index / max(1, len(values) - 1)
            y = top + plot_height * (1.0 - value / gt.world_duration)
            coords.append(f"{x:.2f},{y:.2f}")
        return " ".join(coords)

    boundaries: list[str] = []
    for segment in gt.segments[1:]:
        boundary_x = left + (plot_width * segment.video_start_frame / (gt.video_frame_count - 1))
        boundaries.append(
            f'<line x1="{boundary_x:.2f}" y1="{top}" x2="{boundary_x:.2f}" '
            f'y2="{top + plot_height}" stroke="#a0a7b0" stroke-dasharray="5 5" />'
        )
    elements = [
        (
            f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" '
            f'height="{height}" viewBox="0 0 {width} {height}">'
        ),
        '<rect width="100%" height="100%" fill="#ffffff" />',
        (
            f'<line x1="{left}" y1="{top + plot_height}" '
            f'x2="{left + plot_width}" y2="{top + plot_height}" stroke="#22262b" />'
        ),
        (f'<line x1="{left}" y1="{top}" x2="{left}" y2="{top + plot_height}" stroke="#22262b" />'),
        *boundaries,
        (f'<polyline points="{points(identity)}" fill="none" stroke="#9aa1a8" stroke-width="2" />'),
        (f'<polyline points="{points(gt)}" fill="none" stroke="#16845b" stroke-width="4" />'),
        (
            f'<polyline points="{points(prediction)}" fill="none" '
            'stroke="#d04438" stroke-width="2.5" />'
        ),
        (
            f'<text x="{left + plot_width / 2}" y="{height - 18}" '
            'text-anchor="middle" font-family="Arial" font-size="15">'
            "Observation frame</text>"
        ),
        (
            f'<text x="18" y="{top + plot_height / 2}" '
            f'transform="rotate(-90 18 {top + plot_height / 2})" '
            'text-anchor="middle" font-family="Arial" font-size="15">'
            "Canonical world time (s)</text>"
        ),
        (f'<text x="{left}" y="20" font-family="Arial" font-size="14" fill="#16845b">GT</text>'),
        (
            f'<text x="{left + 48}" y="20" font-family="Arial" font-size="14" '
            'fill="#d04438">Subagent</text>'
        ),
        (
            f'<text x="{left + 142}" y="20" font-family="Arial" font-size="14" '
            'fill="#737b83">Identity</text>'
        ),
        "</svg>",
    ]
    return "\n".join(elements) + "\n"


def _metric(value: Any) -> str:
    if value is None:
        return "n/a"
    if isinstance(value, float):
        return f"{value:.4f}"
    return str(value)


def _scene_table(
    prediction: dict[str, Any] | None,
    baseline: dict[str, Any] | None,
    oracle: dict[str, Any] | None,
) -> tuple[str, str]:
    keys = (
        "mean_vehicle_err",
        "worst_vehicle_err",
        "movable_recall",
        "mover_count_err",
        "direction_error_rate",
        "path_shape_err",
        "scale_error",
        "layout_err",
    )
    markdown = [
        "| Metric | Subagent | No-motion | Oracle |",
        "| --- | ---: | ---: | ---: |",
    ]
    html_rows = []
    for key in keys:
        predicted_value = prediction.get(key) if prediction else "not scored"
        baseline_value = baseline.get(key) if baseline else "not scored"
        oracle_value = oracle.get(key) if oracle else "not provided"
        markdown.append(
            f"| `{key}` | {_metric(predicted_value)} | {_metric(baseline_value)} | "
            f"{_metric(oracle_value)} |"
        )
        html_rows.append(
            f"<tr><td>{html.escape(key)}</td>"
            f"<td>{html.escape(_metric(predicted_value))}</td>"
            f"<td>{html.escape(_metric(baseline_value))}</td>"
            f"<td>{html.escape(_metric(oracle_value))}</td></tr>"
        )
    return "\n".join(markdown), "".join(html_rows)


def _capability_table(
    *,
    inspection: SubmissionInspection,
    model_timeline: dict[str, Any] | None,
    identity_timeline_score: dict[str, Any],
    oracle_timeline_score: dict[str, Any],
    model_scene: dict[str, Any] | None,
    baseline_scene: dict[str, Any] | None,
    oracle_scene: dict[str, Any] | None,
) -> tuple[str, str]:
    rows = [
        (
            "Output contract",
            "validator pass",
            inspection.passed,
            "n/a",
            True,
            "required",
        ),
        (
            "World-time alignment",
            "normalized_mae",
            model_timeline.get("normalized_mae") if model_timeline else "invalid",
            identity_timeline_score["normalized_mae"],
            oracle_timeline_score["normalized_mae"],
            "lower",
        ),
        (
            "Edit segmentation",
            "boundary_f1",
            model_timeline.get("boundary_f1") if model_timeline else "invalid",
            identity_timeline_score["boundary_f1"],
            oracle_timeline_score["boundary_f1"],
            "higher",
        ),
        (
            "Playback direction",
            "direction_accuracy",
            model_timeline.get("direction_accuracy") if model_timeline else "invalid",
            identity_timeline_score["direction_accuracy"],
            oracle_timeline_score["direction_accuracy"],
            "higher",
        ),
        (
            "Playback rate",
            "log_rate_mae",
            model_timeline.get("log_rate_mae") if model_timeline else "invalid",
            identity_timeline_score["log_rate_mae"],
            oracle_timeline_score["log_rate_mae"],
            "lower",
        ),
        (
            "Mover discovery",
            "movable_recall",
            model_scene.get("movable_recall") if model_scene else "not scored",
            baseline_scene.get("movable_recall") if baseline_scene else "not scored",
            oracle_scene.get("movable_recall") if oracle_scene else "not provided",
            "higher",
        ),
        (
            "Mover count",
            "mover_count_err",
            model_scene.get("mover_count_err") if model_scene else "not scored",
            baseline_scene.get("mover_count_err") if baseline_scene else "not scored",
            oracle_scene.get("mover_count_err") if oracle_scene else "not provided",
            "lower",
        ),
        (
            "3D trajectory",
            "mean_vehicle_err",
            model_scene.get("mean_vehicle_err") if model_scene else "not scored",
            baseline_scene.get("mean_vehicle_err") if baseline_scene else "not scored",
            oracle_scene.get("mean_vehicle_err") if oracle_scene else "not provided",
            "lower",
        ),
        (
            "Path shape",
            "path_shape_err",
            model_scene.get("path_shape_err") if model_scene else "not scored",
            baseline_scene.get("path_shape_err") if baseline_scene else "not scored",
            oracle_scene.get("path_shape_err") if oracle_scene else "not provided",
            "lower",
        ),
    ]
    markdown = [
        "| Capability | Signal | Subagent | Baseline | Oracle | Better |",
        "| --- | --- | ---: | ---: | ---: | --- |",
    ]
    html_rows = []
    for capability, signal, model, baseline, oracle, direction in rows:
        values = (_metric(model), _metric(baseline), _metric(oracle))
        markdown.append(
            f"| {capability} | `{signal}` | {values[0]} | {values[1]} | {values[2]} | {direction} |"
        )
        html_rows.append(
            f"<tr><td>{html.escape(capability)}</td><td>{html.escape(signal)}</td>"
            f"<td>{html.escape(values[0])}</td><td>{html.escape(values[1])}</td>"
            f"<td>{html.escape(values[2])}</td><td>{html.escape(direction)}</td></tr>"
        )
    return "\n".join(markdown), "".join(html_rows)


def evaluate_model_submission(
    *,
    task_dir: Path,
    submission_dir: Path,
    output_dir: Path,
    sceneact_score_path: Path | None = None,
    sceneact_baseline_path: Path | None = None,
    sceneact_oracle_path: Path | None = None,
    prediction_video_path: Path | None = None,
    reference_video_path: Path | None = None,
) -> ModelEvaluationResult:
    """Score one blind submission and create a self-contained visual case-study report."""
    task_dir = task_dir.expanduser().resolve()
    submission_dir = submission_dir.expanduser().resolve()
    output_dir = output_dir.expanduser().resolve()
    if output_dir.exists():
        raise FileExistsError(f"evaluation report already exists: {output_dir}")
    output_dir.mkdir(parents=True)
    inspection = inspect_model_submission(task_dir=task_dir, submission_dir=submission_dir)
    task = ModelEvaluationTask.model_validate_json(
        (task_dir / "public" / "task.json").read_text(encoding="utf-8")
    )
    gt = Timeline.model_validate_json(
        (task_dir / "private" / "timeline.json").read_text(encoding="utf-8")
    )
    identity = identity_timeline(
        fps=gt.fps,
        frame_count=gt.video_frame_count,
        world_duration=gt.world_duration,
    )
    prediction: Timeline | None = None
    model_score: WorldTimeScore | None = None
    invalid_timeline_audit: dict[str, Any] | None = None
    if inspection.timeline_valid:
        prediction = Timeline.model_validate_json(
            (submission_dir / task.output.timeline).read_text(encoding="utf-8")
        )
        model_score = evaluate_timeline(gt, prediction)
    else:
        invalid_timeline_audit = _invalid_timeline_audit(
            path=submission_dir / task.output.timeline,
            gt=gt,
        )
    identity_score = evaluate_timeline(gt, identity)
    oracle_score = evaluate_timeline(gt, gt)
    sceneact_score = _load_optional_score(sceneact_score_path)
    sceneact_baseline = _load_optional_score(sceneact_baseline_path)
    sceneact_oracle = _load_optional_score(sceneact_oracle_path)
    edit_program = (
        _json_object(task_dir / "private" / "edit_program.json")
        if (task_dir / "private" / "edit_program.json").is_file()
        else {}
    )
    preset = str(edit_program.get("preset", "hidden-edit"))

    timeline_svg_path: Path | None = None
    if prediction is not None:
        timeline_svg_path = output_dir / "timeline_comparison.svg"
        timeline_svg_path.write_text(
            _timeline_svg(gt=gt, prediction=prediction, identity=identity), encoding="utf-8"
        )
    contact_sheet = output_dir / "observation_contact_sheet.jpg"
    shutil.copy2(task_dir / "public" / task.observation_contact_sheet, contact_sheet)
    prediction_video: Path | None = None
    if prediction_video_path is not None:
        prediction_video = output_dir / "prediction.mp4"
        _link_or_copy(prediction_video_path.expanduser().resolve(), prediction_video)
    reference_video: Path | None = None
    if reference_video_path is not None:
        reference_video = output_dir / "canonical_reference.mp4"
        _link_or_copy(reference_video_path.expanduser().resolve(), reference_video)

    model_payload = model_score.model_dump(mode="json") if model_score else None
    identity_payload = identity_score.model_dump(mode="json")
    oracle_payload = oracle_score.model_dump(mode="json")
    mapping_delta = (
        identity_score.normalized_mae - model_score.normalized_mae if model_score else None
    )
    if mapping_delta is not None and mapping_delta > 0:
        temporal_diagnosis = (
            "The structured prediction beats the identity baseline on source-time mapping."
        )
    elif invalid_timeline_audit and invalid_timeline_audit.get("available") is True:
        boundary_metrics = invalid_timeline_audit["internal_boundary_metrics"]
        temporal_diagnosis = (
            "The timeline is ineligible for primary scoring. Its declared internal boundaries "
            f"have diagnostic F1={_metric(boundary_metrics['f1'])}, while inclusive frame "
            "coverage or sampling metadata violate the output contract."
        )
    else:
        temporal_diagnosis = (
            "The structured prediction does not beat the identity mapping baseline."
        )
    scene_diagnosis = "Scene reconstruction was not scored."
    if sceneact_score is not None:
        recall = sceneact_score.get("movable_recall")
        mean_error = sceneact_score.get("mean_vehicle_err")
        if sceneact_baseline is not None:
            baseline_recall = sceneact_baseline.get("movable_recall")
            baseline_error = sceneact_baseline.get("mean_vehicle_err")
            scene_diagnosis = (
                f"The predicted GLB reached movable_recall={_metric(recall)} versus "
                f"{_metric(baseline_recall)} for no-motion, and mean_vehicle_err="
                f"{_metric(mean_error)} versus {_metric(baseline_error)}."
            )
        else:
            scene_diagnosis = (
                f"The predicted GLB reached movable_recall={_metric(recall)} and "
                f"mean_vehicle_err={_metric(mean_error)}."
            )

    evaluation = {
        "schema_version": "0.1",
        "task_id": task.task_id,
        "case_study_only": True,
        "hidden_edit_preset": preset,
        "inspection": inspection.model_dump(mode="json"),
        "worldtime": {
            "subagent": model_payload,
            "identity": identity_payload,
            "oracle": oracle_payload,
            "normalized_mae_improvement_over_identity": mapping_delta,
            "invalid_submission_audit": invalid_timeline_audit,
        },
        "sceneact": {
            "subagent": sceneact_score,
            "no_motion": sceneact_baseline,
            "oracle": sceneact_oracle,
        },
        "diagnosis": {
            "temporal": temporal_diagnosis,
            "scene": scene_diagnosis,
            "limitation": "One canonical scene measures task execution, not generalization.",
        },
        "artifacts": {
            "prediction_video": prediction_video.name if prediction_video else None,
            "reference_video": reference_video.name if reference_video else None,
        },
    }
    evaluation_json = output_dir / "evaluation.json"
    evaluation_json.write_text(
        json.dumps(evaluation, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )

    scene_markdown, scene_html_rows = _scene_table(
        sceneact_score,
        sceneact_baseline,
        sceneact_oracle,
    )
    capability_markdown, capability_html_rows = _capability_table(
        inspection=inspection,
        model_timeline=model_payload,
        identity_timeline_score=identity_payload,
        oracle_timeline_score=oracle_payload,
        model_scene=sceneact_score,
        baseline_scene=sceneact_baseline,
        oracle_scene=sceneact_oracle,
    )
    timeline_markdown = (
        "| Metric | Subagent | Identity | Oracle |\n"
        "| --- | ---: | ---: | ---: |\n"
        + "\n".join(
            f"| `{key}` | {_metric(model_payload.get(key) if model_payload else 'invalid')} | "
            f"{_metric(identity_payload[key])} | {_metric(oracle_payload[key])} |"
            for key in (
                "normalized_mae",
                "boundary_f1",
                "direction_accuracy",
                "log_rate_mae",
            )
        )
    )
    invalid_audit_markdown = ""
    invalid_audit_html = ""
    if invalid_timeline_audit and invalid_timeline_audit.get("available") is True:
        audit_boundaries = invalid_timeline_audit["internal_boundary_metrics"]
        declared_starts = invalid_timeline_audit["declared_start_boundaries"]
        expected_starts = invalid_timeline_audit["expected_start_boundaries"]
        declared_world_starts = invalid_timeline_audit["declared_world_start_times"]
        expected_world_starts = invalid_timeline_audit["expected_world_start_times"]
        declared_world_ends = invalid_timeline_audit["declared_world_end_times"]
        expected_world_ends = invalid_timeline_audit["expected_world_end_times"]
        coverage_issues = invalid_timeline_audit["inclusive_coverage_issues"]
        audit_metadata = invalid_timeline_audit["metadata"]
        declared_duration = _metric(audit_metadata["declared_world_duration"])
        expected_duration = _metric(audit_metadata["expected_world_duration"])
        invalid_audit_markdown = f"""### Non-scoring Invalid Timeline Audit

| Evidence | Submitted | Expected / Result |
| --- | --- | --- |
| Start boundaries | `{declared_starts}` | `{expected_starts}` |
| World start times | `{declared_world_starts}` | `{expected_world_starts}` |
| World end times | `{declared_world_ends}` | `{expected_world_ends}` |
| Boundary F1 | `{_metric(audit_boundaries["f1"])}` | diagnostic only |
| Inclusive coverage issues | `{coverage_issues}` | `[]` |
| World duration | `{declared_duration}` | `{expected_duration}` |

This audit does not repair the raw submission or assign a World-Time score.
"""
        invalid_audit_html = (
            '<section class="audit"><h3>Non-scoring Invalid Timeline Audit</h3>'
            f"<p><strong>Submitted starts:</strong> {html.escape(str(declared_starts))}<br>"
            f"<strong>Expected starts:</strong> {html.escape(str(expected_starts))}<br>"
            f"<strong>Submitted world starts:</strong> "
            f"{html.escape(str(declared_world_starts))}<br>"
            f"<strong>Expected world starts:</strong> "
            f"{html.escape(str(expected_world_starts))}<br>"
            f"<strong>Submitted world ends:</strong> "
            f"{html.escape(str(declared_world_ends))}<br>"
            f"<strong>Expected world ends:</strong> "
            f"{html.escape(str(expected_world_ends))}<br>"
            f"<strong>Boundary F1:</strong> {_metric(audit_boundaries['f1'])}<br>"
            f"<strong>Coverage issues:</strong> {html.escape(str(coverage_issues))}<br>"
            "The raw timeline remains invalid and receives no World-Time score.</p></section>"
        )
    rationale_path = submission_dir / task.output.rationale
    rationale = (
        rationale_path.read_text(encoding="utf-8")
        if rationale_path.is_file()
        else "No rationale was submitted."
    )
    svg_markdown = "![Timeline comparison](timeline_comparison.svg)" if timeline_svg_path else ""
    video_markdown = ""
    if prediction_video is not None and reference_video is not None:
        video_markdown = (
            "- [Subagent canonical render](prediction.mp4)\n"
            "- [Canonical reference render](canonical_reference.mp4)"
        )
    report_markdown = output_dir / "report.md"
    report_markdown.write_text(
        f"""# Video2Scene Blind Evaluation Demo

**Task:** `{task.task_id}`

**Hidden edit revealed after submission:** `{preset}`

**Submission valid:** `{inspection.passed}`

This is a complete single-case evaluation-system demonstration. It is not evidence of
cross-scene generalization.

## Observation

![Observation contact sheet](observation_contact_sheet.jpg)

## Video Time -> World Time

{timeline_markdown}

{svg_markdown}

{invalid_audit_markdown}

## Canonical 3D Motion

{scene_markdown}

{video_markdown}

## Capability Diagnosis

{capability_markdown}

- {temporal_diagnosis}
- {scene_diagnosis}
- Format failures: `{inspection.failures}`
- Generalization remains unmeasured because this report contains one canonical scene.

## Model Rationale

{rationale}
""",
        encoding="utf-8",
    )

    timeline_html_rows = "".join(
        f"<tr><td>{html.escape(key)}</td>"
        f"<td>{html.escape(_metric(model_payload.get(key) if model_payload else 'invalid'))}</td>"
        f"<td>{html.escape(_metric(identity_payload[key]))}</td>"
        f"<td>{html.escape(_metric(oracle_payload[key]))}</td></tr>"
        for key in (
            "normalized_mae",
            "boundary_f1",
            "direction_accuracy",
            "log_rate_mae",
        )
    )
    svg_html = (
        '<img src="timeline_comparison.svg" alt="Timeline comparison">' if timeline_svg_path else ""
    )
    task_label = html.escape(task.task_id)
    preset_label = html.escape(preset)
    temporal_label = html.escape(temporal_diagnosis)
    scene_label = html.escape(scene_diagnosis)
    media_html = ""
    if prediction_video is not None or reference_video is not None:
        media_blocks = []
        if prediction_video is not None:
            media_blocks.append(
                "<section><h3>Subagent canonical render</h3>"
                '<video controls preload="metadata" src="prediction.mp4"></video></section>'
            )
        if reference_video is not None:
            media_blocks.append(
                "<section><h3>Canonical reference</h3>"
                '<video controls preload="metadata" '
                'src="canonical_reference.mp4"></video></section>'
            )
        media_html = '<div class="media-grid">' + "".join(media_blocks) + "</div>"
    report_html = output_dir / "report.html"
    report_html.write_text(
        f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Video2Scene Blind Evaluation Demo</title>
<style>
body{{margin:0;background:#f4f5f3;color:#202326;font:15px/1.55 Arial,sans-serif}}
header{{background:#20262b;color:#fff;padding:28px max(24px,calc((100% - 1040px)/2))}}
main{{max-width:1040px;margin:auto;padding:28px 24px 48px}}
h1{{font-size:28px;margin:0 0 8px}} h2{{font-size:20px;margin:32px 0 12px}}
.meta{{color:#cdd4d9}} img{{display:block;max-width:100%;height:auto}}
video{{display:block;width:100%;background:#111}}
.media-grid{{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:16px}}
.media-grid h3{{font-size:15px;margin:8px 0}}
table{{width:100%;border-collapse:collapse;background:#fff}}
th,td{{padding:9px 12px;border:1px solid #d8dcde;text-align:left}}
th{{background:#e9eceb}} code{{background:#e6e9e8;padding:2px 4px}}
.warning{{border-left:4px solid #c48a12;padding:8px 14px;background:#fff8e8}}
.audit{{border-left:4px solid #b64238;padding:8px 14px;background:#fff}}
pre{{white-space:pre-wrap;background:#fff;padding:16px;border:1px solid #d8dcde}}
</style>
</head>
<body>
<header>
<h1>Video2Scene Blind Evaluation Demo</h1>
<div class="meta">
Task {task_label} | hidden edit: {preset_label} | valid: {inspection.passed}
</div>
</header>
<main>
<p class="warning">
Single canonical-scene case study. This demonstrates the complete evaluation loop,
not model generalization.
</p>
<h2>Observation</h2>
<img src="observation_contact_sheet.jpg" alt="Observation frames">
<h2>Video Time to World Time</h2>
<table>
<thead><tr>
<th>Metric</th><th>Subagent</th><th>Identity</th><th>Oracle</th>
</tr></thead>
<tbody>{timeline_html_rows}</tbody>
</table>
{svg_html}
{invalid_audit_html}
<h2>Canonical 3D Motion</h2>
<table>
<thead><tr>
<th>Metric</th><th>Subagent</th><th>No-motion</th><th>Oracle</th>
</tr></thead>
<tbody>{scene_html_rows}</tbody>
</table>
{media_html}
<h2>Capability Diagnosis</h2>
<table>
<thead><tr>
<th>Capability</th><th>Signal</th><th>Subagent</th><th>Baseline</th>
<th>Oracle</th><th>Better</th>
</tr></thead>
<tbody>{capability_html_rows}</tbody>
</table>
<p>{temporal_label}</p>
<p>{scene_label}</p>
<h2>Model Rationale</h2><pre>{html.escape(rationale)}</pre>
</main>
</body>
</html>\n""",
        encoding="utf-8",
    )
    return ModelEvaluationResult(
        task_id=task.task_id,
        output_dir=output_dir,
        evaluation_json=evaluation_json,
        report_markdown=report_markdown,
        report_html=report_html,
        timeline_svg=timeline_svg_path,
        inspection=inspection,
    )
