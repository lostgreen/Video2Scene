"""One-command construction of the first displayable World-Time benchmark demo."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path

from pydantic import BaseModel

from smcb.dsl.io import load_scene
from smcb.worldtime.edits import (
    PRESET_ORDER,
    edit_program,
    materialize_observation,
    program_timeline,
)
from smcb.worldtime.evaluation import evaluate_timeline, identity_timeline


class WorldTimeDemoResult(BaseModel):
    output_dir: Path
    master_video: Path
    showcase_video: Path
    observations: dict[str, Path]
    report_json: Path


def _link_or_copy(source: Path, destination: Path) -> None:
    try:
        os.link(source, destination)
    except OSError:
        shutil.copy2(source, destination)


def _encode_showcase(*, videos: list[Path], output: Path, ffmpeg_bin: str) -> None:
    labels = ("NORMAL", "REVERSE", "FREEZE", "REPLAY")
    command = [ffmpeg_bin, "-y", "-loglevel", "warning"]
    for video in videos:
        command.extend(["-i", str(video)])
    labeled = ";".join(
        f"[{index}:v]drawtext=text='{label}':x=18:y=18:fontsize=28:"
        "fontcolor=white:box=1:boxcolor=black@0.65"
        f"[v{index}]"
        for index, label in enumerate(labels)
    )
    stack = ";[v0][v1]hstack=inputs=2[top];[v2][v3]hstack=inputs=2[bottom];"
    stack += "[top][bottom]vstack=inputs=2[out]"
    command.extend(
        [
            "-filter_complex",
            labeled + stack,
            "-map",
            "[out]",
            "-an",
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
    )
    log_path = output.with_suffix(".ffmpeg.log")
    with log_path.open("w", encoding="utf-8") as log:
        result = subprocess.run(command, stdout=log, stderr=subprocess.STDOUT, check=False)
    if result.returncode == 0:
        return
    fallback = [ffmpeg_bin, "-y", "-loglevel", "warning"]
    for video in videos:
        fallback.extend(["-i", str(video)])
    fallback.extend(
        [
            "-filter_complex",
            "[0:v][1:v]hstack=inputs=2[top];[2:v][3:v]hstack=inputs=2[bottom];"
            "[top][bottom]vstack=inputs=2[out]",
            "-map",
            "[out]",
            "-an",
            "-c:v",
            "libx264",
            "-preset",
            "medium",
            "-crf",
            "18",
            "-pix_fmt",
            "yuv420p",
            str(output),
        ]
    )
    with log_path.open("a", encoding="utf-8") as log:
        fallback_result = subprocess.run(
            fallback, stdout=log, stderr=subprocess.STDOUT, check=False
        )
    if fallback_result.returncode != 0:
        raise RuntimeError(f"showcase encode failed; see {log_path}")


def build_worldtime_demo(
    *, master_sample_dir: Path, output_dir: Path, ffmpeg_bin: str
) -> WorldTimeDemoResult:
    """Generate four edits, oracle/baseline scores, and a labeled 2x2 MP4."""
    master_sample_dir = master_sample_dir.expanduser().resolve()
    output_dir = output_dir.expanduser().resolve()
    if output_dir.exists():
        raise FileExistsError(f"World-Time demo output already exists: {output_dir}")
    scene = load_scene(master_sample_dir / "scene.json")
    frame_count = scene.render.frame_end - scene.render.frame_start + 1
    if scene.schema_version != "0.2" or not scene.animations or frame_count != 144:
        raise ValueError("World-Time demo requires the 144-frame dynamic canonical master")
    output_dir.mkdir(parents=True)
    master_video = output_dir / "master.mp4"
    _link_or_copy(master_sample_dir / "input.mp4", master_video)
    observations: dict[str, Path] = {}
    observation_report: dict[str, object] = {}
    report: dict[str, object] = {
        "schema_version": "0.1",
        "master_sample": str(master_sample_dir),
        "fps": scene.render.fps,
        "frame_count": frame_count,
        "world_duration": frame_count / scene.render.fps,
        "observations": observation_report,
    }
    videos: list[Path] = []
    for preset in PRESET_ORDER:
        program = edit_program(preset, fps=scene.render.fps, frame_count=frame_count)
        observation_dir = output_dir / "observations" / preset
        video = materialize_observation(
            master_frames_dir=master_sample_dir / "frames",
            output_dir=observation_dir,
            program=program,
            ffmpeg_bin=ffmpeg_bin,
        )
        gt = program_timeline(program)
        identity = identity_timeline(
            fps=gt.fps,
            frame_count=gt.video_frame_count,
            world_duration=gt.world_duration,
        )
        scores = {
            "oracle": evaluate_timeline(gt, gt).model_dump(mode="json"),
            "identity_baseline": evaluate_timeline(gt, identity).model_dump(mode="json"),
        }
        (observation_dir / "scores.json").write_text(
            json.dumps(scores, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        observations[preset] = observation_dir
        videos.append(video)
        observation_report[preset] = {
            "video": str(video),
            "timeline": str(observation_dir / "timeline.json"),
            "scores": scores,
        }
    showcase = output_dir / "showcase.mp4"
    _encode_showcase(videos=videos, output=showcase, ffmpeg_bin=ffmpeg_bin)
    (output_dir / "showcase_layout.json").write_text(
        json.dumps(
            {
                "top_left": "normal",
                "top_right": "reverse",
                "bottom_left": "freeze",
                "bottom_right": "replay",
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    report_path = output_dir / "demo_report.json"
    report["showcase_video"] = str(showcase)
    report_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return WorldTimeDemoResult(
        output_dir=output_dir,
        master_video=master_video,
        showcase_video=showcase,
        observations=observations,
        report_json=report_path,
    )
