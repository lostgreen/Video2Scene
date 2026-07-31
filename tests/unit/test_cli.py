"""Tests for the initialization CLI."""

import json

import smcb.cli
from smcb.cli import Check, python_check


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
