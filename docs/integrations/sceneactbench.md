# SceneActBench Compatibility Boundary

SceneActBench is pinned at commit `5b01037454c2ef96c4dea4006b927d27da9d5447` and is
used only as an external execution and evaluation harness. Video2Scene's deterministic Scene
Program remains the sole source of truth for geometry, animation, camera, and dense trajectories.

## Current Gate: Milestone 0

The repository currently verifies:

- the submodule revision and MIT license;
- the upstream Dynamic scorer at `src/harness/metrics_t6.py`;
- a runnable SceneAct-specific Blender binary;
- the minimal `mcp`, `numpy`, and `scipy` Python modules;
- disabled BlenderMCP telemetry.

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
5. Verify an official Dynamic oracle sample before exporting local packages or changing the
   existing scene compiler.

The next compatibility gate is one official Dynamic sample plus an oracle score through the
pinned `evaluate_t6(agent_glb, sample_dir)` entry point. Dataset acquisition must remain scoped to
one scene until that contract is documented and reproducible.
