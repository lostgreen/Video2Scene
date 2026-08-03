"""Tests for the initialization CLI."""

import json
from pathlib import Path

import smcb.cli
from smcb.cli import Check, python_check
from smcb.integrations.sceneactbench.doctor import SceneActDoctorReport


def test_python_check_requires_311() -> None:
    assert not python_check((3, 10)).ok
    assert python_check((3, 11)).ok


def test_doctor_json(monkeypatch: object, capsys: object) -> None:
    monkeypatch.setattr(  # type: ignore[attr-defined]
        smcb.cli,
        "collect_doctor_checks",
        lambda _config: (Check(name="python", ok=True, detail="3.11"),),
    )
    assert smcb.cli.main(["doctor", "--json"]) == 0
    payload = json.loads(capsys.readouterr().out)  # type: ignore[attr-defined]
    assert payload[0]["name"] == "python"


def test_sceneact_doctor_json(monkeypatch: object, capsys: object, tmp_path: Path) -> None:
    report = SceneActDoctorReport(
        sceneact_root=str(tmp_path / "sceneactbench"),
        sceneact_data_root=str(tmp_path / "data"),
        sceneact_commit="1" * 40,
        expected_commit="1" * 40,
        commit_matches=True,
        license="MIT",
        blender="Blender 4.5.12 LTS",
        blender_path="/tools/blender",
        mcp_importable=True,
        numpy=True,
        scipy=True,
        metrics_t6_found=True,
        telemetry_disabled=True,
        passed=True,
    )
    monkeypatch.setattr(  # type: ignore[attr-defined]
        smcb.cli, "collect_sceneact_doctor", lambda _config: report
    )

    assert smcb.cli.main(["sceneact", "doctor", "--project-root", str(tmp_path)]) == 0
    payload = json.loads(capsys.readouterr().out)  # type: ignore[attr-defined]
    assert payload["passed"]
    assert payload["sceneact_commit"] == "1" * 40
