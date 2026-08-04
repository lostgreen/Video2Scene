# World-Time Demo Implementation State

## Goal

Produce one displayable benchmark loop from a real dynamic Blender scene: canonical master,
normal/reverse/freeze/replay observations, timeline GT, automatic mapping scores, and a 2x2 MP4.

## Current evidence

- Scene Program v0.2 and the deterministic two-mover platform-station blueprint are implemented.
- Dynamic render/package gates require 144 frames at 24 fps, two visible movers, and non-trivial
  centroid motion.
- The local package validator checks exact mover trajectories and animated GLB roots before the
  unmodified pinned SceneAct scorer runs.
- The World-Time evaluator covers mapping error, breakpoints, direction, and playback rate.
- Current local check: Ruff passes and 36 focused tests pass.
- KML check at `af2c524`: Ruff, mypy, full 51-test suite, and CLI help pass.
- The first canonical render passed its gate with 144 frames, 11/11 visible targets, and mover
  travel of approximately 2.63 m and 10.50 m.
- Local full CLI/mypy are not authoritative because the Mac environment lacks the repository's
  optional `gdown`, `pydantic`, and type-stub dependencies. No Mac installation is permitted.

## Changed areas

- `src/smcb/dsl/` and `schemas/scene_program_v0.2.schema.json`
- `configs/sceneact/platform_station_dynamic.yaml`
- `src/smcb/integrations/sceneactbench/` and `blender_scripts/compile_scene.py`
- `src/smcb/worldtime/`, CLI commands, unit tests, and integration documentation

## Latest failure fingerprint

The first Dynamic package export was rejected with
`animated_root_mismatch:cargo_chest,mover_platform,mover_vehicle:mover_platform,mover_vehicle`.
The normalized Chest GLB contains two asset-authored clips targeting three nodes. Those inherited
actions entered the assembled GLB when animation export was enabled. The current fix clears
imported object/data animation before Scene Program tracks are applied; the canonical centroids
and rendered appearance should remain unchanged.

After stripping those actions, the Dynamic package validator passed, but the pinned scorer oracle
reported `mean_vehicle_err=0.2287` and `scale_error=0.5229`. Both movers used skinned assets
(`Bouncer` and `Crab`). Blender GT applies their armature deformation while `metrics_t6.py`
samples node transforms and static mesh centroids without skin joint matrices. This
representation mismatch is current; the earlier asset-animation failure is resolved.

## Next actions

1. Re-render with the visually distinct rigid `Bomb` and `Cube_Exclamation` assets as movers;
   verify the only animated GLB roots are the two declared movers.
2. Export/validate the local Dynamic package and require a near-zero oracle through pinned
   `metrics_t6.py`.
3. Generate the four observations and showcase, inspect compact metrics and ffprobe metadata, and
   download the final MP4 for review.

Verbose Blender and ffmpeg output must remain in remote log files under
`/home/xuboshen/zgw/log/`; only compact status and failure fingerprints belong here.
