# Video2Scene

Video2Scene currently implements the Data Collection MVP for SceneMotionCodeBench:

```text
official asset pack -> canonical GLBs -> Scene Program v0.1
                    -> Blender headless -> PNG frames + MP4 + GLB + dense GT
                    -> automatic QC -> reproducible dataset samples
```

The next staged milestone adds SceneActBench only as a pinned execution/evaluation harness. The
long-term task is World-Time Canonicalization: recovering a canonical world timeline and a dense
video-to-world time mapping from temporally edited observations. Camera estimation, asset
retrieval, physics, rich render passes, and the web viewer remain outside the current gate.

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
with quaternions serialized as `xyzw`. Supported templates are `static_orbit`,
`moving_object`, `moving_camera`, and `parent_motion`; animation interpolation is linear.

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
- `src/smcb/dsl/`: Scene Program v0.1 typed contract
- `src/smcb/generation/`: deterministic sampler and QC
- `src/smcb/integrations/sceneactbench/`: pinned harness configuration and compatibility checks
- `src/smcb/blender/`: Blender subprocess boundary
- `blender_scripts/`: dependency-free scripts executed by Blender
- `src/smcb/storage/`: sample construction, resume, reproduce, validation
