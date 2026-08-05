# Blind Model Evaluation Demo State

## Goal

Run one untouched subagent response through a complete, displayable evaluation loop: blind public
input, structured timeline and Scene Program output, contract validation, Blender compilation,
World-Time scoring, pinned SceneAct scoring, baseline/oracle comparison, and visual report.

## Current evidence

- The task packager separates anonymous public input from timeline, scene, edit, ID-map, and source
  GT under `private/`; task IDs and public assumptions are neutral with respect to the hidden edit.
- The submission gate allows animation-only edits and rejects changes to known scene fields.
- Reports compare identity/subagent/oracle timelines and no-motion/subagent/oracle 3D motion.
- One sealed subagent received only `public/` and produced an untouched three-file submission.
- Scene Program and rationale pass the contract. The timeline is primary-invalid because it uses
  exclusive segment ends (`72/96/144`) where the schema requires inclusive ends (`71/95/143`).
- The non-scoring audit finds exact internal boundaries (`boundary_f1=1.0`) and exact world starts;
  this identifies a systematic endpoint convention error without repairing or scoring the file.
- The subagent found both movers. Pinned SceneAct reports `movable_recall=1.0`,
  `mover_count_err=0.0`, `direction_error_rate=0.0`, `mean_vehicle_err=0.0184`, and
  `path_shape_err=0.0200`. No-motion mean error is `1.0`; oracle mean error is `0.0043`.
- The focused local World-Time suite passes 18 tests; changed-module Ruff and mypy checks pass.
- KML validation at `8392898` passed Ruff, formatting, mypy over 45 modules, and all 56 tests;
  later report diagnostics pass focused KML tests through `e87e021`.
- Local CLI import remains unavailable because the pre-existing Mac environment lacks optional
  `gdown`; complete CLI and Blender checks are assigned to the existing KML environment.

## Current paths

- code checkout: `/home/xuboshen/zgw/Video2Scene`
- external task root: `/m2v_intern/xuboshen/zgw/Video2Scene/data/model_evaluation_demo`
- canonical sample: `/m2v_intern/xuboshen/zgw/Video2Scene/data/sceneact_sources/platform_station_dynamic_001`
- replay observation: `/m2v_intern/xuboshen/zgw/Video2Scene/data/worldtime_demo/platform_station_dynamic_001/observations/replay`
- evaluation task: `/m2v_intern/xuboshen/zgw/Video2Scene/data/model_evaluation_demo/core_case_001`
- final report: `/m2v_intern/xuboshen/zgw/Video2Scene/data/model_evaluation_demo/core_case_001/report/subagent_001`
- local ignored demo: `/Users/lostgreen/Desktop/AIM3Lab/AgenticMLLM/Video2Scene/Demo/core_case_001`

## Next actions

1. Run the final full KML suite after the invalid-timeline diagnostic additions.
2. Merge the feature branch into `main`, push, and fast-forward the KML checkout to `main`.
3. Keep `Demo/` ignored and preserve all raw submissions, scores, renders, and reports externally.

The first task ID `blind_replay_001` leaked the hidden edit label and is invalid. It is preserved as
`blind_replay_001_invalid_task_id_leak_6aceaea`; only `core_case_001` is current. The first
no-motion render omitted `.env.local` and failed on `libEGL.so.1`; its directory is preserved as
`no_motion_render_failed_missing_env_8392898`. Earlier report revisions are stale and preserved
beside the final report. Browser visual navigation to local `file://` output was blocked by policy;
media existence, HTML references, video metadata, and a downloaded 12-frame comparison image were
checked instead.
