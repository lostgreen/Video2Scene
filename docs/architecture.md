# Architecture

The target architecture and long-term implementation order are defined in
[`PLAN.md`](../PLAN.md). Data Collection MVP v0.1 narrows the active pipeline to:

```text
Source manifest -> raw inventory -> canonical asset index
                -> deterministic Scene Program
                -> Blender compiler + RGB render + dense GT
                -> ffmpeg -> QC -> accepted sample
```

`scene.json` is the source of truth. Blender scripts intentionally use only Blender's bundled
Python standard library and `bpy`; orchestration and validation stay in the regular Python
environment. Generated attempts are immutable and promoted by directory rename only after QC.

Large state is separated from the Git checkout with `SMCB_PROJECT_DATA_ROOT`. The KML layout is
documented in [`../assets/README.md`](../assets/README.md).

SceneActBench is an isolated downstream compatibility layer:

```text
Scene Program -> deterministic Blender outputs -> SceneAct-compatible package
                                                   -> pinned external harness/scorer

master rollout -> temporal edit map phi(t) -> World-Time observations and exact mapping GT
```

The compatibility layer never generates GT and does not alter the current compiler. See
[`integrations/sceneactbench.md`](integrations/sceneactbench.md) for its pinned boundary and
[`world_time_direction.md`](world_time_direction.md) for the benchmark direction built above it.
