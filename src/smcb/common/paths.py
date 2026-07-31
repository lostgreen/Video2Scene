"""Repository path helpers."""

from pathlib import Path


def find_project_root(start: Path) -> Path:
    """Find the nearest parent containing ``pyproject.toml``."""
    current = start.resolve()
    for candidate in (current, *current.parents):
        if (candidate / "pyproject.toml").is_file():
            return candidate
    raise FileNotFoundError(f"No pyproject.toml found above {start}")
