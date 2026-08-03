"""Read-only compatibility diagnostics for the pinned SceneActBench harness."""

from __future__ import annotations

import importlib.util
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

from smcb.integrations.sceneactbench.attribution import SCENEACT_LICENSE
from smcb.integrations.sceneactbench.config import SceneActConfig


@dataclass(frozen=True)
class SceneActDoctorReport:
    """Machine-readable result of a SceneActBench compatibility check."""

    sceneact_root: str
    sceneact_data_root: str
    sceneact_commit: str | None
    expected_commit: str
    commit_matches: bool
    license: str | None
    blender: str | None
    blender_path: str | None
    mcp_importable: bool
    numpy: bool
    scipy: bool
    metrics_t6_found: bool
    telemetry_disabled: bool
    passed: bool


def dependency_available(module: str) -> bool:
    """Return whether a Python module can be resolved without importing it."""
    try:
        return importlib.util.find_spec(module) is not None
    except (ImportError, ModuleNotFoundError, ValueError):
        return False


def sceneact_commit(root: Path) -> str | None:
    """Resolve the checked-out upstream commit without contacting the network."""
    if not root.is_dir():
        return None
    try:
        completed = subprocess.run(
            ["git", "-C", str(root), "rev-parse", "HEAD"],
            check=False,
            capture_output=True,
            text=True,
            timeout=10,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    commit = completed.stdout.strip()
    return commit if completed.returncode == 0 and len(commit) == 40 else None


def _license_kind(root: Path) -> str | None:
    license_path = root / "LICENSE"
    if not license_path.is_file():
        return None
    try:
        header = license_path.read_text(encoding="utf-8")[:2048]
    except OSError:
        return None
    return SCENEACT_LICENSE if "MIT License" in header else "unknown"


def _blender_version(configured_path: str | None) -> tuple[str | None, str | None, bool]:
    resolved = configured_path or shutil.which("blender")
    if resolved is None:
        return None, None, False
    path = Path(resolved).expanduser()
    if configured_path and not path.is_file():
        return str(path), "configured path missing", False
    try:
        completed = subprocess.run(
            [str(path), "--version"],
            check=False,
            capture_output=True,
            text=True,
            timeout=20,
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        return str(path), f"failed to start: {error}", False
    lines = (completed.stdout or completed.stderr).splitlines()
    version = lines[0] if lines else f"exit code {completed.returncode}"
    return str(path), version, completed.returncode == 0


def collect_sceneact_doctor(config: SceneActConfig) -> SceneActDoctorReport:
    """Inspect the pinned harness and minimal Dynamic scorer runtime."""
    commit = sceneact_commit(config.root)
    license_kind = _license_kind(config.root)
    metrics_found = (config.root / "src" / "harness" / "metrics_t6.py").is_file()
    blender_path, blender_version, blender_ok = _blender_version(config.blender_bin)
    mcp_available = dependency_available("mcp")
    numpy_available = dependency_available("numpy")
    scipy_available = dependency_available("scipy")
    commit_matches = commit == config.expected_commit
    passed = all(
        (
            config.root.is_dir(),
            commit_matches,
            license_kind == SCENEACT_LICENSE,
            metrics_found,
            blender_ok,
            mcp_available,
            numpy_available,
            scipy_available,
            config.telemetry_disabled,
        )
    )
    return SceneActDoctorReport(
        sceneact_root=str(config.root),
        sceneact_data_root=str(config.data_root),
        sceneact_commit=commit,
        expected_commit=config.expected_commit,
        commit_matches=commit_matches,
        license=license_kind,
        blender=blender_version,
        blender_path=blender_path,
        mcp_importable=mcp_available,
        numpy=numpy_available,
        scipy=scipy_available,
        metrics_t6_found=metrics_found,
        telemetry_disabled=config.telemetry_disabled,
        passed=passed,
    )
