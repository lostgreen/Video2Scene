# SceneActBench Static Package Contract

Milestone 2 produces one deterministic, multi-asset static scene before introducing movers,
models, or MCP. Scene Program v0.1 remains the only source of truth. The integration blueprint
resolves normalized assets by their upstream source stem, then records the exact resolved asset
IDs and hashes in private build metadata.

## Platform Station Blueprint

`configs/sceneact/platform_station_static.yaml` defines 10 visible instances:

| Role | Normalized source |
| --- | --- |
| two supports | `Bridge_Modular_Center`, `Bridge_Modular` |
| connector | `Bridge_Small` |
| landmarks | `Door`, `Goal_Flag` |
| props | `Cannon`, `Chest` |
| future mover placeholder | `Bouncer` |
| barriers | `Fence_Middle`, `Fence_Corner` |

Positions, scale, relations, fixed camera, lighting, 24 fps, and 144 frames are explicit. The
layout spans X, Y, and Z rather than using the generic sampler's row arrangement. Scene Program
v0.1 now allows up to 20 objects without changing existing field semantics or old template reads.

## Two-Stage Output

`sceneact build-static` writes a private source sample with the Scene Program, Blender file,
assembled GLB, one physically rendered frame reused across the 144-frame static sequence, MP4,
dense compiler GT, visibility metrics, and `sceneact_build.json`. Every target must be visible in
all frames and exceed the configured projected-area threshold.

`sceneact export-package` writes:

```text
t6l1_local_platform_station_001/
  components/asset_0001.glb ... asset_0010.glb
  reference/frame_0001.png ... frame_0144.png
  reference.mp4
  gt/scene.glb
  gt/trajectory.json
  camera.json
  layout_gt.json
  meta.json
  preview.png
```

Component filenames are anonymous. `gt/trajectory.json` is `{}` because M2 has no mover.
`layout_gt.json` stores the compiled world-space mesh centroid for each stable top-level object,
matching the representation consumed by the pinned upstream layout scorer. `camera.json` follows
the official fixed-camera keys (`name`, `type`, `location`, `rotation_euler_deg`, `lens_mm`, and
`matrix_world`).

`meta.json` is private evaluation metadata: it includes semantic roles, source names, asset IDs,
and component hashes. It must not be copied into a future agent workspace or prompt.

## Validation

```bash
video2scene sceneact validate-package --scene-dir <package>
```

The validator checks the exact 24 fps/144-frame gate, 6-10 component cardinality, anonymous and
contiguous component names, no symlink payloads, GLB/PNG/MP4 signatures, empty static mover map,
layout/component agreement, official camera fields, and all recorded component SHA-256 values.
It does not claim Dynamic scorer readiness. Milestone 3 adds controlled animation, dense mover
trajectories, and oracle/perturbation scoring to this same scene.
