"""Command-line interface for the Video2Scene data collection MVP."""

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
from smcb.assets.normalizer import normalize_library
from smcb.assets.source import fetch_source, load_source_manifest, source_status
from smcb.blender.runner import render_scene
from smcb.common.config import ProjectConfig
from smcb.dsl.io import load_scene, write_json_schema, write_scene
from smcb.generation.config import load_dataset_config
from smcb.generation.sampler import load_asset_index, sample_scene
from smcb.integrations.sceneactbench import SceneActConfig, collect_sceneact_doctor
from smcb.storage.dataset import build_dataset, reproduce_sample, validate_dataset


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


def _add_asset_common(parser: argparse.ArgumentParser, *, include_limit: bool = False) -> None:
    parser.add_argument(
        "--manifest", type=Path, default=Path("assets/manifests/quaternius_platformer.json")
    )
    parser.add_argument("--asset-root", type=Path)
    if include_limit:
        parser.add_argument("--limit", type=int, default=30)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="video2scene")
    parser.add_argument("--version", action="version", version=__version__)
    commands = parser.add_subparsers(dest="command", required=True)

    doctor = commands.add_parser("doctor", help="check required local tools")
    doctor.add_argument("--json", action="store_true", dest="as_json")
    doctor.add_argument("--root", type=Path, default=Path.cwd())
    doctor.add_argument("--blender-bin")

    assets = commands.add_parser("assets", help="acquire and normalize the fixed asset pack")
    asset_commands = assets.add_subparsers(dest="asset_command", required=True)
    asset_doctor = asset_commands.add_parser("doctor", help="check asset readiness")
    _add_asset_common(asset_doctor)
    asset_fetch = asset_commands.add_parser("fetch", help="download and inventory the source pack")
    _add_asset_common(asset_fetch)
    for name in ("normalize", "previews"):
        action = asset_commands.add_parser(name, help=f"build normalized asset {name}")
        _add_asset_common(action, include_limit=True)
        action.add_argument("--source", type=Path)
        action.add_argument("--output", type=Path)
        action.add_argument("--preview-output", type=Path)
        action.add_argument("--blender-bin")
        action.add_argument("--force", action="store_true")

    sceneact = commands.add_parser(
        "sceneact", help="inspect and operate the pinned SceneActBench compatibility layer"
    )
    sceneact_commands = sceneact.add_subparsers(dest="sceneact_command", required=True)
    sceneact_doctor = sceneact_commands.add_parser(
        "doctor", help="check the pinned harness and minimal Dynamic scorer runtime"
    )
    sceneact_doctor.add_argument("--project-root", type=Path)
    sceneact_doctor.add_argument("--sceneact-root", type=Path)
    sceneact_doctor.add_argument("--data-root", type=Path)
    sceneact_doctor.add_argument("--blender-bin")

    sample = commands.add_parser("sample-scene", help="write one deterministic Scene Program")
    sample.add_argument("--config", type=Path, default=Path("configs/dataset/scene_smoke.yaml"))
    sample.add_argument("--asset-index", type=Path)
    sample.add_argument(
        "--template", choices=("static_orbit", "moving_object", "moving_camera", "parent_motion")
    )
    sample.add_argument("--seed", type=int, default=42)
    sample.add_argument("--sample-id", default="sample_000001")
    sample.add_argument("--output", type=Path, default=Path("scene.json"))

    render = commands.add_parser("render", help="compile and render one Scene Program")
    render.add_argument("--scene", type=Path, required=True)
    render.add_argument("--asset-index", type=Path)
    render.add_argument("--output", type=Path)
    render.add_argument("--blender-bin")

    generate = commands.add_parser("generate", help="build a QC-filtered dataset")
    generate.add_argument("--config", type=Path, required=True)
    generate.add_argument("--asset-index", type=Path)
    generate.add_argument("--output", type=Path)
    generate.add_argument("--num-samples", type=int)
    generate.add_argument("--seed", type=int)
    generate.add_argument("--blender-bin")

    validate = commands.add_parser("validate-dataset", help="check a generated dataset contract")
    validate.add_argument("dataset", type=Path, nargs="?")

    reproduce = commands.add_parser("reproduce", help="re-render a saved sample")
    reproduce.add_argument("sample")
    reproduce.add_argument("--output", type=Path)
    reproduce.add_argument("--blender-bin")

    schema = commands.add_parser("write-schema", help="refresh the Scene Program JSON Schema")
    schema.add_argument(
        "--output", type=Path, default=Path("schemas/scene_program_v0.1.schema.json")
    )
    return parser


def _root_config(root: Path | None = None) -> ProjectConfig:
    return ProjectConfig.from_env(root=root or Path.cwd())


def _blender_bin(config: ProjectConfig, override: str | None) -> str:
    value = override or config.blender_bin or shutil.which("blender")
    if value is None:
        raise FileNotFoundError("Blender not found; set BLENDER_BIN or pass --blender-bin")
    return value


def _manifest_path(config: ProjectConfig, path: Path) -> Path:
    return path if path.is_absolute() else config.root / path


def _print_json(payload: object) -> None:
    print(json.dumps(payload, indent=2, sort_keys=True, default=str))


def _handle_doctor(args: argparse.Namespace) -> int:
    config = _root_config(args.root)
    if args.blender_bin:
        config = replace(config, blender_bin=args.blender_bin)
    checks = collect_doctor_checks(config)
    if args.as_json:
        _print_json([asdict(item) for item in checks])
    else:
        for item in checks:
            marker = "ok" if item.ok else "missing"
            print(f"[{marker:7}] {item.name}: {item.detail}")
    return 0 if all(item.ok or not item.required for item in checks) else 1


