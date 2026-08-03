"""Read-only SceneActBench doctor tests."""

from dataclasses import replace
from pathlib import Path

import smcb.integrations.sceneactbench.doctor as sceneact_doctor
from smcb.integrations.sceneactbench.attribution import SCENEACT_PINNED_COMMIT
from smcb.integrations.sceneactbench.config import SceneActConfig


def _upstream_fixture(tmp_path: Path) -> Path:
    root = tmp_path / "sceneactbench"
    (root / "src" / "harness").mkdir(parents=True)
    (root / "src" / "harness" / "metrics_t6.py").write_text("# scorer\n")
    (root / "LICENSE").write_text("MIT License\n", encoding="utf-8")
    return root


def test_doctor_passes_only_complete_pinned_runtime(tmp_path: Path, monkeypatch: object) -> None:
    root = _upstream_fixture(tmp_path)
    config = SceneActConfig(
        project_root=tmp_path,
        root=root,
        data_root=tmp_path / "data",
        blender_bin="/tools/blender",
        telemetry_disabled=True,
    )
    monkeypatch.setattr(  # type: ignore[attr-defined]
        sceneact_doctor, "_git_commit", lambda _root: SCENEACT_PINNED_COMMIT
    )
    monkeypatch.setattr(  # type: ignore[attr-defined]
        sceneact_doctor,
        "_blender_version",
        lambda _path: ("/tools/blender", "Blender 4.5.12 LTS", True),
    )
    monkeypatch.setattr(  # type: ignore[attr-defined]
        sceneact_doctor, "dependency_available", lambda _module: True
    )

    report = sceneact_doctor.collect_sceneact_doctor(config)

    assert report.passed
    assert report.commit_matches
    assert report.license == "MIT"
    assert report.metrics_t6_found
    assert report.blender == "Blender 4.5.12 LTS"


def test_doctor_rejects_commit_drift_and_enabled_telemetry(
    tmp_path: Path, monkeypatch: object
) -> None:
    root = _upstream_fixture(tmp_path)
    config = SceneActConfig(
        project_root=tmp_path,
        root=root,
        data_root=tmp_path / "data",
        blender_bin="/tools/blender",
        telemetry_disabled=True,
    )
    monkeypatch.setattr(  # type: ignore[attr-defined]
        sceneact_doctor, "_git_commit", lambda _root: "0" * 40
    )
    monkeypatch.setattr(  # type: ignore[attr-defined]
        sceneact_doctor,
        "_blender_version",
        lambda _path: ("/tools/blender", "Blender 4.5.12 LTS", True),
    )
    monkeypatch.setattr(  # type: ignore[attr-defined]
        sceneact_doctor, "dependency_available", lambda _module: True
    )

    assert not sceneact_doctor.collect_sceneact_doctor(config).passed
    assert not sceneact_doctor.collect_sceneact_doctor(
        replace(config, telemetry_disabled=False, expected_commit="0" * 40)
    ).passed
