"""Subprocess boundary for deterministic Blender compilation and video encoding."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

from smcb.dsl.io import load_scene


@dataclass(frozen=True)
class RenderResult:
    sample_dir: Path
    video_path: Path
    blender_log: Path
    ffmpeg_log: Path


def render_scene(
    *,
    scene_path: Path,
    asset_index_path: Path,
    output_dir: Path,
    blender_bin: str,
    blender_script: Path,
    ffmpeg_bin: str | None = None,
) -> RenderResult:
    """Compile a Scene Program in Blender, then encode its PNG frames with ffmpeg."""
    scene = load_scene(scene_path)
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "frames").mkdir(parents=True, exist_ok=True)
    (output_dir / "gt").mkdir(parents=True, exist_ok=True)
    (output_dir / "debug").mkdir(parents=True, exist_ok=True)
    blender_log = output_dir / "debug" / "blender.log"
    output_scene_path = output_dir / "scene.json"
    if scene_path.resolve() != output_scene_path.resolve():
        output_scene_path.write_text(scene_path.read_text(encoding="utf-8"), encoding="utf-8")
    command = [
        blender_bin,
        "--background",
        "--factory-startup",
        "--gpu-backend",
        os.environ.get("BLENDER_GPU_BACKEND", "opengl"),
        "--python",
        str(blender_script),
        "--",
        "--scene",
        str(output_scene_path.resolve()),
        "--asset-index",
        str(asset_index_path.resolve()),
        "--output",
        str(output_dir.resolve()),
    ]
    with blender_log.open("w", encoding="utf-8") as log:
        result = subprocess.run(command, stdout=log, stderr=subprocess.STDOUT, check=False)
    if result.returncode != 0:
        raise RuntimeError(f"Blender render failed; see {blender_log}")

    resolved_ffmpeg = ffmpeg_bin or shutil.which("ffmpeg")
    if resolved_ffmpeg is None:
        raise FileNotFoundError("ffmpeg was not found")
    video_path = output_dir / "input.mp4"
    ffmpeg_log = output_dir / "debug" / "ffmpeg.log"
    encode_command = [
        resolved_ffmpeg,
        "-y",
        "-loglevel",
        "warning",
        "-framerate",
        str(scene.render.fps),
        "-start_number",
        str(scene.render.frame_start),
        "-i",
        str(output_dir / "frames" / "frame_%04d.png"),
        "-c:v",
        "libx264",
        "-preset",
        "medium",
        "-crf",
        "18",
        "-pix_fmt",
        "yuv420p",
        "-movflags",
        "+faststart",
        str(video_path),
    ]
    with ffmpeg_log.open("w", encoding="utf-8") as log:
        encoded = subprocess.run(encode_command, stdout=log, stderr=subprocess.STDOUT, check=False)
    if encoded.returncode != 0:
        raise RuntimeError(f"ffmpeg encode failed; PNG frames remain available; see {ffmpeg_log}")

    first_frame = output_dir / "frames" / f"frame_{scene.render.frame_start:04d}.png"
    if first_frame.is_file():
        shutil.copyfile(first_frame, output_dir / "debug" / "preview.png")
    result_payload = {
        "sample_id": scene.sample_id,
        "frame_count": scene.render.frame_end - scene.render.frame_start + 1,
        "fps": scene.render.fps,
        "video": video_path.name,
    }
    (output_dir / "debug" / "render_result.json").write_text(
        json.dumps(result_payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return RenderResult(
        sample_dir=output_dir,
        video_path=video_path,
        blender_log=blender_log,
        ffmpeg_log=ffmpeg_log,
    )
