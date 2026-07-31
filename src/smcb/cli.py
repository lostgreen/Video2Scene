"""Command-line interface for SceneMotionCodeBench."""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from collections.abc import Sequence
from dataclasses import asdict, dataclass, replace
from pathlib import Path

from smcb import __version__
from smcb.common.config import ProjectConfig


@dataclass(frozen=True)
class Check:
    """One environment diagnostic result."""

    name: str
    ok: bool
    detail: str
    required: bool = True


def python_check(version: tuple[int, int]) -> Check:
    """Check the supported project Python version."""
    return Check(
        name="python",
        ok=version >= (3, 11),
        detail=f"{version[0]}.{version[1]} (requires >=3.11)",
    )


def executable_check(name: str, configured_path: str | None = None) -> Check:
    """Check whether an external executable can be resolved."""
    resolved = configured_path or shutil.which(name)
    if resolved is None:
        return Check(name=name, ok=False, detail="not found")
    path = Path(resolved).expanduser()
    if configured_path and not path.is_file():
        return Check(name=name, ok=False, detail=f"configured path missing: {path}")
    return Check(name=name, ok=True, detail=str(path))


def blender_check(configured_path: str | None) -> Check:
    """Resolve Blender and verify that the binary starts."""
    base = executable_check("blender", configured_path)
    if not base.ok:
        return base
    try:
        completed = subprocess.run(
            [base.detail, "--version"],
            check=False,
            capture_output=True,
            text=True,
            timeout=20,
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        return Check(name="blender", ok=False, detail=f"failed to start: {error}")
    first_line = (completed.stdout or completed.stderr).splitlines()
    detail = first_line[0] if first_line else f"exit code {completed.returncode}"
    return Check(name="blender", ok=completed.returncode == 0, detail=detail)


def collect_doctor_checks(config: ProjectConfig) -> Sequence[Check]:
    """Collect bounded diagnostics without changing the environment."""
    return (
        python_check((sys.version_info.major, sys.version_info.minor)),
        blender_check(config.blender_bin),
        executable_check("ffmpeg"),
        executable_check("node"),
        executable_check("git"),
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="smcb")
    parser.add_argument("--version", action="version", version=__version__)
    commands = parser.add_subparsers(dest="command", required=True)
    doctor = commands.add_parser("doctor", help="check required local tools")
    doctor.add_argument("--json", action="store_true", dest="as_json")
    doctor.add_argument("--root", type=Path, default=Path.cwd())
    doctor.add_argument("--blender-bin")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    config = ProjectConfig.from_env(root=args.root)
    if args.blender_bin:
        config = replace(config, blender_bin=args.blender_bin)
    checks = collect_doctor_checks(config)
    if args.as_json:
        print(json.dumps([asdict(item) for item in checks], indent=2, sort_keys=True))
    else:
        for item in checks:
            marker = "ok" if item.ok else "missing"
            print(f"[{marker:7}] {item.name}: {item.detail}")
    return 0 if all(item.ok or not item.required for item in checks) else 1


if __name__ == "__main__":
    raise SystemExit(main())
