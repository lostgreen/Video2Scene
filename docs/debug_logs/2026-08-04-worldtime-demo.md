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
- Local full CLI/mypy are not authoritative because the Mac environment lacks the repository's
  optional `gdown`, `pydantic`, and type-stub dependencies. No Mac installation is permitted.

## Changed areas

- `src/smcb/dsl/` and `schemas/scene_program_v0.2.schema.json`
- `configs/sceneact/platform_station_dynamic.yaml`
- `src/smcb/integrations/sceneactbench/` and `blender_scripts/compile_scene.py`
- `src/smcb/worldtime/`, CLI commands, unit tests, and integration documentation

## Current hypothesis

The selected-only Blender GLB export will preserve the 11 stable component roots and animation
channels only beneath `mover_vehicle` and `mover_platform`. The canonical centroids should match
the pinned scorer because both implementations average per-mesh vertex centroids over a mover
subtree.

## Next actions

1. On KML, verify Blender 4.5 accepts the selected-only glTF export options.
2. Render the 144-frame dynamic master under `/m2v_intern/xuboshen/zgw/Video2Scene/data/` and
   inspect visibility, mover travel, GLB roots, and a representative frame.
3. Export/validate the local Dynamic package and run its oracle through pinned `metrics_t6.py`.
4. Generate the four observations and showcase, inspect compact metrics and ffprobe metadata, and
   download the final MP4 for review.

Verbose Blender and ffmpeg output must remain in remote log files under
`/home/xuboshen/zgw/log/`; only compact status and failure fingerprints belong here.
