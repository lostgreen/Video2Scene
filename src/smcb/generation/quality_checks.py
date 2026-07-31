"""Automatic dataset quality checks over rendered artifacts and dense GT."""

from __future__ import annotations

import json
import math
from dataclasses import asdict, dataclass
from itertools import combinations
from pathlib import Path
from typing import Any

from PIL import Image, ImageStat

from smcb.dsl.models import SceneProgram
from smcb.generation.config import QualityControlSection


@dataclass(frozen=True)
class QCReport:
    passed: bool
    failures: list[str]
    metrics: dict[str, Any]

    def write(self, path: Path) -> None:
        path.write_text(json.dumps(asdict(self), indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _distance(first: list[float], second: list[float]) -> float:
    return math.sqrt(sum((left - right) ** 2 for left, right in zip(first, second, strict=True)))


def _iou(left: list[float], right: list[float]) -> float:
    overlap_width = max(0.0, min(left[2], right[2]) - max(left[0], right[0]))
    overlap_height = max(0.0, min(left[3], right[3]) - max(left[1], right[1]))
    intersection = overlap_width * overlap_height
    left_area = max(0.0, left[2] - left[0]) * max(0.0, left[3] - left[1])
    right_area = max(0.0, right[2] - right[0]) * max(0.0, right[3] - right[1])
    union = left_area + right_area - intersection
    return intersection / union if union > 0 else 0.0


def _motion_positions(
    scene: SceneProgram,
    trajectories: dict[str, list[dict[str, Any]]],
    camera: dict[str, Any],
) -> list[list[float]]:
    animated_target = scene.animations[0].target_id if scene.animations else ""
    if animated_target == scene.camera.id:
        return [frame["position"] for frame in camera["frames"]]
    return [frame["position"] for frame in trajectories.get(animated_target, [])]


def _frame_luminance(frame_paths: list[Path]) -> tuple[float, float]:
    means: list[float] = []
    deviations: list[float] = []
    for path in frame_paths:
        with Image.open(path).convert("RGB") as image:
            stat = ImageStat.Stat(image)
            means.append(sum(stat.mean) / (3.0 * 255.0))
            deviations.append(sum(stat.stddev) / (3.0 * 255.0))
    return sum(means) / len(means), sum(deviations) / len(deviations)


def run_quality_checks(
    sample_dir: Path,
    scene: SceneProgram,
    config: QualityControlSection,
) -> QCReport:
    """Validate one complete sample and return compact failure fingerprints."""
    failures: list[str] = []
    required = [
        "input.mp4",
        "scene.blend",
        "scene.glb",
        "gt/camera.json",
        "gt/trajectories.json",
        "gt/visibility.json",
    ]
    missing = [name for name in required if not (sample_dir / name).is_file()]
    if missing:
        return QCReport(False, [f"missing_artifacts:{','.join(missing)}"], {"missing": missing})

    visibility = json.loads((sample_dir / "gt" / "visibility.json").read_text(encoding="utf-8"))
    trajectories = json.loads((sample_dir / "gt" / "trajectories.json").read_text(encoding="utf-8"))
    camera = json.loads((sample_dir / "gt" / "camera.json").read_text(encoding="utf-8"))
    minimum_ratios = {
        object_id: details["visible_frame_ratio"] for object_id, details in visibility.items()
    }
    minimum_pixels = {
        object_id: details["min_visible_pixels"] for object_id, details in visibility.items()
    }
    for object_id, ratio in minimum_ratios.items():
        if ratio < config.min_visible_frame_ratio:
            failures.append(f"low_visibility:{object_id}:{ratio:.3f}")
    for object_id, pixels in minimum_pixels.items():
        if pixels < config.min_visible_pixels:
            failures.append(f"small_projection:{object_id}:{pixels}")

    camera_inside = any(
        frame.get("camera_inside_bbox", False)
        for details in visibility.values()
        for frame in details["frames"]
    )
    if camera_inside:
        failures.append("camera_inside_mesh_bbox")
    underground = any(
        frame.get("world_bbox_min", [0.0, 0.0, 0.0])[2] < -0.08
        for details in visibility.values()
        for frame in details["frames"]
    )
    if underground:
        failures.append("object_below_ground")

    max_iou = 0.0
    overlap_frames = 0
    for frame_index in range(scene.render.frame_end - scene.render.frame_start + 1):
        bboxes = [
            details["frames"][frame_index]["screen_bbox"]
            for details in visibility.values()
            if details["frames"][frame_index].get("visible")
        ]
        frame_max = max((_iou(left, right) for left, right in combinations(bboxes, 2)), default=0.0)
        max_iou = max(max_iou, frame_max)
        if frame_max > config.max_pairwise_screen_iou:
            overlap_frames += 1
    frame_count = scene.render.frame_end - scene.render.frame_start + 1
    if overlap_frames / frame_count > 0.10:
        failures.append(f"severe_overlap:{overlap_frames / frame_count:.3f}")

    positions = _motion_positions(scene, trajectories, camera)
    max_motion = (
        max((_distance(positions[0], item) for item in positions[1:]), default=0.0)
        if positions
        else 0.0
    )
    endpoint_motion = _distance(positions[0], positions[-1]) if len(positions) > 1 else 0.0
    if max_motion < config.min_motion_distance:
        failures.append(f"insufficient_motion:{max_motion:.4f}")
    if endpoint_motion < config.min_motion_distance * 0.25:
        failures.append(f"identical_endpoints:{endpoint_motion:.4f}")

    frame_paths = sorted((sample_dir / "frames").glob("frame_*.png"))
    expected_frames = frame_count
    if len(frame_paths) != expected_frames:
        failures.append(f"frame_count:{len(frame_paths)}:{expected_frames}")
        luminance_mean, luminance_std = 0.0, 0.0
    else:
        selected = [frame_paths[0], frame_paths[len(frame_paths) // 2], frame_paths[-1]]
        luminance_mean, luminance_std = _frame_luminance(selected)
        if luminance_mean < 0.01:
            failures.append(f"video_black:{luminance_mean:.4f}")
        if luminance_mean > 0.99:
            failures.append(f"video_white:{luminance_mean:.4f}")
        if luminance_std < 0.005:
            failures.append(f"video_flat:{luminance_std:.4f}")

    metrics = {
        "visible_frame_ratio": minimum_ratios,
        "min_visible_pixels": minimum_pixels,
        "max_pairwise_screen_iou": max_iou,
        "overlap_frame_ratio": overlap_frames / frame_count,
        "max_motion_distance": max_motion,
        "endpoint_motion_distance": endpoint_motion,
        "luminance_mean": luminance_mean,
        "luminance_std": luminance_std,
    }
    return QCReport(not failures, failures, metrics)
