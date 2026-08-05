# Video2Scene

Video2Scene implements the Data Collection MVP, a staged SceneActBench compatibility layer, and
the first executable World-Time Canonicalization demo:

```text
official asset pack -> canonical GLBs -> Scene Program v0.1
                    -> Blender headless -> PNG frames + MP4 + GLB + dense GT
                    -> automatic QC -> reproducible dataset samples

dynamic Scene Program v0.2 -> canonical world rollout
                           -> normal / reverse / freeze / replay observations
                           -> Video Time -> World Time GT + automatic scores + 2x2 showcase MP4
```

The compatibility gate builds deterministic static and two-mover dynamic platform stations and
exports them in SceneAct's directory shape. The first World-Time track recovers a canonical world
timeline and a dense video-to-world time mapping from temporally edited observations. Camera
estimation, asset retrieval, physics, rich render passes, and the web viewer remain outside the
current gate.

## Requirements

- Python 3.11+
- Blender 4.5.12 LTS
- ffmpeg
- Git

```bash
cp .env.example .env.local
# Edit machine-specific paths.
make setup
make doctor
make test
make smoke
```

Both `smcb` and `video2scene` resolve to the same CLI. Make targets use
`scripts/run_python.sh`, which loads `.env.local` without asking Make to parse shell syntax.

## SceneActBench compatibility

Initialize the pinned MIT-licensed harness and run the read-only compatibility check:

```bash
scripts/fetch_sceneactbench.sh
pip install -e ".[sceneact]"
export DISABLE_TELEMETRY=true
make sceneact-doctor
```

This check does not download the SceneActBench dataset, launch an agent, or call a model. The
third-party code stays behind `src/smcb/integrations/sceneactbench/`, while Scene Program remains
the only GT source. See [the integration boundary](docs/integrations/sceneactbench.md) and the
[World-Time direction](docs/world_time_direction.md).

Fetch and score only the pinned official Dynamic oracle sample:

```bash
video2scene sceneact fetch-sample \
  --scene-id t6l1_platformer_001 \
  --profile oracle
video2scene sceneact inspect-sample \
  --scene-dir "$SCENEACT_DATA_ROOT/benchmark_t6_final/t6l1_platformer_001"
video2scene sceneact score-oracle \
  --scene-dir "$SCENEACT_DATA_ROOT/benchmark_t6_final/t6l1_platformer_001"
```

The default profile downloads only seven scorer-facing files. Use `--profile full` only when the
reference frames and component library are required. Every fetched scene receives pinned source
metadata and the external dataset's CC-BY-NC-4.0 notice.

Build and export the Milestone 2 static package on a Blender-equipped development machine:

```bash
video2scene sceneact build-static \
  --asset-index "$SMCB_ASSET_ROOT/normalized/index.json" \
  --output "$SMCB_DATA_DIR/sceneact_sources/platform_station_static_001"
video2scene sceneact export-package \
  --sample "$SMCB_DATA_DIR/sceneact_sources/platform_station_static_001" \
  --output "$SMCB_DATA_DIR/sceneact_local/t6l1_local_platform_station_001"
video2scene sceneact validate-package \
  --scene-dir "$SMCB_DATA_DIR/sceneact_local/t6l1_local_platform_station_001"
```

The static package contains 144 reference frames at 24 fps, anonymous component filenames,
compiled static layout centroids, an empty mover map, and one assembled scene GLB. See the
[static package contract](docs/integrations/sceneactbench_static_package.md).

Build the first dynamic canonical master, export its SceneAct-compatible package, then generate
the displayable World-Time demo:

```bash
video2scene sceneact build-dynamic \
  --asset-index "$SMCB_ASSET_ROOT/normalized/index.json" \
  --output "$SMCB_DATA_DIR/sceneact_sources/platform_station_dynamic_001"
video2scene sceneact export-dynamic-package \
  --sample "$SMCB_DATA_DIR/sceneact_sources/platform_station_dynamic_001" \
  --output "$SMCB_DATA_DIR/sceneact_local/t6l1_local_platform_station_dynamic_001"
video2scene sceneact validate-dynamic-package \
  --scene-dir "$SMCB_DATA_DIR/sceneact_local/t6l1_local_platform_station_dynamic_001"
video2scene worldtime build-demo \
  --master-sample "$SMCB_DATA_DIR/sceneact_sources/platform_station_dynamic_001" \
  --output "$SMCB_DATA_DIR/worldtime_demo/platform_station_dynamic_001"
```

The final directory contains four six-second observations, piecewise-linear timeline GT, oracle
and identity-baseline scores, and `showcase.mp4`. See the
[World-Time demo contract](docs/integrations/worldtime_demo.md).

Package one observation as a blind model task, validate an untouched structured response, and
generate a baseline/oracle-bracketed evaluation report:

