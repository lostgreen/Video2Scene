# Blind Model Evaluation Demo

This protocol turns one existing World-Time observation into a reproducible, leakage-resistant
model evaluation. It evaluates two coupled outputs:

```text
edited RGB observation + known anonymous initial scene
  -> predicted Video Time -> World Time mapping
  -> predicted canonical Scene Program animation
  -> Blender compilation
  -> World-Time metrics + pinned SceneAct Dynamic metrics
  -> baseline/oracle-bracketed visual report
```

The first task is a Core-track case study. Asset IDs, initial transforms, camera, lighting, and
render settings are given. The model must discover temporal edits, moving objects, and canonical
motion. Asset retrieval, camera recovery, and unknown-scene reconstruction are deliberately not
part of this task.

## Leakage boundary

`worldtime build-eval-task` creates physically separate directories:

```text
core_case_001/
  public/
    PROMPT.md
    task.json
    input.mp4
    observation_contact_sheet.jpg
    initial_scene.json
    timeline.schema.json
    scene_program.schema.json
  private/
    timeline.json
    canonical_scene.json
    edit_program.json
    object_id_map.json
    source_manifest.json
```

The public Scene Program uses deterministic anonymous IDs and has an empty `animations` list.
Original object IDs, canonical animation, edit preset, timeline GT, and source paths remain under
`private/`. Give a model only `public/`; write its untouched response to a separate submission
directory.

Build a task from the existing replay observation:

```bash
video2scene worldtime build-eval-task \
  --canonical-sample "$SMCB_DATA_DIR/sceneact_sources/platform_station_dynamic_001" \
  --observation "$SMCB_DATA_DIR/worldtime_demo/platform_station_dynamic_001/observations/replay" \
  --task-id core_case_001 \
  --output "$SMCB_DATA_DIR/model_evaluation_demo/core_case_001"
```

## Submission contract

The model must emit exactly the following semantic outputs:

- `timeline.json`: contiguous piecewise-linear observation-frame to canonical-time mapping
- `scene_program.json`: the public initial scene unchanged except for inferred mover tracks
- `answer.md`: concise evidence, detected edit structure, moving objects, and uncertainty

The task-specific gate validates schemas, sampling, segment count, a non-empty rationale, and that
the model did not rewrite known objects, assets, transforms, camera, lighting, or render settings:

```bash
video2scene worldtime inspect-submission \
  --task "$TASK_DIR" \
  --submission "$TASK_DIR/submissions/subagent_001"
```

An invalid response remains an evaluation result. Do not repair it before scoring or silently
retry with hidden feedback.

## 3D compilation and scoring

Compile both the model prediction and the no-motion public scene with the same asset index and
Blender runtime:

```bash
video2scene render \
  --scene "$SUBMISSION/scene_program.json" \
  --asset-index "$SMCB_ASSET_ROOT/normalized/index.json" \
  --output "$TASK_DIR/artifacts/subagent_001_render"
video2scene render \
  --scene "$TASK_DIR/public/initial_scene.json" \
  --asset-index "$SMCB_ASSET_ROOT/normalized/index.json" \
  --output "$TASK_DIR/artifacts/no_motion_render"
```

Pass each `scene.glb` through the same pinned, unmodified SceneAct Dynamic scorer. Preserve the
JSON outputs as `sceneact_subagent.json`, `sceneact_no_motion.json`, and `sceneact_oracle.json`.
Then produce the report:

```bash
video2scene worldtime evaluate-submission \
  --task "$TASK_DIR" \
  --submission "$SUBMISSION" \
  --sceneact-score "$TASK_DIR/scores/sceneact_subagent.json" \
  --sceneact-baseline "$TASK_DIR/scores/sceneact_no_motion.json" \
  --sceneact-oracle "$TASK_DIR/scores/sceneact_oracle.json" \
  --prediction-video "$TASK_DIR/artifacts/subagent_001_render/input.mp4" \
  --reference-video "$CANONICAL_SAMPLE/input.mp4" \
  --output "$TASK_DIR/report/subagent_001"
```

## Capability interpretation

Every measured signal is bracketed by a trivial baseline and an oracle ceiling:

| Capability | Metric | Baseline | Better |
| --- | --- | --- | --- |
| World-time alignment | normalized MAE | identity timeline | lower |
| Edit segmentation | boundary F1 | identity timeline | higher |
| Playback direction | direction accuracy | identity timeline | higher |
| Playback rate | log-rate MAE | identity timeline | lower |
| Mover discovery | movable recall/count error | no-motion Scene Program | higher/lower |
| 3D trajectory | mean/worst vehicle error | no-motion Scene Program | lower |
| Path geometry | path-shape/direction error | no-motion Scene Program | lower |
| Contract following | submission validator | invalid output | pass required |

`evaluation.json` is the machine-readable record. `report.html` combines the contact sheet,
timeline plot, metric tables, model rationale, predicted canonical render, and revealed reference
render. A model can therefore fail independently at edit understanding, mover discovery, motion
geometry, or structured output instead of receiving one opaque aggregate score.

## Claim boundary

One scene and one replay edit demonstrate that the evaluation machinery works and yield a useful
qualitative case study. They do not estimate generalization. A benchmark claim requires multiple
held-out scenes, asset families, cameras, edit types, seeds, and confidence intervals, with task
generation and submission capture performed before private GT is revealed.
