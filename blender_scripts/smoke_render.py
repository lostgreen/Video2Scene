"""Render a tiny scene to verify a headless Blender installation."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import bpy  # type: ignore[import-not-found]


def script_arguments() -> list[str]:
    """Return arguments passed after Blender's ``--`` separator."""
    return sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else []


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument(
        "--engine",
        choices=("BLENDER_EEVEE_NEXT", "CYCLES"),
        default="BLENDER_EEVEE_NEXT",
    )
    parser.add_argument("--size", type=int, default=64)
    parser.add_argument("--samples", type=int, default=1)
    return parser


def main() -> None:
    args = build_parser().parse_args(script_arguments())
    if args.size < 1 or args.samples < 1:
        raise ValueError("size and samples must be positive")

    output = args.output.expanduser().resolve()
    output.parent.mkdir(parents=True, exist_ok=True)

    scene = bpy.context.scene
    scene.render.engine = args.engine
    scene.render.resolution_x = args.size
    scene.render.resolution_y = args.size
    scene.render.resolution_percentage = 100
    scene.render.image_settings.file_format = "PNG"
    scene.render.filepath = str(output)
    if args.engine == "CYCLES":
        scene.cycles.device = "CPU"
        scene.cycles.samples = args.samples

    bpy.ops.render.render(write_still=True)
    print(f"DONE SMCB_BLENDER_SMOKE_OK engine={args.engine} output={output}")


if __name__ == "__main__":
    main()
