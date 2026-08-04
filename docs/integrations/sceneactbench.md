# SceneActBench Compatibility Boundary

SceneActBench is pinned at commit `5b01037454c2ef96c4dea4006b927d27da9d5447` and is
used only as an external execution and evaluation harness. Video2Scene's deterministic Scene
Program remains the sole source of truth for geometry, animation, camera, and dense trajectories.

## Current Gate: Milestone 3 Demo

The repository verifies:

- the submodule revision and MIT license;
- the upstream Dynamic scorer at `src/harness/metrics_t6.py`;
- a runnable SceneAct-specific Blender binary;
- the minimal `mcp`, `numpy`, and `scipy` Python modules;
- disabled BlenderMCP telemetry.
- one pinned official Dynamic oracle sample through the unmodified scorer;
- a deterministic 10-component local static scene and SceneAct-shaped package.
- a deterministic 11-component local Dynamic scene with two rigid movers and dense trajectories;
- a local Dynamic oracle through the same unmodified scorer;
- four World-Time observations plus timeline GT, automatic metrics, and a 2x2 showcase MP4.

Run:

```bash
pip install -e ".[sceneact]"
export DISABLE_TELEMETRY=true
video2scene sceneact doctor
```

The doctor is read-only. It does not download the SceneActBench dataset, launch MCP, call a model,
or import upstream code into the Video2Scene generation process.

## Integration Rules

1. Keep upstream code unmodified and adapt it under `smcb.integrations.sceneactbench`.
2. Store SceneAct datasets and run artifacts below `SCENEACT_DATA_ROOT`, never in Git.
3. Do not expose GT paths, semantic asset names, credentials, or the project checkout to an agent
   workspace.
4. Bind future MCP processes to localhost and disable telemetry by default.
5. Keep private blueprint roles and asset IDs out of public component filenames and future agent
   prompts.

The official oracle gate and its scorer assumptions are recorded in the
[Dynamic contract](sceneactbench_dynamic_contract.md). The local M2 build/export path is recorded
in the [static package contract](sceneactbench_static_package.md). The controlled-mover scene and
temporal-edit loop are recorded in the [World-Time demo contract](worldtime_demo.md). No model or
MCP process is part of this demo gate; model submission is the next track.