def _handle_assets(args: argparse.Namespace, config: ProjectConfig) -> int:
    manifest_path = _manifest_path(config, args.manifest)
    asset_root = (args.asset_root or config.asset_root).resolve()
    if args.asset_command == "doctor":
        status = source_status(manifest_path, asset_root)
        _print_json(status)
        return 0 if status["ready"] else 1
    if args.asset_command == "fetch":
        _print_json(fetch_source(manifest_path, asset_root))
        return 0

    manifest = load_source_manifest(manifest_path)
    source = (args.source or asset_root / "raw" / manifest.pack_id).resolve()
    output = (args.output or asset_root / "normalized").resolve()
    previews = (args.preview_output or asset_root / "previews").resolve()
    index = normalize_library(
        source=source,
        output=output,
        previews=previews,
        manifest_path=manifest_path,
        blender_bin=_blender_bin(config, args.blender_bin),
        blender_script=config.root / "blender_scripts" / "normalize_asset.py",
        limit=args.limit,
        force=args.force,
    )
    _print_json(
        {
            "pack_id": index.pack_id,
            "normalized_count": len(index.assets),
            "asset_manifest_hash": index.asset_manifest_hash,
            "index": output / "index.json",
        }
    )
    return 0


def _handle_sceneact(args: argparse.Namespace) -> int:
    if args.sceneact_command != "doctor":
        raise AssertionError(f"unhandled SceneActBench command: {args.sceneact_command}")
    project = _root_config(args.project_root)
    config = SceneActConfig.from_project(project)
    config = replace(
        config,
        root=(args.sceneact_root or config.root).resolve(),
        data_root=(args.data_root or config.data_root).resolve(),
        blender_bin=args.blender_bin or config.blender_bin,
    )
    report = collect_sceneact_doctor(config)
    _print_json(asdict(report))
    return 0 if report.passed else 1


def _handle_sample(args: argparse.Namespace, config: ProjectConfig) -> int:
    dataset_config = load_dataset_config(_manifest_path(config, args.config))
    index_path = (args.asset_index or config.asset_root / "normalized" / "index.json").resolve()
    scene = sample_scene(
        config=dataset_config,
        asset_index=load_asset_index(index_path),
        seed=args.seed,
        sample_id=args.sample_id,
        template=args.template,
    )
    output = args.output.resolve()
    write_scene(scene, output)
    _print_json({"scene": output, "sample_id": scene.sample_id, "template": scene.template})
    return 0


def _handle_render(args: argparse.Namespace, config: ProjectConfig) -> int:
    scene_path = args.scene.resolve()
    scene = load_scene(scene_path)
    output = (args.output or config.data_dir / "generated" / "manual" / scene.sample_id).resolve()
    index_path = (args.asset_index or config.asset_root / "normalized" / "index.json").resolve()
    result = render_scene(
        scene_path=scene_path,
        asset_index_path=index_path,
        output_dir=output,
        blender_bin=_blender_bin(config, args.blender_bin),
        blender_script=config.root / "blender_scripts" / "compile_scene.py",
    )
    _print_json({"sample_dir": result.sample_dir, "video": result.video_path})
    return 0


def _handle_generate(args: argparse.Namespace, config: ProjectConfig) -> int:
    config_path = _manifest_path(config, args.config)
    dataset_config = load_dataset_config(config_path)
    output = (args.output or config.data_dir / dataset_config.dataset.output_subdir).resolve()
    index_path = (args.asset_index or config.asset_root / "normalized" / "index.json").resolve()
    result = build_dataset(
        config=dataset_config,
        output_dir=output,
        asset_index_path=index_path,
        project_root=config.root,
        blender_bin=_blender_bin(config, args.blender_bin),
        blender_script=config.root / "blender_scripts" / "compile_scene.py",
        num_samples=args.num_samples,
        base_seed=args.seed,
    )
    _print_json(asdict(result))
    return 0


def _resolve_sample(config: ProjectConfig, value: str) -> Path:
    candidate = Path(value)
    if candidate.is_dir():
        return candidate.resolve()
    for dataset in ("mvp", "smoke", "scene_smoke"):
        path = config.data_dir / "generated" / dataset / value
        if path.is_dir():
            return path.resolve()
    raise FileNotFoundError(f"sample directory not found: {value}")


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "doctor":
        return _handle_doctor(args)
    if args.command == "sceneact":
        return _handle_sceneact(args)
    config = _root_config()
    if args.command == "assets":
        return _handle_assets(args, config)
    if args.command == "sample-scene":
        return _handle_sample(args, config)
    if args.command == "render":
        return _handle_render(args, config)
    if args.command == "generate":
        return _handle_generate(args, config)
    if args.command == "validate-dataset":
        dataset = args.dataset or config.data_dir / "generated" / "mvp"
        payload = validate_dataset(dataset.resolve())
        _print_json(payload)
        return 0 if payload["passed"] else 1
    if args.command == "reproduce":
        sample_dir = _resolve_sample(config, args.sample)
        output = (args.output or sample_dir.with_name(f"{sample_dir.name}_reproduced")).resolve()
        if output.exists():
            raise FileExistsError(f"reproduction output already exists: {output}")
        reproduced = reproduce_sample(
            sample_dir=sample_dir,
            output_dir=output,
            blender_bin=_blender_bin(config, args.blender_bin),
            blender_script=config.root / "blender_scripts" / "compile_scene.py",
        )
        _print_json({"reproduced": reproduced})
        return 0
    if args.command == "write-schema":
        output = args.output.resolve()
        write_json_schema(output)
        _print_json({"schema": output})
        return 0
    raise AssertionError(f"unhandled command: {args.command}")


if __name__ == "__main__":
    raise SystemExit(main())
