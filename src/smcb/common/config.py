"""Centralized project configuration."""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class ProjectConfig:
    """Resolved paths and external executable settings."""

    root: Path
    project_data_root: Path
    asset_root: Path
    data_dir: Path
    artifacts_dir: Path
    blender_bin: str | None

    @classmethod
    def from_env(
        cls,
        root: Path | None = None,
        environ: Mapping[str, str] | None = None,
    ) -> ProjectConfig:
        values = os.environ if environ is None else environ
        project_root = (root or Path.cwd()).resolve()
        project_data_value = values.get("SMCB_PROJECT_DATA_ROOT")
        project_data_root = (
            Path(project_data_value).expanduser() if project_data_value else project_root
        ).resolve()
        asset_value = values.get("SMCB_ASSET_ROOT")
        data_value = values.get("SMCB_DATA_DIR")
        artifacts_value = values.get("SMCB_ARTIFACTS_DIR")
        return cls(
            root=project_root,
            project_data_root=project_data_root,
            asset_root=(
                Path(asset_value).expanduser() if asset_value else project_data_root / "assets"
            ).resolve(),
            data_dir=(
                Path(data_value).expanduser() if data_value else project_data_root / "data"
            ).resolve(),
            artifacts_dir=(
                Path(artifacts_value).expanduser()
                if artifacts_value
                else project_data_root / "artifacts"
            ).resolve(),
            blender_bin=values.get("BLENDER_BIN"),
        )
