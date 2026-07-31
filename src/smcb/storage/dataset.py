"""Dataset construction, resumability, reproducibility, and validation."""

from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass
from pathlib import Path

from smcb import __version__
from smcb.blender.runner import render_scene
from smcb.dsl.io import load_scene, write_scene
from smcb.generation.config import DatasetConfig
from smcb.generation.quality_checks import QCReport, run_quality_checks
from smcb.generation.sampler import candidate_library, load_asset_index, sample_scene


@dataclass(frozen=True)
class DatasetBuildResult:
    dataset_dir: Path
    requested: int
    generated: int
    skipped: int


def _git_commit(project_root: Path) -> str:
    result = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=project_root,
        capture_output=True,
        text=True,
        check=False,
    )
    return result.stdout.strip() if result.returncode == 0 else "unknown"


def _blender_version(blender_bin: str) -> str:
    result = subprocess.run(
        [blender_bin, "--version"], capture_output=True, text=True, check=False, timeout=30
    )
    lines = result.stdout.splitlines()
    return lines[0] if result.returncode == 0 and lines else "unknown"


def _write_metadata(
    *,
    sample_dir: Path,
    sample_id: str,
    scene_seed: int,
    template: str,
    asset_pack: str,
    asset_manifest_hash: str,
    asset_index_path: Path,
    candidates: list[str],
    git_commit: str,
    blender_version: str,
) -> None:
    payload = {
        "sample_id": sample_id,
        "seed": scene_seed,
        "template": template,
        "generator_version": __version__,
        "git_commit": git_commit,
        "blender_version": blender_version,
        "asset_pack": asset_pack,
        "asset_manifest_hash": asset_manifest_hash,
        "asset_index_path": str(asset_index_path.resolve()),
        "candidate_asset_ids": candidates,
    }
    (sample_dir / "metadata.json").write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    (sample_dir / "gt" / "candidates.json").write_text(
        json.dumps(candidates, indent=2) + "\n", encoding="utf-8"
    )


def build_dataset(
    *,
    config: DatasetConfig,
    output_dir: Path,
    asset_index_path: Path,
    project_root: Path,
    blender_bin: str,
    blender_script: Path,
    num_samples: int | None = None,
    base_seed: int | None = None,
) -> DatasetBuildResult:
    """Generate valid samples with bounded deterministic resampling and resume support."""
    asset_index = load_asset_index(asset_index_path)
    requested = num_samples or config.dataset.num_samples
    seed = config.seed if base_seed is None else base_seed
    output_dir.mkdir(parents=True, exist_ok=True)
    attempts_root = output_dir / "_attempts"
    attempts_root.mkdir(parents=True, exist_ok=True)
    generated = 0
    skipped = 0
    commit = _git_commit(project_root)
    blender_version = _blender_version(blender_bin)

    for sample_index in range(requested):
        sample_id = f"sample_{sample_index + 1:06d}"
        final_dir = output_dir / sample_id
        qc_path = final_dir / "qc.json"
        if qc_path.is_file() and json.loads(qc_path.read_text(encoding="utf-8")).get("passed"):
            skipped += 1
            continue
        accepted = False
        for attempt in range(config.quality_control.max_resample_attempts):
            scene_seed = seed + sample_index * 100_000 + attempt
            attempt_dir = attempts_root / f"{sample_id}_attempt_{attempt:02d}"
            previous_qc = attempt_dir / "qc.json"
            if previous_qc.is_file():
                continue
            attempt_dir.mkdir(parents=True, exist_ok=True)
            scene = sample_scene(
                config=config,
                asset_index=asset_index,
                seed=scene_seed,
                sample_id=sample_id,
                sample_index=sample_index,
            )
            scene_path = attempt_dir / "scene.json"
            write_scene(scene, scene_path)
            candidates = candidate_library(
                scene, asset_index, config.assets.candidate_library_size, scene_seed
            )
            try:
                render_scene(
                    scene_path=scene_path,
                    asset_index_path=asset_index_path,
                    output_dir=attempt_dir,
                    blender_bin=blender_bin,
                    blender_script=blender_script,
                )
                _write_metadata(
                    sample_dir=attempt_dir,
                    sample_id=scene.sample_id,
                    scene_seed=scene_seed,
                    template=scene.template,
                    asset_pack=asset_index.pack_id,
                    asset_manifest_hash=asset_index.asset_manifest_hash,
                    asset_index_path=asset_index_path,
                    candidates=candidates,
                    git_commit=commit,
                    blender_version=blender_version,
                )
                report = run_quality_checks(attempt_dir, scene, config.quality_control)
            except Exception as error:
                report = QCReport(False, [f"pipeline_error:{type(error).__name__}:{error}"], {})
            report.write(attempt_dir / "qc.json")
            if report.passed:
                attempt_dir.rename(final_dir)
                generated += 1
                accepted = True
                break
        if not accepted:
            raise RuntimeError(
                f"failed to generate {sample_id} after "
                f"{config.quality_control.max_resample_attempts} attempts"
            )

    summary = {
        "schema_version": "1.0",
        "name": config.dataset.name,
        "requested": requested,
        "generated": generated,
        "skipped": skipped,
        "seed": seed,
        "asset_manifest_hash": asset_index.asset_manifest_hash,
    }
    (output_dir / "dataset.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return DatasetBuildResult(output_dir, requested, generated, skipped)


def reproduce_sample(
    *,
    sample_dir: Path,
    output_dir: Path,
    blender_bin: str,
    blender_script: Path,
) -> Path:
    """Recompile a saved scene with its recorded asset index."""
    metadata = json.loads((sample_dir / "metadata.json").read_text(encoding="utf-8"))
    asset_index_path = Path(metadata["asset_index_path"])
    write_scene(load_scene(sample_dir / "scene.json"), output_dir / "scene.json")
    render_scene(
        scene_path=output_dir / "scene.json",
        asset_index_path=asset_index_path,
        output_dir=output_dir,
        blender_bin=blender_bin,
        blender_script=blender_script,
    )
    return output_dir


def validate_dataset(dataset_dir: Path) -> dict[str, object]:
    """Validate sample contracts without replaying Blender."""
    sample_dirs = sorted(path for path in dataset_dir.glob("sample_*") if path.is_dir())
    invalid: dict[str, list[str]] = {}
    required = (
        "scene.json",
        "metadata.json",
        "qc.json",
        "input.mp4",
        "scene.blend",
        "scene.glb",
        "gt/camera.json",
        "gt/trajectories.json",
        "gt/visibility.json",
        "gt/candidates.json",
        "debug/preview.png",
    )
    for sample_dir in sample_dirs:
        failures = [item for item in required if not (sample_dir / item).is_file()]
        try:
            scene = load_scene(sample_dir / "scene.json")
            frame_count = len(list((sample_dir / "frames").glob("frame_*.png")))
            expected = scene.render.frame_end - scene.render.frame_start + 1
            if frame_count != expected:
                failures.append(f"frame_count:{frame_count}:{expected}")
            qc = json.loads((sample_dir / "qc.json").read_text(encoding="utf-8"))
            if not qc.get("passed"):
                failures.append("qc_failed")
        except (OSError, ValueError, json.JSONDecodeError) as error:
            failures.append(f"invalid_json:{type(error).__name__}")
        if failures:
            invalid[sample_dir.name] = failures
    return {
        "dataset_dir": str(dataset_dir.resolve()),
        "sample_count": len(sample_dirs),
        "valid_count": len(sample_dirs) - len(invalid),
        "invalid": invalid,
        "passed": bool(sample_dirs) and not invalid,
    }
