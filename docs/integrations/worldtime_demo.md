# World-Time Demo Contract

The first displayable demo proves one narrow benchmark loop without a model dependency:

```text
one canonical animated world
  -> normal / reverse / freeze / replay observations
  -> piecewise-linear Video Time -> World Time ground truth
  -> oracle and identity-baseline metrics
  -> labeled 2x2 showcase MP4
```

## Canonical master

`sceneact build-dynamic` compiles `configs/sceneact/platform_station_dynamic.yaml` as Scene Program
v0.2. The rollout is fixed at 144 frames, 24 fps, a fixed camera, and exactly two translation
movers. Its GLB export contains the component hierarchy and mover animation; camera, lights, and
render-only ground are excluded from the scored scene.

The command refuses an existing output directory and requires every target to remain visible. It
also checks that both mover centroids have 144 samples and travel at least one meter.

## Temporal edits

`worldtime build-demo` creates four six-second observations from the canonical PNG sequence. The
first prototype deliberately preserves observation length:

| Preset | Frame mapping |
| --- | --- |
| `normal` | master 0 through 143 |
| `reverse` | master 143 through 0 |
| `freeze` | 0-47, hold 47 for 24 frames, then 48-119 |
| `replay` | 0-71, replay 48-71, then 72-119 |

Each observation contains `input.mp4`, `preview.png`, `edit_program.json`, `timeline.json`, a dense
`frame_to_world_time.json`, and `scores.json`. Frame PNGs are hard-linked when the filesystem
allows it so the edit set does not multiply storage.

## Metrics

`timeline.json` is the submission contract for the first track. It represents the mapping as
contiguous piecewise-linear segments and covers every video frame exactly once. The independent
World-Time evaluator reports:

- mean, median, and p90 source-time error in seconds
- mean error normalized by the six-second canonical duration
- temporal breakpoint precision, recall, and F1 with a two-frame default tolerance
- playback direction accuracy away from ground-truth breakpoints
- log playback-rate error

The demo records a perfect oracle and an identity baseline for every edit. These metrics do not
replace or modify SceneActBench's 3D scene metrics.

## Output layout

```text
worldtime_demo/platform_station_dynamic_001/
  master.mp4
  showcase.mp4
  showcase_layout.json
  demo_report.json
  observations/
    normal/{input.mp4,timeline.json,edit_program.json,scores.json,...}
    reverse/{input.mp4,timeline.json,edit_program.json,scores.json,...}
    freeze/{input.mp4,timeline.json,edit_program.json,scores.json,...}
    replay/{input.mp4,timeline.json,edit_program.json,scores.json,...}
```

`showcase.mp4` arranges normal and reverse on the top row, freeze and replay on the bottom row. If
the installed ffmpeg lacks `drawtext`, generation falls back to the same stable 2x2 layout without
labels.

Score an external timeline independently:

```bash
video2scene worldtime score \
  --ground-truth observations/replay/timeline.json \
  --prediction prediction/timeline.json
```
