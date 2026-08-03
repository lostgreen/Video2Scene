"""Thin wrapper around the pinned upstream Dynamic scorer."""

from __future__ import annotations

import importlib.util
from collections.abc import Callable
from pathlib import Path
from typing import Any, cast

from smcb.integrations.sceneactbench.attribution import SCENEACT_PINNED_COMMIT
from smcb.integrations.sceneactbench.doctor import sceneact_commit
from smcb.integrations.sceneactbench.samples import inspect_dynamic_sample


def _load_evaluate_t6(metrics_path: Path) -> Callable[[str, str], dict[str, Any]]:
    spec = importlib.util.spec_from_file_location("sceneactbench_metrics_t6_pinned", metrics_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load SceneActBench scorer: {metrics_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    evaluate = getattr(module, "evaluate_t6", None)
    if not callable(evaluate):
        raise RuntimeError(f"evaluate_t6 is missing from {metrics_path}")
    return cast(Callable[[str, str], dict[str, Any]], evaluate)


def score_dynamic_prediction(
    *,
    sceneact_root: Path,
    sample_dir: Path,
    prediction_glb: Path,
) -> dict[str, Any]:
    """Score one GLB through the unmodified scorer at the pinned upstream commit."""
    sceneact_root = sceneact_root.expanduser().resolve()
    commit = sceneact_commit(sceneact_root)
    if commit != SCENEACT_PINNED_COMMIT:
        raise RuntimeError(
            f"SceneActBench commit mismatch: expected {SCENEACT_PINNED_COMMIT}, found {commit}"
        )
    inspection = inspect_dynamic_sample(sample_dir)
    if not inspection.passed:
        raise ValueError(f"invalid Dynamic sample: {', '.join(inspection.failures)}")
    prediction_glb = prediction_glb.expanduser().resolve()
    if not prediction_glb.is_file():
        raise FileNotFoundError(f"prediction GLB not found: {prediction_glb}")
    metrics_path = sceneact_root / "src" / "harness" / "metrics_t6.py"
    evaluate = _load_evaluate_t6(metrics_path)
    result = evaluate(str(prediction_glb), inspection.sample_dir)
    if not isinstance(result, dict):
        raise TypeError("SceneActBench evaluate_t6 returned a non-object result")
    return result


def score_dynamic_oracle(*, sceneact_root: Path, sample_dir: Path) -> dict[str, Any]:
    """Use the official GT animated GLB as the prediction for a contract oracle."""
    sample_dir = sample_dir.expanduser().resolve()
    return score_dynamic_prediction(
        sceneact_root=sceneact_root,
        sample_dir=sample_dir,
        prediction_glb=sample_dir / "gt" / "gt_scene.glb",
    )
