# World-Time Demo Implementation State

## Goal

Produce one displayable benchmark loop from a real dynamic Blender scene: canonical master,
normal/reverse/freeze/replay observations, timeline GT, automatic mapping scores, and a 2x2 MP4.

## Current evidence

- Scene Program v0.2 compiles an 11-component platform station with two rigid movers.
- KML validation at `f9bfee1`: Ruff, mypy, the full 51-test suite, and CLI help pass.
- The canonical render has 144 frames at 24 fps, 11/11 visible targets, and mover travel of
  approximately 2.60 m and 10.50 m.
- The Dynamic package has two animated roots and two dense 144-frame mover trajectories.
- The unmodified pinned SceneAct oracle reports `mean_vehicle_err=0.0043`,
  `movable_recall=1.0`, `mover_count_err=0.0`, and `direction_error_rate=0.0`.
- All four World-Time oracle mappings have zero error. Identity normalized MAE is 0.5000 for
  reverse, 0.0978 for freeze, and 0.0833 for replay.
- `showcase.mp4` is 1024x1024, 24 fps, 144 frames, and six seconds. Its four labels and quadrants
  passed visual inspection.

## Resolved failures

- Asset-authored Chest clips polluted the first assembled GLB. Imported animation data is now
  cleared before Scene Program tracks are applied.
- Skinned Bouncer/Crab movers disagreed with the scorer's static-mesh centroid representation.
  The demo now uses the rigid Bomb and Cube_Exclamation assets; the package validator rejects
  skinned or animated mover components.

Older Blender, package, and scorer results from those two failures are stale. They remain in
external directories suffixed with `failed_af2c524_asset_animation` and
`failed_9211692_skinned_movers`; no failed data was deleted.

## Artifacts

- canonical source: `/m2v_intern/xuboshen/zgw/Video2Scene/data/sceneact_sources/platform_station_dynamic_001`
- Dynamic package: `/m2v_intern/xuboshen/zgw/Video2Scene/data/sceneact_local/t6l1_local_platform_station_dynamic_001`
- World-Time demo: `/m2v_intern/xuboshen/zgw/Video2Scene/data/worldtime_demo/platform_station_dynamic_001`
- SceneAct oracle: `/m2v_intern/xuboshen/zgw/Video2Scene/artifacts/worldtime_demo/platform_station_dynamic_001/sceneact_oracle.json`
- local review copy: `/Users/lostgreen/Downloads/Video2Scene_WorldTime_Demo.mp4`

Verbose Blender and ffmpeg output remains under `/home/xuboshen/zgw/log/`. The next action is to
merge the validated feature branch and begin the first model-submission baseline.
