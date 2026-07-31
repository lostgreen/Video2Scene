"""Asset inventory and stable identifier tests."""

from pathlib import Path

from smcb.assets.inventory import build_inventory, stable_asset_id
from smcb.assets.normalizer import _source_is_excluded


def test_stable_asset_id_depends_on_relative_path() -> None:
    first = stable_asset_id("pack", "Cubes/glTF/Cube.gltf")
    assert first == stable_asset_id("pack", "Cubes/glTF/Cube.gltf")
    assert first != stable_asset_id("pack", "Nature/glTF/Cube.gltf")
    assert first.startswith("pack_cube_")


def test_inventory_is_sorted_and_content_addressed(tmp_path: Path) -> None:
    (tmp_path / "z.txt").write_text("last", encoding="utf-8")
    (tmp_path / "nested").mkdir()
    (tmp_path / "nested" / "a.txt").write_text("first", encoding="utf-8")
    first = build_inventory(tmp_path)
    assert [item["path"] for item in first["files"]] == ["nested/a.txt", "z.txt"]
    (tmp_path / "z.txt").write_text("changed", encoding="utf-8")
    second = build_inventory(tmp_path)
    assert first["inventory_sha256"] != second["inventory_sha256"]


def test_manifest_globs_exclude_rigged_character_assets() -> None:
    patterns = ["Character/**", "**/Character/**"]
    assert _source_is_excluded("Character/glTF/Character.gltf", patterns)
    assert _source_is_excluded(
        "Platformer Game Kit - Dec 2021/Character/glTF/Character.gltf", patterns
    )
    assert not _source_is_excluded("Cubes/glTF/Cube_Bricks.gltf", patterns)
