# Third-Party Notices

Video2Scene includes SceneActBench as a pinned Git submodule for compatibility testing and as
an external execution/evaluation harness. Video2Scene does not use SceneActBench as a source of
ground truth.

## SceneActBench

- Repository: https://github.com/Feinaldo2/SceneActBench
- Pinned commit: `5b01037454c2ef96c4dea4006b927d27da9d5447`
- Copyright: 2026 SceneActBench Authors (Tencent Hunyuan)
- License: MIT; see `third_party/sceneactbench/LICENSE`

The SceneActBench repository bundles BlenderMCP, also distributed under the MIT License. Its
source and notices remain within `third_party/sceneactbench/blender-mcp/`.

SceneActBench datasets are separate artifacts and are not included in this repository. Any
future downloader must preserve the dataset's own attribution and non-commercial license terms.
