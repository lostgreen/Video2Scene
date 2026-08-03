"""Project path configuration tests."""

from pathlib import Path

from smcb.common.config import ProjectConfig


def test_external_project_data_root(tmp_path: Path) -> None:
    external = tmp_path / "external"
    config = ProjectConfig.from_env(
        root=tmp_path,
        environ={"SMCB_PROJECT_DATA_ROOT": str(external)},
    )
    assert config.asset_root == external / "assets"
    assert config.data_dir == external / "data"
    assert config.artifacts_dir == external / "artifacts"


def test_explicit_paths_override_project_data_root(tmp_path: Path) -> None:
    config = ProjectConfig.from_env(
        root=tmp_path,
        environ={
            "SMCB_PROJECT_DATA_ROOT": str(tmp_path / "external"),
            "SMCB_ASSET_ROOT": str(tmp_path / "assets_override"),
            "SMCB_DATA_DIR": str(tmp_path / "data_override"),
        },
    )
    assert config.asset_root == tmp_path / "assets_override"
    assert config.data_dir == tmp_path / "data_override"


def test_smcb_blender_bin_takes_precedence_over_legacy_name(tmp_path: Path) -> None:
    config = ProjectConfig.from_env(
        root=tmp_path,
        environ={
            "SMCB_BLENDER_BIN": "/tools/smcb-blender",
            "BLENDER_BIN": "/tools/legacy-blender",
        },
    )
    assert config.blender_bin == "/tools/smcb-blender"
