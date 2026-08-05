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
- The focused local World-Time suite passes 17 tests; Ruff and mypy pass for changed modules.
- Local CLI import remains unavailable because the pre-existing Mac environment lacks optional
  `gdown`; complete CLI and Blender checks are assigned to the existing KML environment.

## Current paths

- code checkout: `/home/xuboshen/zgw/Video2Scene`
- external task root: `/m2v_intern/xuboshen/zgw/Video2Scene/data/model_evaluation_demo`
- canonical sample: `/m2v_intern/xuboshen/zgw/Video2Scene/data/sceneact_sources/platform_station_dynamic_001`
- replay observation: `/m2v_intern/xuboshen/zgw/Video2Scene/data/worldtime_demo/platform_station_dynamic_001/observations/replay`

## Next actions

1. Validate the feature branch with the full KML test suite.
2. Build the blind replay task and transfer only `public/` to the local ignored `Demo/` tree.
3. Dispatch one restricted subagent and preserve its raw three-file response.
4. Render/score the raw response and no-motion baseline on KML.
5. Generate and visually inspect the final report, then record metrics and artifact paths here.

No model result exists yet. Any earlier oracle-only World-Time output is setup evidence, not the
current blind-submission result.
