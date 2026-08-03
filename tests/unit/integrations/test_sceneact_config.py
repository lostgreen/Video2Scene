"""SceneActBench integration configuration tests."""

import json
from pathlib import Path

from smcb.common.config import ProjectConfig
from smcb.integrations.sceneactbench.attribution import (
    SCENEACT_LICENSE,
    SCENEACT_PINNED_COMMIT,
    SCENEACT_REPOSITORY,
)
from smcb.integrations.sceneactbench.config import SceneActConfig


def test_sceneact_lock_matches_runtime_attribution() -> None:
    repository_root = Path(__file__).resolve().parents[3]
    lock = json.loads(
        (repository_root / "third_party" / "sceneactbench.lock.json").read_text(encoding="utf-8")
    )

    assert lock["repository"] == SCENEACT_REPOSITORY
    assert lock["commit"] == SCENEACT_PINNED_COMMIT
    assert lock["license"] == SCENEACT_LICENSE


def test_sceneact_defaults_stay_below_project_roots(tmp_path: Path) -> None:
    project = ProjectConfig.from_env(
        root=tmp_path,
        environ={"SMCB_PROJECT_DATA_ROOT": str(tmp_path / "external")},
    )
    config = SceneActConfig.from_project(project, environ={})

    assert config.root == tmp_path / "third_party" / "sceneactbench"
    assert config.data_root == tmp_path / "external" / "external_data" / "sceneactbench"
    assert config.blender_bin is None
    assert not config.telemetry_disabled


def test_sceneact_environment_overrides_and_disables_telemetry(tmp_path: Path) -> None:
    project = ProjectConfig.from_env(
        root=tmp_path,
        environ={"SMCB_BLENDER_BIN": "/smcb/blender"},
    )
    config = SceneActConfig.from_project(
        project,
        environ={
            "SCENEACT_ROOT": str(tmp_path / "upstream"),
            "SCENEACT_DATA_ROOT": str(tmp_path / "data"),
            "SCENEACT_BLENDER_BIN": "/sceneact/blender",
            "DISABLE_TELEMETRY": "TRUE",
        },
    )

    assert config.root == tmp_path / "upstream"
    assert config.data_root == tmp_path / "data"
    assert config.blender_bin == "/sceneact/blender"
    assert config.telemetry_disabled
