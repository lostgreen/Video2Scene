"""Environment-backed configuration for the isolated SceneActBench integration."""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from smcb.common.config import ProjectConfig
from smcb.integrations.sceneactbench.attribution import SCENEACT_PINNED_COMMIT

_TRUE_VALUES = frozenset({"1", "true", "yes", "on"})


@dataclass(frozen=True)
class SceneActConfig:
    """Resolved third-party, data, and Blender settings for SceneActBench."""

    project_root: Path
    root: Path
    data_root: Path
    blender_bin: str | None
    telemetry_disabled: bool
    expected_commit: str = SCENEACT_PINNED_COMMIT

    @classmethod
    def from_project(
        cls,
        project: ProjectConfig,
        environ: Mapping[str, str] | None = None,
    ) -> SceneActConfig:
        values = os.environ if environ is None else environ
        root_value = values.get("SCENEACT_ROOT")
        data_value = values.get("SCENEACT_DATA_ROOT")
        blender_bin = (
            values.get("SCENEACT_BLENDER_BIN")
            or values.get("SMCB_BLENDER_BIN")
            or project.blender_bin
        )
        return cls(
            project_root=project.root,
            root=(
                Path(root_value).expanduser()
                if root_value
                else project.root / "third_party" / "sceneactbench"
            ).resolve(),
            data_root=(
                Path(data_value).expanduser()
                if data_value
                else project.project_data_root / "external_data" / "sceneactbench"
            ).resolve(),
            blender_bin=blender_bin,
            telemetry_disabled=values.get("DISABLE_TELEMETRY", "").lower() in _TRUE_VALUES,
        )
