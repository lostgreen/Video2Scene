"""Scoped acquisition and validation for one official Dynamic sample."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from smcb.integrations.sceneactbench.attribution import (
    SCENEACT_DATASET_LICENSE,
    SCENEACT_DATASET_REPOSITORY,
    SCENEACT_DATASET_REVISION,
)
from smcb.integrations.sceneactbench.contracts import (
    DynamicFetchResult,
    DynamicSampleInspection,
    FetchProfile,
)

_SCENE_ID = re.compile(r"^t6l[0-9]+_[a-z0-9][a-z0-9_]*$")
_ORACLE_RELATIVE_FILES = (
    "camera.json",
    "gt/gt_scene.glb",
    "gt/trajectory.json",
    "layout_gt.json",
    "meta.json",
    "preview.png",
    "reference.mp4",
)
_PROVENANCE_FILES = frozenset({"LICENSE_DATASET.txt", "source.json"})


def validate_scene_id(scene_id: str) -> str:
    """Reject arbitrary paths before constructing Hugging Face patterns."""
    if not _SCENE_ID.fullmatch(scene_id):
        raise ValueError(f"invalid SceneActBench Dynamic scene ID: {scene_id!r}")
    return scene_id


def scene_relative_dir(scene_id: str) -> Path:
    return Path("benchmark_t6_final") / validate_scene_id(scene_id)


def _allow_patterns(scene_id: str, profile: FetchProfile) -> list[str]:
    base = scene_relative_dir(scene_id).as_posix()
    if profile == "full":
        return [f"{base}/**"]
    return [f"{base}/{relative}" for relative in _ORACLE_RELATIVE_FILES]


def _snapshot_download(**kwargs: Any) -> str:
    try:
        from huggingface_hub import snapshot_download
    except ImportError as error:
        raise RuntimeError(
            "SceneActBench downloads require the 'sceneact' optional dependency"
        ) from error
    return snapshot_download(**kwargs)


def _required_failures(sample_dir: Path, profile: FetchProfile) -> list[str]:
    failures = [
        f"missing:{relative}"
        for relative in _ORACLE_RELATIVE_FILES
        if not (sample_dir / relative).is_file()
    ]
    if profile == "full":
        if not any((sample_dir / "components").glob("*.glb")):
            failures.append("missing:components/*.glb")
        if not any((sample_dir / "reference").glob("*.png")):
            failures.append("missing:reference/*.png")
    return failures


def _write_provenance(
    sample_dir: Path,
    *,
    scene_id: str,
    profile: FetchProfile,
) -> tuple[int, int]:
    payload_files = sorted(
        path
        for path in sample_dir.rglob("*")
        if path.is_file() and path.name not in _PROVENANCE_FILES
    )
    manifest_files = [
        {"path": path.relative_to(sample_dir).as_posix(), "bytes": path.stat().st_size}
        for path in payload_files
    ]
    source = {
        "dataset": SCENEACT_DATASET_REPOSITORY,
        "dataset_revision": SCENEACT_DATASET_REVISION,
        "license": SCENEACT_DATASET_LICENSE,
        "scene_id": scene_id,
        "profile": profile,
        "files": manifest_files,
    }
    (sample_dir / "source.json").write_text(
        json.dumps(source, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    (sample_dir / "LICENSE_DATASET.txt").write_text(
        "SceneActBench dataset subset\n"
        f"Source: https://huggingface.co/datasets/{SCENEACT_DATASET_REPOSITORY}\n"
        f"Revision: {SCENEACT_DATASET_REVISION}\n"
        f"License: {SCENEACT_DATASET_LICENSE}\n\n"
        "This dataset is separate from the MIT-licensed SceneActBench harness. "
        "Use and redistribution must follow the dataset license.\n",
        encoding="utf-8",
    )
    return len(payload_files), sum(path.stat().st_size for path in payload_files)


def fetch_dynamic_sample(
    *,
    scene_id: str,
    output_root: Path,
    profile: FetchProfile = "oracle",
) -> DynamicFetchResult:
    """Fetch one pinned Dynamic scene, never the complete SceneActBench dataset."""
    validate_scene_id(scene_id)
    if profile not in ("oracle", "full"):
        raise ValueError(f"unsupported fetch profile: {profile}")
    output_root = output_root.expanduser().resolve()
    output_root.mkdir(parents=True, exist_ok=True)
    _snapshot_download(
        repo_id=SCENEACT_DATASET_REPOSITORY,
        repo_type="dataset",
        revision=SCENEACT_DATASET_REVISION,
        allow_patterns=_allow_patterns(scene_id, profile),
        local_dir=str(output_root),
    )
    sample_dir = output_root / scene_relative_dir(scene_id)
    failures = _required_failures(sample_dir, profile)
    if failures:
        raise FileNotFoundError(
            f"incomplete SceneActBench sample {scene_id}: {', '.join(failures)}"
        )
    file_count, byte_count = _write_provenance(sample_dir, scene_id=scene_id, profile=profile)
    return DynamicFetchResult(
        scene_id=scene_id,
        profile=profile,
        sample_dir=str(sample_dir),
        dataset_revision=SCENEACT_DATASET_REVISION,
        downloaded_file_count=file_count,
        downloaded_bytes=byte_count,
    )


def _load_json_object(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"expected a JSON object: {path}")
    return payload


def inspect_dynamic_sample(sample_dir: Path) -> DynamicSampleInspection:
    """Validate the scorer-facing subset without reading frame or GLB payload bytes."""
    sample_dir = sample_dir.expanduser().resolve()
    failures = _required_failures(sample_dir, "oracle")
    if failures:
        raise FileNotFoundError(
            f"incomplete SceneActBench sample {sample_dir.name}: {', '.join(failures)}"
        )
    meta = _load_json_object(sample_dir / "meta.json")
    layout = _load_json_object(sample_dir / "layout_gt.json")
    trajectories = _load_json_object(sample_dir / "gt" / "trajectory.json")
    scene_id = str(meta.get("sample_id", ""))
    if scene_id != sample_dir.name:
        failures.append(f"sample_id_mismatch:{scene_id}")
    fps = int(meta.get("fps", 0))
    frame_count = int(meta.get("n_frames", 0))
    if fps <= 0:
        failures.append("invalid:fps")
    if frame_count <= 0:
        failures.append("invalid:n_frames")
    mover_counts: dict[str, int] = {}
    for name, items in trajectories.items():
        if not isinstance(items, list) or not items or not isinstance(items[0], dict):
            continue
        if "f" in items[0] and "loc" in items[0]:
            mover_counts[str(name)] = len(items)
    if not mover_counts:
        failures.append("invalid:no_mover_trajectories")
    for name, count in mover_counts.items():
        if count != frame_count:
            failures.append(f"trajectory_frame_count:{name}:{count}")
    layout_objects = layout.get("objects") or layout.get("static_objects") or []
    if not isinstance(layout_objects, list):
        failures.append("invalid:layout_objects")
        layout_objects = []
    license_found = (sample_dir / "LICENSE_DATASET.txt").is_file()
    source_found = (sample_dir / "source.json").is_file()
    if not license_found:
        failures.append("missing:LICENSE_DATASET.txt")
    if not source_found:
        failures.append("missing:source.json")
    return DynamicSampleInspection(
        scene_id=scene_id,
        sample_dir=str(sample_dir),
        fps=fps,
        frame_count=frame_count,
        mover_names=sorted(mover_counts),
        trajectory_frame_counts=mover_counts,
        static_object_count=len(layout_objects),
        reference_video=str(sample_dir / "reference.mp4"),
        gt_scene_glb=str(sample_dir / "gt" / "gt_scene.glb"),
        license_found=license_found,
        source_metadata_found=source_found,
        failures=failures,
        passed=not failures,
    )
