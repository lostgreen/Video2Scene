"""Metrics for piecewise-linear Video Time -> World Time predictions."""

from __future__ import annotations

import math
from statistics import median

from pydantic import BaseModel, Field

from smcb.worldtime.schema import Timeline, TimelineSegment


class WorldTimeScore(BaseModel):
    frame_count: int = Field(gt=0)
    mae_seconds: float = Field(ge=0)
    normalized_mae: float = Field(ge=0)
    median_error_seconds: float = Field(ge=0)
    p90_error_seconds: float = Field(ge=0)
    boundary_precision: float = Field(ge=0, le=1)
    boundary_recall: float = Field(ge=0, le=1)
    boundary_f1: float = Field(ge=0, le=1)
    direction_accuracy: float = Field(ge=0, le=1)
    log_rate_mae: float = Field(ge=0)


def dense_timeline(timeline: Timeline) -> list[float]:
    values: list[float] = []
    for segment in timeline.segments:
        count = segment.video_end_frame - segment.video_start_frame + 1
        if count == 1:
            values.append(segment.world_start_time)
            continue
        for offset in range(count):
            fraction = offset / (count - 1)
            values.append(
                segment.world_start_time
                + fraction * (segment.world_end_time - segment.world_start_time)
            )
    return values


def identity_timeline(*, fps: int, frame_count: int, world_duration: float) -> Timeline:
    return Timeline(
        fps=fps,
        video_frame_count=frame_count,
        world_duration=world_duration,
        segments=[
            TimelineSegment(
                video_start_frame=0,
                video_end_frame=frame_count - 1,
                world_start_time=0.0,
                world_end_time=(frame_count - 1) / fps,
            )
        ],
    )


def _boundary_score(
    gt: Timeline, prediction: Timeline, tolerance: int
) -> tuple[float, float, float]:
    gt_boundaries = [segment.video_start_frame for segment in gt.segments[1:]]
    predicted = [segment.video_start_frame for segment in prediction.segments[1:]]
    if not gt_boundaries and not predicted:
        return 1.0, 1.0, 1.0
    unmatched = set(gt_boundaries)
    matches = 0
    for boundary in predicted:
        candidates = [item for item in unmatched if abs(item - boundary) <= tolerance]
        if candidates:
            matched = min(candidates, key=lambda item: abs(item - boundary))
            unmatched.remove(matched)
            matches += 1
    precision = matches / len(predicted) if predicted else 0.0
    recall = matches / len(gt_boundaries) if gt_boundaries else 0.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    return precision, recall, f1


def _sign(value: float, epsilon: float = 1e-8) -> int:
    if value > epsilon:
        return 1
    if value < -epsilon:
        return -1
    return 0


def _p90(values: list[float]) -> float:
    ordered = sorted(values)
    index = max(0, math.ceil(0.9 * len(ordered)) - 1)
    return ordered[index]


def evaluate_timeline(
    gt: Timeline, prediction: Timeline, *, boundary_tolerance_frames: int = 2
) -> WorldTimeScore:
    if gt.fps != prediction.fps or gt.video_frame_count != prediction.video_frame_count:
        raise ValueError("GT and prediction timeline sampling must match")
    if not math.isclose(gt.world_duration, prediction.world_duration, abs_tol=1e-8):
        raise ValueError("GT and prediction canonical world durations must match")
    if boundary_tolerance_frames < 0:
        raise ValueError("boundary tolerance must be non-negative")
    gt_values = dense_timeline(gt)
    predicted_values = dense_timeline(prediction)
    errors = [abs(left - right) for left, right in zip(gt_values, predicted_values, strict=True)]
    precision, recall, boundary_f1 = _boundary_score(gt, prediction, boundary_tolerance_frames)
    gt_boundaries = {segment.video_start_frame for segment in gt.segments[1:]}
    direction_matches = 0
    direction_total = 0
    rate_errors: list[float] = []
    for index in range(len(gt_values) - 1):
        if index + 1 in gt_boundaries:
            continue
        gt_delta = gt_values[index + 1] - gt_values[index]
        predicted_delta = predicted_values[index + 1] - predicted_values[index]
        direction_matches += _sign(gt_delta) == _sign(predicted_delta)
        direction_total += 1
        if abs(gt_delta) > 1e-8:
            gt_rate = abs(gt_delta * gt.fps)
            predicted_rate = max(abs(predicted_delta * gt.fps), 1e-6)
            rate_errors.append(abs(math.log(predicted_rate) - math.log(gt_rate)))
    return WorldTimeScore(
        frame_count=len(errors),
        mae_seconds=sum(errors) / len(errors),
        normalized_mae=(sum(errors) / len(errors)) / gt.world_duration,
        median_error_seconds=median(errors),
        p90_error_seconds=_p90(errors),
        boundary_precision=precision,
        boundary_recall=recall,
        boundary_f1=boundary_f1,
        direction_accuracy=direction_matches / direction_total if direction_total else 1.0,
        log_rate_mae=sum(rate_errors) / len(rate_errors) if rate_errors else 0.0,
    )
