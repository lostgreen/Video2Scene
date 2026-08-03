# Pinned SceneActBench Dynamic Contract

This contract was inspected against:

- harness commit `5b01037454c2ef96c4dea4006b927d27da9d5447`;
- dataset revision `128b767d15ffd73e9175773ac7a626846c0b68db`;
- official scene `t6l1_platformer_001`.

## Scoring Entry Point

The unmodified entry point is:

```python
evaluate_t6(agent_glb: str, sample_dir: str) -> dict
```

It is defined in `src/harness/metrics_t6.py`. The harness supplies the run artifact
`agent_scene.glb`; if an agent does not export a usable file, upstream `run.py` attempts a
whole-scene GLB export with animations enabled.

The scorer reads:

```text
<sample_dir>/meta.json
<sample_dir>/layout_gt.json
<sample_dir>/gt/trajectory.json
<sample_dir>/gt/gt_scene.glb
```

The official platformer sample has 144 frames at 24 fps. The GT scene GLB is 414,852 bytes and
the complete official sample is 50,824,075 bytes. The default `oracle` fetch profile downloads
only seven scorer/inspection files totaling about 1.1 MB; `full` must be requested explicitly.

## Trajectory Contract

`gt/trajectory.json` is a JSON object keyed by mover name. A scorer-visible mover value is a list
of records containing:

```json
{"f": 1, "loc": [0.0, 0.0, 0.0]}
```

Frames are 1-based. `loc` is already in Blender Z-up coordinates. Entries without both `f` and
`loc` are ignored; the platformer sample's `coins` metadata is therefore not a mover trajectory.
Sparse trajectories are forward-filled by the scorer, but Video2Scene compatibility packages
must export one point per frame.

Agent trajectories are extracted from animation-driven GLB nodes. Driven descendants are grouped
under their top-level scene object, sampled at `frame / fps`, converted from glTF +Y-up to Blender
Z-up, and matched to GT movers with Hungarian assignment.

## Layout Contract

`layout_gt.json` contains `objects` (with `static_objects` accepted as a fallback). Each object
uses `location` or `loc`; the official platformer object also includes `name`, `type`, `scale`, and
`rotZ_deg`. Dynamic scoring uses only static top-level centroids and bidirectional Chamfer distance,
not semantic asset classes. The platformer sample contains 28 static layout objects.

## Score Output

The primary metric is `worst_vehicle_err` and lower is better. Top-level diagnostics include:

```text
mean_vehicle_err, movable_recall, mover_count_err,
direction_error_rate, path_shape_err, heading_err,
scale_error, size_error, mover_size_err, layout_err
```

Nested `trajectory`, `semantic`, `layout`, `size`, and `mover_size` objects preserve detailed
matching diagnostics. SceneActBench run directories store `score.json`, `steps.json`, `task.json`,
and `agent_scene.glb`.

### Observed Official Oracle Baseline

On KML, using the official `gt/gt_scene.glb` as its own prediction produced:

```text
worst_vehicle_err   0.0029    movable_recall       1.0
mean_vehicle_err    0.0029    direction_error_rate 0.0
path_shape_err      0.0037    heading_err           0.0
scale_error         0.0010    size_error            0.0
mover_size_err      0.0       layout_err            0.0294
mover_count_err     3.0
```

The non-zero mover count is an upstream baseline property, not a wrapper error. The official GLB
has four animation-driven top-level roots (`Hero`, `Coin_0`, `Coin_1`, `Coin_2`), while
`trajectory.json` exposes only `Hero` as a mover because coin entries lack `f` and `loc`.
Consequently the pinned scorer reports `n_agent=4`, `n_gt=1`, and `mover_count_err=3.0`. Local
packages must be compared with this recorded baseline; the compatibility layer must not patch the
upstream scorer to hide it.

## Reproducible Gate

```bash
video2scene sceneact fetch-sample \
  --scene-id t6l1_platformer_001 \
  --profile oracle
video2scene sceneact inspect-sample --scene-dir <sample-dir>
video2scene sceneact score-oracle --scene-dir <sample-dir>
```

Each fetched sample contains `LICENSE_DATASET.txt` and `source.json`. Dataset files are external,
CC-BY-NC-4.0 artifacts and must never be committed. The oracle gate must pass before local package
export or task generation is implemented.
