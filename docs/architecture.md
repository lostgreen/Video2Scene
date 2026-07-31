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
