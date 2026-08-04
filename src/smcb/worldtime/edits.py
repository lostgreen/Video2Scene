"""Deterministic temporal-edit presets and observation materialization."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path
from typing import cast

from smcb.worldtime.schema import (
    EditKind,
    EditSpan,
    TemporalEditProgram,
    Timeline,
    TimelineSegment,
)

PRESET_ORDER: tuple[EditKind, ...] = ("normal", "reverse", "freeze", "replay")


def edit_program(preset: str, *, fps: int = 24, frame_count: int = 144) -> TemporalEditProgram:
    """Return the four fixed MVP programs used by the first showcase."""
    if frame_count != 144 or fps != 24:
        raise ValueError("the first World-Time demo is fixed at 144 frames and 24 fps")
    presets: dict[str, list[EditSpan]] = {
        "normal": [
            EditSpan(kind="normal", master_start_frame=0, frame_count=144, step=1),
        ],
        "reverse": [
            EditSpan(kind="reverse", master_start_frame=143, frame_count=144, step=-1),
        ],
        "freeze": [
            EditSpan(kind="normal", master_start_frame=0, frame_count=48, step=1),
            EditSpan(kind="freeze", master_start_frame=47, frame_count=24, step=0),
            EditSpan(kind="normal", master_start_frame=48, frame_count=72, step=1),
        ],
        "replay": [
            EditSpan(kind="normal", master_start_frame=0, frame_count=72, step=1),
            EditSpan(kind="replay", master_start_frame=48, frame_count=24, step=1),
            EditSpan(kind="normal", master_start_frame=72, frame_count=48, step=1),
        ],
    }
    try:
        spans = presets[preset]
    except KeyError as error:
        raise ValueError(f"unknown temporal-edit preset: {preset}") from error
    return TemporalEditProgram(
        preset=cast(EditKind, preset),
        fps=fps,
        master_frame_count=frame_count,
        spans=spans,
    )


def master_frame_indices(program: TemporalEditProgram) -> list[int]:
    return [
        span.master_start_frame + span.step * offset
        for span in program.spans
        for offset in range(span.frame_count)
    ]


def program_timeline(program: TemporalEditProgram) -> Timeline:
    segments: list[TimelineSegment] = []
    output_start = 0
    for span in program.spans:
        output_end = output_start + span.frame_count - 1
        world_end_frame = span.master_start_frame + span.step * (span.frame_count - 1)
        segments.append(
            TimelineSegment(
                video_start_frame=output_start,
                video_end_frame=output_end,
                world_start_time=span.master_start_frame / program.fps,
                world_end_time=world_end_frame / program.fps,
            )
        )
        output_start = output_end + 1
    return Timeline(
        fps=program.fps,
        video_frame_count=program.master_frame_count,
        world_duration=program.master_frame_count / program.fps,
        segments=segments,
    )


def dense_world_times(program: TemporalEditProgram) -> list[float]:
    return [frame / program.fps for frame in master_frame_indices(program)]


def _link_or_copy(source: Path, destination: Path) -> None:
    try:
        os.link(source, destination)
    except OSError:
        shutil.copy2(source, destination)


def _encode_frames(*, frames_dir: Path, output: Path, fps: int, ffmpeg_bin: str) -> Path:
    log_path = output.with_suffix(".ffmpeg.log")
    command = [
        ffmpeg_bin,
        "-y",
        "-loglevel",
        "warning",
        "-framerate",
        str(fps),
        "-start_number",
        "1",
        "-i",
        str(frames_dir / "frame_%04d.png"),
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
        str(output),
    ]
    with log_path.open("w", encoding="utf-8") as log:
        result = subprocess.run(command, stdout=log, stderr=subprocess.STDOUT, check=False)
    if result.returncode != 0:
        raise RuntimeError(f"temporal edit encode failed; see {log_path}")
    return output


def materialize_observation(
    *,
    master_frames_dir: Path,
    output_dir: Path,
    program: TemporalEditProgram,
    ffmpeg_bin: str,
) -> Path:
    """Create one edited frame sequence and MP4 without duplicating PNG storage."""
    if output_dir.exists():
        raise FileExistsError(f"observation output already exists: {output_dir}")
    master_frames = sorted(master_frames_dir.glob("frame_*.png"))
    if len(master_frames) != program.master_frame_count:
        raise ValueError(
            f"master frame count mismatch: {len(master_frames)} != {program.master_frame_count}"
        )
    frames_dir = output_dir / "frames"
    frames_dir.mkdir(parents=True)
    for output_index, master_index in enumerate(master_frame_indices(program), start=1):
        _link_or_copy(master_frames[master_index], frames_dir / f"frame_{output_index:04d}.png")
    timeline = program_timeline(program)
    (output_dir / "edit_program.json").write_text(
        program.model_dump_json(indent=2) + "\n", encoding="utf-8"
    )
    (output_dir / "timeline.json").write_text(
        timeline.model_dump_json(indent=2) + "\n", encoding="utf-8"
    )
    (output_dir / "frame_to_world_time.json").write_text(
        json.dumps({"fps": program.fps, "world_times": dense_world_times(program)}, indent=2)
        + "\n",
        encoding="utf-8",
    )
    shutil.copy2(frames_dir / "frame_0001.png", output_dir / "preview.png")
    return _encode_frames(
        frames_dir=frames_dir,
        output=output_dir / "input.mp4",
        fps=program.fps,
        ffmpeg_bin=ffmpeg_bin,
    )
