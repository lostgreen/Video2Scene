"""Temporal-edit DSL and World-Time evaluator tests."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from smcb.worldtime.edits import (
    PRESET_ORDER,
    dense_world_times,
    edit_program,
    master_frame_indices,
    program_timeline,
)
from smcb.worldtime.evaluation import evaluate_timeline, identity_timeline
from smcb.worldtime.schema import EditSpan, TemporalEditProgram, Timeline


@pytest.mark.parametrize("preset", PRESET_ORDER)
def test_edit_presets_are_dense_deterministic_and_in_range(preset: str) -> None:
    first = edit_program(preset)
    second = edit_program(preset)

    assert first.model_dump(mode="json") == second.model_dump(mode="json")
    indices = master_frame_indices(first)
    assert len(indices) == 144
    assert min(indices) >= 0
    assert max(indices) < 144
    timeline = program_timeline(first)
    assert timeline.video_frame_count == 144
    assert len(dense_world_times(first)) == 144


def test_edit_presets_have_expected_time_behavior() -> None:
    normal = master_frame_indices(edit_program("normal"))
    reverse = master_frame_indices(edit_program("reverse"))
    freeze = master_frame_indices(edit_program("freeze"))
    replay = master_frame_indices(edit_program("replay"))

    assert normal == list(range(144))
    assert reverse == list(reversed(range(144)))
    assert freeze[48:72] == [47] * 24
    assert replay[72:96] == list(range(48, 72))
    assert replay[:72] == list(range(72))


@pytest.mark.parametrize("preset", PRESET_ORDER)
def test_oracle_timeline_scores_perfectly(preset: str) -> None:
    gt = program_timeline(edit_program(preset))

    score = evaluate_timeline(gt, gt)

    assert score.normalized_mae == pytest.approx(0.0)
    assert score.boundary_f1 == pytest.approx(1.0)
    assert score.direction_accuracy == pytest.approx(1.0)
    assert score.log_rate_mae == pytest.approx(0.0)


def test_identity_baseline_exposes_video_time_world_time_failures() -> None:
    reverse_gt = program_timeline(edit_program("reverse"))
    reverse_identity = identity_timeline(
        fps=24, frame_count=144, world_duration=reverse_gt.world_duration
    )
    reverse_score = evaluate_timeline(reverse_gt, reverse_identity)
    freeze_gt = program_timeline(edit_program("freeze"))
    freeze_score = evaluate_timeline(freeze_gt, reverse_identity)
    replay_gt = program_timeline(edit_program("replay"))
    replay_score = evaluate_timeline(replay_gt, reverse_identity)

    assert reverse_score.normalized_mae > 0.45
    assert reverse_score.direction_accuracy == pytest.approx(0.0)
    assert freeze_score.normalized_mae > 0.05
    assert freeze_score.boundary_f1 == pytest.approx(0.0)
    assert freeze_score.direction_accuracy < 1.0
    assert replay_score.normalized_mae > 0.02
    assert replay_score.boundary_f1 == pytest.approx(0.0)


def test_timeline_rejects_frame_coverage_gaps() -> None:
    payload = program_timeline(edit_program("freeze")).model_dump(mode="json")
    payload["segments"][1]["video_start_frame"] += 1

    with pytest.raises(ValidationError, match="cover video frames contiguously"):
        Timeline.model_validate(payload)


def test_edit_program_rejects_out_of_range_start_even_when_end_is_valid() -> None:
    with pytest.raises(ValidationError, match="leaves the master frame range"):
        TemporalEditProgram(
            preset="reverse",
            fps=24,
            master_frame_count=144,
            spans=[
                EditSpan(
                    kind="reverse",
                    master_start_frame=286,
                    frame_count=144,
                    step=-1,
                )
            ],
        )


def test_evaluator_rejects_a_different_canonical_world_duration() -> None:
    gt = program_timeline(edit_program("normal"))
    prediction = gt.model_copy(update={"world_duration": 7.0})

    with pytest.raises(ValueError, match="canonical world durations"):
        evaluate_timeline(gt, prediction)