```bash
video2scene worldtime build-eval-task \
  --canonical-sample "$SMCB_DATA_DIR/sceneact_sources/platform_station_dynamic_001" \
  --observation "$SMCB_DATA_DIR/worldtime_demo/platform_station_dynamic_001/observations/replay" \
  --task-id blind_replay_001 \
  --output "$SMCB_DATA_DIR/model_evaluation_demo/blind_replay_001"
video2scene worldtime inspect-submission \
  --task "$SMCB_DATA_DIR/model_evaluation_demo/blind_replay_001" \
  --submission "$SUBMISSION_DIR"
```

The public task and private GT are physically separated. The final report diagnoses timeline
recovery, edit boundaries, playback direction/rate, mover discovery, and 3D trajectory quality.
See the [blind model evaluation protocol](docs/integrations/model_evaluation_demo.md).

## External data

Raw assets, normalized assets, previews, frames, and generated datasets are never tracked by
Git. Configure one external root:

```bash
export SMCB_PROJECT_DATA_ROOT=/m2v_intern/xuboshen/zgw/Video2Scene
export SMCB_ASSET_ROOT=/m2v_intern/xuboshen/zgw/Video2Scene/assets
export SMCB_DATA_DIR=/m2v_intern/xuboshen/zgw/Video2Scene/data
export SMCB_ARTIFACTS_DIR=/m2v_intern/xuboshen/zgw/Video2Scene/artifacts
```

On the KML development machine the code checkout is separate at
`/home/xuboshen/zgw/Video2Scene`.

## Assets

The tracked manifest points to Quaternius' official Ultimate Platformer Pack. The source is
CC0 and the upstream Drive folder contains the Blend, FBX, glTF, and OBJ variants. Downloaded
files remain untouched. Acquisition fetches the compiler-facing `.gltf/.bin` payload plus the
upstream license, while `download_report.json` records per-file failures and
`source_inventory.json` records the available tree's aggregate SHA-256.
The MVP manifest caps acquisition at 30 eligible rigid glTF assets and enforces a 120-second
per-file network deadline; partial files remain resumable.

```bash
make assets                 # fetch, inventory, normalize the first 30 assets
make asset-previews         # ensure six views and contact sheets exist
video2scene assets doctor
```

Each normalized asset produces `<asset_id>.glb`, `<asset_id>.json`, six PNG views, and one
contact sheet. `normalized/index.json` is the only asset lookup used by the compiler.
The MVP manifest excludes `Character/**`: those rigged files carry Blender editor custom-shape
helpers that are outside the rigid-object scope. The remaining 108 glTF assets cover the first
30-asset target without that ambiguity.

## Dataset workflow

Run the levels in order:

```bash
make scene-smoke            # Level 1: one 128x128 sample
make dataset-smoke          # Level 2: four 128x128 samples, one per template
make dataset-mvp            # Level 3: 100 512x512 samples
make dataset-check
```

The direct production command is:

```bash
video2scene generate \
  --config configs/dataset/mvp.yaml \
  --num-samples 100 \
  --seed 42
```

Generation is resumable. A failed attempt remains below `_attempts/` with `qc.json` and
bounded logs; only passing attempts are renamed to `sample_XXXXXX/`. Attempt directories carry
the generator Git commit prefix, so fixed compiler code can replay the same deterministic seeds
without deleting stale evidence.

## Sample contract

```text
sample_000001/
  scene.json
  metadata.json
  qc.json
  input.mp4
  frames/frame_0001.png ...
  scene.blend
  scene.glb
  gt/camera.json
  gt/trajectories.json
  gt/visibility.json
  gt/candidates.json
  debug/preview.png
  debug/blender.log
  debug/ffmpeg.log
```

`scene.json` is the source of truth. Coordinates are right-handed, Z-up, -Y-forward, meters,
with quaternions serialized as `xyzw`. The general sampler supports `static_orbit`,
`moving_object`, `moving_camera`, and `parent_motion`; the SceneAct integration adds the explicit
`platform_station_static` and `platform_station_dynamic` blueprints. Animation interpolation is
linear.

Re-render a sample from its saved scene and recorded asset index:

```bash
video2scene reproduce sample_000001
```

The command writes a sibling `sample_000001_reproduced/` and refuses to overwrite an existing
reproduction.

## Repository layout

- `assets/manifests/`: tracked upstream declarations; payloads are ignored
- `configs/dataset/`: Level 1, smoke, and MVP configurations
- `schemas/`: generated Scene Program JSON Schema
- `src/smcb/assets/`: acquisition, inventory, normalization orchestration
- `src/smcb/dsl/`: Scene Program v0.1/v0.2 typed contracts
- `src/smcb/generation/`: deterministic sampler and QC
- `src/smcb/integrations/sceneactbench/`: pinned harness configuration and compatibility checks
- `src/smcb/worldtime/`: temporal-edit DSL, observation builder, and mapping metrics
- `src/smcb/blender/`: Blender subprocess boundary
- `blender_scripts/`: dependency-free scripts executed by Blender
- `src/smcb/storage/`: sample construction, resume, reproduce, validation
