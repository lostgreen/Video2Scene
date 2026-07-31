# Video2SceneMotionCode / SceneMotionCodeBench

> 面向 Coding Agent 的项目仓库规划文档
>
> 目标：在 Linux 服务器上完成资产规范化、场景程序采样、Blender 无界面渲染、模型推理、自动评测，并通过 Web 页面远程查看输入视频、GT 场景、预测场景和评测结果。

---

## 1. 项目定位

### 1.1 核心任务

给定：

1. 一段由 3D 场景渲染得到的视频；
2. 一个固定候选资产库；
3. 一个受约束的场景程序 schema；

模型一次性输出可执行的 3D 场景与动画程序：

- 资产选择；
- 对象实例数量与 identity；
- 位置、旋转、缩放；
- 相机类型、内参和轨迹；
- 灯光；
- 动画关键帧；
- 简单父子关系或约束。

程序经过固定编译器转换为 Blender 场景和可选的 Three.js 场景，再通过渲染结果和结构化指标进行评测。

### 1.2 第一阶段范围

首版只支持：

- 已知资产库；
- 刚体对象；
- 3–8 个对象；
- 1–3 个运动对象；
- 3–6 秒视频；
- 正交或透视相机；
- `step / linear / bezier` 插值；
- `parent / look_at / track_to` 三类简单关系；
- Blender headless 渲染；
- JSON DSL 输出；
- Three.js 网页预览。

暂不支持：

- mesh 生成；
- 骨骼级动作恢复；
- 布料、流体、破碎；
- 复杂物理参数恢复；
- 任意 Python 代码输出；
- 任意互联网视频。

### 1.3 项目价值

该任务把以下能力放在一个可诊断的 benchmark 中：

- 视频细节理解；
- 多对象持续跟踪；
- 资产视觉匹配；
- 3D 空间布局恢复；
- 相机运动与物体运动分解；
- 时间程序归纳；
- 可执行、可编辑代码生成。

---

## 2. 总体系统架构

```text
Asset Packs
   │
   ▼
Asset Normalizer
   │
   ├── normalized_assets/*.glb
   ├── metadata.json
   └── thumbnails / turntables
   │
   ▼
Scene Program Sampler
   │
   └── scene_program.json
   │
   ▼
Blender Compiler + Headless Renderer
   │
   ├── input_video.mp4
   ├── scene.blend
   ├── scene.glb
   ├── RGB / masks / depth / normals / flow
   └── object & camera trajectories
   │
   ├─────────────────────────────┐
   ▼                             ▼
Model Inference              Benchmark Index
   │                             │
   └── predicted_scene.json      │
   │                             │
   ▼                             │
Schema Validator                 │
   │                             │
   ▼                             │
Prediction Compiler              │
   │                             │
   └── predicted.glb / video     │
   │                             │
   ▼                             │
Evaluator                        │
   │                             │
   └── metrics.json              │
   │                             │
   └──────────────┬──────────────┘
                  ▼
           FastAPI + Three.js
                  │
                  ▼
      Local Browser via SSH Tunnel
```

---

## 3. 推荐仓库结构

```text
scene-motion-code-bench/
├── README.md
├── PLAN.md
├── LICENSE
├── pyproject.toml
├── uv.lock                         # 或 requirements/，二选一
├── .python-version
├── .gitignore
├── .pre-commit-config.yaml
├── Makefile
├── docker/
│   ├── Dockerfile.base
│   ├── Dockerfile.blender
│   ├── Dockerfile.web
│   └── compose.yaml
├── configs/
│   ├── assets/
│   │   ├── normalization.yaml
│   │   └── asset_sources.example.yaml
│   ├── generation/
│   │   ├── tier1_scene_camera.yaml
│   │   ├── tier2_rigid_motion.yaml
│   │   └── tier3_relations.yaml
│   ├── rendering/
│   │   ├── eevee_fast.yaml
│   │   └── cycles_eval.yaml
│   ├── evaluation/
│   │   └── default.yaml
│   └── server/
│       └── local.yaml
├── schemas/
│   ├── scene_program.schema.json
│   ├── asset_metadata.schema.json
│   ├── sample_manifest.schema.json
│   └── metrics.schema.json
├── src/
│   └── smcb/
│       ├── __init__.py
│       ├── cli.py
│       ├── common/
│       │   ├── config.py
│       │   ├── logging.py
│       │   ├── paths.py
│       │   ├── ids.py
│       │   └── exceptions.py
│       ├── assets/
│       │   ├── importer.py
│       │   ├── normalizer.py
│       │   ├── metadata.py
│       │   ├── thumbnails.py
│       │   ├── similarity.py
│       │   └── validator.py
│       ├── dsl/
│       │   ├── models.py
│       │   ├── schema.py
│       │   ├── validation.py
│       │   ├── canonicalize.py
│       │   └── symmetry.py
│       ├── generation/
│       │   ├── sampler.py
│       │   ├── templates.py
│       │   ├── placement.py
│       │   ├── motion.py
│       │   ├── camera.py
│       │   ├── lighting.py
│       │   ├── distractors.py
│       │   └── quality_checks.py
│       ├── blender/
│       │   ├── bootstrap.py
│       │   ├── compiler.py
│       │   ├── import_assets.py
│       │   ├── transforms.py
│       │   ├── animation.py
│       │   ├── camera.py
│       │   ├── lighting.py
│       │   ├── render.py
│       │   ├── passes.py
│       │   └── export_gltf.py
│       ├── inference/
│       │   ├── base.py
│       │   ├── prompt_builder.py
│       │   ├── video_sampling.py
│       │   ├── asset_context.py
│       │   ├── providers/
│       │   │   └── mock.py
│       │   └── runner.py
│       ├── evaluation/
│       │   ├── matching.py
│       │   ├── executable.py
│       │   ├── assets.py
│       │   ├── pose.py
│       │   ├── camera.py
│       │   ├── motion.py
│       │   ├── relations.py
│       │   ├── render_metrics.py
│       │   ├── editability.py
│       │   ├── aggregate.py
│       │   └── report.py
│       ├── storage/
│       │   ├── manifests.py
│       │   ├── dataset_index.py
│       │   └── cache.py
│       └── server/
│           ├── app.py
│           ├── api.py
│           ├── models.py
│           ├── jobs.py
│           └── static.py
├── blender_scripts/
│   ├── normalize_asset.py
│   ├── render_sample.py
│   ├── compile_prediction.py
│   └── export_scene.py
├── web/
│   ├── package.json
│   ├── vite.config.ts
│   ├── tsconfig.json
│   └── src/
│       ├── main.tsx
│       ├── api/
│       ├── components/
│       │   ├── VideoPanel.tsx
│       │   ├── SceneViewer.tsx
│       │   ├── Timeline.tsx
│       │   ├── ObjectInspector.tsx
│       │   ├── MetricsPanel.tsx
│       │   └── JsonViewer.tsx
│       ├── scene/
│       │   ├── gltfLoader.ts
│       │   ├── dslCompiler.ts
│       │   ├── coordinateSystem.ts
│       │   └── overlays.ts
│       └── pages/
│           ├── SamplesPage.tsx
│           └── SampleDetailPage.tsx
├── scripts/
│   ├── bootstrap_linux.sh
│   ├── download_assets.sh
│   ├── normalize_assets.sh
│   ├── generate_dataset.sh
│   ├── run_inference.sh
│   ├── evaluate_run.sh
│   ├── launch_viewer.sh
│   └── smoke_test.sh
├── tests/
│   ├── unit/
│   ├── integration/
│   ├── blender/
│   ├── golden/
│   └── web/
├── examples/
│   ├── minimal_scene.json
│   ├── moving_platform.json
│   └── parent_child_motion.json
├── docs/
│   ├── architecture.md
│   ├── dsl.md
│   ├── asset_pipeline.md
│   ├── generation.md
│   ├── evaluation.md
│   ├── web_viewer.md
│   └── deployment.md
├── data/                              # 默认 gitignore
│   ├── raw_assets/
│   ├── normalized_assets/
│   ├── datasets/
│   ├── runs/
│   └── cache/
└── artifacts/                         # 默认 gitignore
    ├── reports/
    └── demos/
```

---

## 4. 核心数据契约

## 4.1 坐标系约定

从第一天固定，不允许模块自行解释：

```json
{
  "coordinate_system": {
    "handedness": "right",
    "up": "Z",
    "forward": "-Y"
  },
  "distance_unit": "meter",
  "time_unit": "second",
  "rotation_representation": "quaternion_xyzw"
}
```

规则：

- DSL 和评测内部统一使用右手、Z-up；
- Blender 编译器直接使用该约定；
- Three.js 前端通过唯一的坐标转换模块适配 Y-up；
- 禁止在业务代码中散落轴变换；
- 所有旋转进入评测前归一化四元数。

## 4.2 Scene Program 最小结构

```json
{
  "schema_version": "0.1.0",
  "sample_id": "sample_000001",
  "timeline": {
    "duration": 4.0,
    "fps": 24
  },
  "coordinate_system": {
    "handedness": "right",
    "up": "Z",
    "forward": "-Y"
  },
  "objects": [
    {
      "id": "object_001",
      "asset_id": "asset_00017",
      "parent_id": null,
      "transform": {
        "position": [0.0, 0.0, 0.0],
        "rotation": [0.0, 0.0, 0.0, 1.0],
        "scale": [1.0, 1.0, 1.0]
      }
    }
  ],
  "camera": {
    "id": "camera_001",
    "type": "perspective",
    "fov_y_degrees": 50.0,
    "transform": {
      "position": [6.0, -6.0, 4.0],
      "rotation": [0.0, 0.0, 0.0, 1.0]
    }
  },
  "lights": [],
  "constraints": [],
  "animation_curves": []
}
```

## 4.3 动画曲线

```json
{
  "target_id": "object_001",
  "property": "position",
  "space": "world",
  "interpolation": "linear",
  "keyframes": [
    {"time": 0.0, "value": [-2.0, 0.0, 1.0]},
    {"time": 3.0, "value": [2.0, 0.0, 1.0]}
  ]
}
```

限制：

- 属性白名单：`position / rotation / scale / visibility`；
- 相机额外支持：`fov_y_degrees / ortho_scale`；
- 首版不允许逐帧任意矩阵；
- 关键帧数量设置上限；
- 时间必须位于 timeline 范围；
- 引用对象必须存在。

## 4.4 资产 metadata

```json
{
  "asset_id": "asset_00017",
  "source": "quaternius",
  "license": "CC0",
  "category": "platform",
  "dimensions": [4.0, 2.0, 0.5],
  "canonical_scale": 1.0,
  "ground_offset": 0.0,
  "forward_axis": "-Y",
  "up_axis": "Z",
  "movable": true,
  "support_surfaces": [
    {
      "id": "top",
      "center": [0.0, 0.0, 0.25],
      "size": [4.0, 2.0]
    }
  ],
  "symmetries": [],
  "animation_clips": []
}
```

## 4.5 单样本目录

```text
sample_000001/
├── manifest.json
├── input_video.mp4
├── gt/
│   ├── scene_program.json
│   ├── scene.blend
│   ├── scene.glb
│   ├── camera_trajectory.json
│   ├── object_trajectories.json
│   ├── rgb/
│   ├── masks/
│   ├── depth/
│   ├── normals/
│   └── flow/
├── candidates/
│   ├── asset_ids.json
│   ├── contact_sheet.png
│   └── thumbnails/
└── quality.json
```

单次实验输出：

```text
runs/<run_id>/
├── run_config.yaml
├── predictions/
│   └── sample_000001.json
├── compiled/
│   └── sample_000001/
│       ├── scene.glb
│       └── render.mp4
├── metrics/
│   └── sample_000001.json
├── aggregate.json
└── report.html
```

---

## 5. 主要模块规划

## 5.1 资产规范化

### 输入

- GLB / glTF / FBX / OBJ / Blend；
- 资产来源配置；
- 可选的人工 override metadata。

### 处理

1. 导入 Blender；
2. 合并或规范 mesh 层级；
3. 应用变换；
4. 统一米制单位；
5. 调整 Z-up 和前向轴；
6. 将原点设置到合理位置；
7. 计算包围盒和 ground offset；
8. 检查材质、纹理和缺失资源；
9. 导出标准 GLB；
10. 生成六视图缩略图和 turntable；
11. 写入 metadata；
12. 运行自动验证。

### 验收标准

- 同一资产重复处理得到一致结果；
- GLB 可由 Blender 和 Three.js 同时加载；
- 所有资产尺寸、轴向和原点可解释；
- 不存在丢贴图、空 mesh、NaN 变换；
- 每个资产生成 metadata 和缩略图。

## 5.2 场景程序采样器

不要完全随机放置对象。采用“模板 + 约束 + 参数随机化”。

首批模板：

1. `static_scene_orbit_camera`
2. `static_scene_dolly_camera`
3. `moving_platform`
4. `rotating_object`
5. `elevator_motion`
6. `hinged_bridge_or_door`
7. `camera_follow_object`
8. `parent_child_transport`
9. `sequential_motion`
10. `crossing_identical_objects`
11. `temporary_occlusion`
12. `camera_object_ambiguity_pair`

每个模板必须定义：

- 必选对象槽位；
- 允许的资产类别；
- 放置关系；
- 运动类型；
- 相机行为；
- 可见性约束；
- 难度标签；
- 可复现 seed。

## 5.3 Blender 编译器

职责：

- 将 DSL 编译为 Blender 场景；
- 导入并实例化资产；
- 设置 transform、parent、constraint；
- 创建动画 F-curves；
- 创建相机和灯光；
- 保存 `.blend`；
- 导出 `.glb`；
- 渲染 RGB 和辅助 pass；
- 输出逐帧对象与相机真值。

要求：

- 纯函数式输入：相同 JSON + 相同资产版本应得到一致场景；
- 编译器不进行隐式“智能修复”；
- 所有修正和默认值必须可记录；
- 编译失败输出结构化错误。

## 5.4 自动质量检查

保存样本前至少检查：

- 每个关键对象的可见帧比例；
- 最大和最小屏幕面积；
- 目标对象是否在相机前方；
- 相机是否进入 mesh；
- 是否出现非预期穿透；
- 是否存在全黑或全白画面；
- 是否存在足够运动幅度；
- 是否有严重裁切；
- 视频是否能够重渲染；
- GT JSON 是否可通过 schema；
- GLB 是否可重新加载。

失败后自动重采样，超过次数则记录失败原因。

## 5.5 候选资产与干扰项

候选集合组成：

- GT 资产；
- 同类别资产；
- 相似轮廓资产；
- 相似尺寸比例资产；
- 随机负样本。

难度分层：

- Easy：跨类别；
- Medium：同类别；
- Hard：近似轮廓或局部差异；
- Ambiguous：输入视角下近似不可区分，使用等价类评分。

模型侧只能看到匿名 `asset_id` 和视觉预览，不能看到语义文件名。

## 5.6 模型推理接口

定义统一抽象：

```python
class SceneProgramPredictor(Protocol):
    def predict(
        self,
        video_path: Path,
        candidate_assets: list[AssetContext],
        schema: dict,
        metadata: dict,
    ) -> PredictionResult:
        ...
```

首版实现：

- `MockPredictor`：返回固定 JSON，用于端到端测试；
- `ReplayPredictor`：读取离线预测；
- `CommandPredictor`：调用外部命令；
- 后续再接具体模型 API 或本地模型。

所有 provider 必须记录：

- 模型名；
- 请求时间；
- 输入帧采样方式；
- token 或成本信息；
- 原始响应；
- JSON 修复次数；
- 最终预测。

## 5.7 评测器

### A. 可执行性

- JSON schema validity；
- asset ID 合法性；
- 引用完整性；
- Blender 编译成功率；
- GLB 导出成功率；
- 渲染成功率。

### B. 资产和实例

- asset top-1 / top-k；
- macro-F1；
- 对象数量误差；
- identity accuracy；
- 漏检和重复实例。

对象匹配使用匈牙利算法，不比较对象名称。

### C. 静态 3D 状态

- 平移误差；
- 归一化平移误差；
- rotation geodesic error；
- symmetry-aware rotation error；
- log-scale error；
- 相对空间关系准确率。

### D. 相机

- 相机类型准确率；
- FOV / ortho scale 误差；
- trajectory ATE；
- relative pose error；
- 朝向误差；
- tracking target 准确率。

### E. 动画

- position RMSE over time；
- rotation error over time；
- velocity / acceleration error；
- 起止、停顿、转向、接触事件 F1；
- 持续时间误差；
- 父子相对变换误差。

主评测在固定时间戳比较，不使用 DTW 掩盖时序错误。DTW 仅作为辅助指标。

### F. 渲染

- 输入视角 RGB；
- 输入视角 mask / depth / normal；
- 隐藏视角 mask / depth / normal；
- 可选隐藏视角 RGB。

几何指标在统一中性光照下重渲染，减少灯光误差污染。

### G. 程序质量与可编辑性

- 关键帧数量；
- 冗余曲线比例；
- 程序长度；
- 标准化编辑成功率。

标准编辑示例：

- 对象整体移动 1 米；
- 动画延迟 0.5 秒；
- 删除对象；
- 修改相机类型；
- 修改 parent 关系。

## 5.8 Web Viewer

### 目标页面

```text
┌──────────────────┬────────────────────────────┐
│ Input Video      │ Interactive 3D Viewer      │
│                  │ GT / Prediction / Overlay  │
├──────────────────┼────────────────────────────┤
│ GT Render        │ Predicted Render           │
├──────────────────┴────────────────────────────┤
│ Timeline / Object Inspector / Metrics / JSON  │
└───────────────────────────────────────────────┘
```

### 必须功能

- 样本列表与筛选；
- 播放输入视频；
- 加载 GT 和预测 GLB；
- GT / prediction 切换；
- 半透明叠加；
- 时间轴同步播放；
- 显示对象 ID、asset ID、包围盒；
- 显示相机和对象轨迹；
- 切换输入视角和自由视角；
- 查看单样本指标；
- 查看 GT / prediction JSON；
- 下载单样本结果；
- 显示编译和渲染错误。

### 部署

服务器：

```bash
smcb serve --host 127.0.0.1 --port 8080
```

本地：

```bash
ssh -L 8080:127.0.0.1:8080 user@server
```

浏览器访问：

```text
http://localhost:8080
```

首版不直接开放公网端口。

---

## 6. 命令行接口规划

统一入口：

```bash
smcb <command> [options]
```

建议命令：

```bash
# 环境与诊断
smcb doctor
smcb version

# 资产
smcb assets normalize --config configs/assets/normalization.yaml
smcb assets validate --root data/normalized_assets
smcb assets thumbnails --root data/normalized_assets
smcb assets index --root data/normalized_assets

# 数据生成
smcb generate --config configs/generation/tier1_scene_camera.yaml --count 100 --seed 42
smcb generate --config configs/generation/tier2_rigid_motion.yaml --count 1000 --workers 4
smcb validate-dataset --dataset data/datasets/dev

# 推理
smcb infer --dataset data/datasets/dev --predictor mock --run-id smoke_mock
smcb infer --dataset data/datasets/dev --predictor command --command ./predict.sh

# 编译预测
smcb compile-run --run data/runs/smoke_mock

# 评测
smcb evaluate --dataset data/datasets/dev --run data/runs/smoke_mock
smcb report --run data/runs/smoke_mock

# 服务
smcb serve --dataset data/datasets/dev --runs data/runs --port 8080
```

每个命令必须：

- 支持 `--dry-run`；
- 支持结构化日志；
- 返回非零错误码；
- 写入可追溯配置；
- 记录 Git commit 和环境信息。

---

## 7. Linux 与容器环境

## 7.1 推荐基础环境

- Linux x86_64；
- Python 3.11 或项目实际支持版本；
- Blender 固定版本；
- Node.js LTS；
- ffmpeg；
- NVIDIA 驱动和可选 GPU 容器支持；
- Git LFS 可选，仅用于小规模 demo 资产；
- 大数据不进入 Git。

## 7.2 环境分层

1. Python 开发环境：DSL、采样、评测、服务；
2. Blender 运行环境：编译和渲染；
3. Web 环境：Vite + React + Three.js；
4. 可选 GPU worker 环境。

不要把 Blender Python 包强行装进普通 Python 环境。普通代码通过子进程调用 Blender：

```bash
blender -b -P blender_scripts/render_sample.py -- --input scene.json --output out/
```

## 7.3 可复现性

必须固定：

- Blender 版本；
- 渲染引擎；
- 渲染参数；
- 资产版本和 checksum；
- Python lockfile；
- Node lockfile；
- 随机 seed；
- 相机和灯光默认值；
- ffmpeg 编码参数。

---

## 8. 分阶段实施计划

## Phase 0：仓库骨架与技术验证

目标：证明 Linux headless Blender → GLB → Web Viewer 全链路可行。

任务：

- 建立 Python 包、CLI、配置、日志；
- 添加 Docker / 本地安装说明；
- 添加最小 JSON schema；
- 手工准备 2–3 个标准 GLB；
- 编译一个静态场景；
- Blender headless 渲染视频；
- 导出 GLB；
- Three.js 加载 GLB；
- FastAPI 返回样本信息；
- 完成 SSH 隧道访问说明。

验收：

```bash
make smoke
```

能够生成并展示一个静态场景。

## Phase 1：最小闭环 MVP

目标：自动生成小型数据集并完成伪预测评测。

范围：

- 10–20 个规范化资产；
- 3 个模板；
- 静态场景和单对象线性运动；
- 透视和正交相机；
- RGB、mask、depth；
- MockPredictor；
- 可执行性、资产、pose、简单 motion 指标；
- GT / prediction Web 对比。

验收：

- 一条命令生成 100 个样本；
- 质量检查能剔除失败样本；
- GT 重新编译可近似复现输入视频；
- Mock 预测可跑完整评测；
- Viewer 可浏览全部样本。

## Phase 2：Benchmark Core

目标：形成可用于首轮模型实验的核心 benchmark。

范围：

- 60–150 个 CC0 资产；
- 10+ 场景模板；
- 3–8 个对象；
- 相机与物体同时运动；
- parent / look_at / track_to；
- hard distractors；
- hidden-view 渲染；
- 完整 motion、camera、relation 评测；
- 输入消融：首帧、首尾帧、均匀帧、乱序、倒放、完整视频。

验收：

- 固定 seed 可稳定复现；
- 所有指标有单元测试；
- 有至少一个真实模型 baseline；
- 报告能拆分 Tier、模板、难度和消融结果。

## Phase 3：规模化与论文 Demo

目标：提高数据规模、稳定性和展示效果。

范围：

- 多 GPU / 多 worker 队列；
- 断点续跑；
- Slurm 可选适配；
- 跨引擎渲染子集；
- 人工挑战集；
- 更强资产相似度检索；
- 在线报告与可分享 demo；
- 基线结果表和可视化。

验收：

- 生成和评测支持任务恢复；
- 大规模运行不会因单样本失败中断；
- Demo 能直接观察“输入视角看似正确、隐藏视角错误”的案例。

---

## 9. Coding Agent 执行顺序

Coding Agent 不应一次性实现全部功能。严格按以下顺序推进，每个步骤都先写测试和最小文档。

### Step 1：初始化仓库

- 创建目录结构；
- 配置 `pyproject.toml`；
- 添加格式化、静态检查和测试；
- 创建 `smcb` CLI；
- 添加 `smcb doctor`；
- 创建最小 README。

完成条件：CI 能运行空测试，CLI 可执行。

### Step 2：实现 DSL

- 定义 Pydantic/dataclass 模型；
- 导出 JSON Schema；
- 实现严格验证；
- 实现 canonicalization；
- 编写 3 个 example JSON；
- 添加错误样例测试。

完成条件：合法和非法程序均有确定结果。

### Step 3：Blender 最小编译器

- 清空场景；
- 导入 GLB；
- 设置 transform；
- 创建相机、灯光；
- 保存 Blend；
- 渲染单帧和短视频；
- 导出 GLB。

完成条件：`examples/minimal_scene.json` 在 headless 环境下可渲染。

### Step 4：静态 Web Viewer

- FastAPI 样本 API；
- React 页面；
- Three.js 加载 GLB；
- 播放视频；
- 展示 JSON；
- 添加 SSH 访问文档。

完成条件：浏览器能同时看到输入视频和 3D 场景。

### Step 5：资产规范化

- 资产导入；
- 轴向、单位、原点规范化；
- metadata；
- 缩略图；
- validation；
- checksum 和版本记录。

完成条件：一批测试资产可自动转为标准 GLB。

### Step 6：场景采样和质量检查

- 实现 3 个模板；
- 可复现随机数；
- 放置约束；
- 运动采样；
- 可见性检查；
- 失败重采样。

完成条件：100 个样本生成成功率达到预设阈值。

### Step 7：数据集 manifest 与索引

- 单样本 manifest；
- dataset index；
- split；
- 文件 checksum；
- validate-dataset 命令。

完成条件：数据集可增量生成和恢复。

### Step 8：推理抽象

- MockPredictor；
- ReplayPredictor；
- CommandPredictor；
- prompt artifact 保存；
- 原始响应保存；
- schema repair 日志。

完成条件：无需真实 API 也能完整跑通推理阶段。

### Step 9：基础评测

- 匈牙利对象匹配；
- asset / count；
- translation / rotation / scale；
- camera type；
- trajectory RMSE；
- 编译和渲染成功率；
- aggregate report。

完成条件：对人工构造的小误差预测得到符合预期的分数。

### Step 10：Web 对比增强

- GT / prediction 开关；
- Overlay；
- 同步时间轴；
- 对象 inspector；
- metrics panel；
- 轨迹和包围盒 overlay。

完成条件：可直接诊断预测失败原因。

### Step 11：高级指标和消融

- symmetry-aware pose；
- hidden-view render；
- event F1；
- parent-relative motion；
- standardized edits；
- 视频输入消融工具。

完成条件：Benchmark Core 指标完整。

---

## 10. 测试策略

## 10.1 单元测试

覆盖：

- schema validation；
- 坐标转换；
- quaternion 工具；
- 关键帧插值；
- 对象匹配；
- pose 和 camera 指标；
- manifest 读写；
- 配置合并。

## 10.2 Golden Tests

保存少量小场景：

- 固定 JSON；
- 固定资产 checksum；
- 固定相机；
- 固定输出指标。

不要严格比较 RGB 每个像素，可比较：

- 文件存在；
- 分辨率；
- 对象数量；
- mask 面积范围；
- 图像感知 hash 或容差统计；
- 轨迹数值。

## 10.3 Blender 集成测试

使用标签区分：

```bash
pytest -m "not blender"
pytest -m blender
```

普通 CI 跑轻量测试；带 Blender 的 runner 跑集成测试。

## 10.4 端到端 Smoke Test

```text
example JSON
→ Blender compile
→ render
→ export GLB
→ Mock prediction
→ compile prediction
→ evaluate
→ API returns sample
```

该测试必须能在小于几分钟内完成。

---

## 11. 工程规范

- Python 代码完整类型标注；
- 业务模块不得直接读取全局环境变量；
- 配置统一由 config 层解析；
- 所有长期任务支持断点续跑；
- 所有外部命令有 timeout 和错误捕获；
- 所有样本失败记录结构化原因；
- 禁止 silently skip；
- 生成器、编译器、评测器必须版本化；
- 数据结果中记录 Git commit；
- 大文件不提交 Git；
- 资产 license 和来源必须保留；
- API key 不进入配置文件和日志；
- Web 服务默认绑定 `127.0.0.1`。

---

## 12. 关键风险与规避方案

### 12.1 坐标系不一致

风险：Blender 正确但 Three.js 错，或相机朝向相反。

方案：只保留一个坐标转换模块；加入轴向 golden scene。

### 12.2 资产质量不统一

风险：单位、原点、材质、命名不一致。

方案：强制离线规范化；原始资产不进入生成器。

### 12.3 随机生成无意义场景

风险：穿透、遮挡、对象不可见。

方案：模板化采样 + 自动质量检查 + 失败重采样。

### 12.4 程序非唯一

风险：不同 JSON 产生同一动画。

方案：主评测比较逐时刻状态和渲染；程序结构作为辅助指标。

### 12.5 灯光欠约束

风险：几何正确但 RGB 差，或反之。

方案：统一中性光照下评几何；灯光独立成 challenge track。

### 12.6 大规模渲染失败

风险：单个场景导致整批任务中断。

方案：每个样本独立进程、超时、重试、失败清单和断点续跑。

### 12.7 网页与 Blender 动画不一致

风险：glTF 插值、父子关系或 quaternion 处理不同。

方案：首版网页优先加载 Blender 导出的 GLB；DSL 直编 Three.js 放在后续。

### 12.8 Benchmark 泄题

风险：资产文件名或类别 metadata 直接透露答案。

方案：模型输入只暴露匿名 ID 和视觉预览；语义 track 单独报告。

---

## 13. 首个可交付版本定义

仓库的第一个正式里程碑应满足：

1. Linux 服务器一条命令完成环境检查；
2. 至少 10 个标准化 GLB 资产；
3. 至少 3 个场景模板；
4. 自动生成 100 个视频样本；
5. 输出 GT JSON、Blend、GLB、RGB、mask、depth；
6. MockPredictor 生成预测；
7. 自动编译预测并输出指标；
8. FastAPI + Three.js 可浏览样本；
9. 可通过 SSH 端口转发在本地打开；
10. 有完整 smoke test 和运行文档。

建议将该版本命名为：

```text
v0.1.0 — End-to-End MVP
```

---

## 14. Coding Agent 首轮任务清单

首轮只完成以下内容，不扩展范围：

```text
[ ] 创建仓库骨架
[ ] 配置 Python 项目和 CLI
[ ] 实现最小 Scene Program schema
[ ] 添加 3 个 example JSON
[ ] 实现 Blender headless 最小编译器
[ ] 渲染一个 3 秒视频
[ ] 导出 scene.glb
[ ] 创建 FastAPI 样本接口
[ ] 创建 Three.js 最小 Viewer
[ ] 编写 smoke_test.sh
[ ] 编写 Linux 安装和 SSH 端口转发说明
```

首轮明确不做：

```text
[ ] 不接真实模型 API
[ ] 不做完整评测指标
[ ] 不做大规模数据生成
[ ] 不做资产自动相似度
[ ] 不做 Slurm
[ ] 不做跨引擎
[ ] 不做骨骼动画
```

---

## 15. 可直接给 Coding Agent 的启动指令

```text
请根据 PLAN.md 初始化 SceneMotionCodeBench 项目仓库。

本轮目标只做到 Phase 0：
1. 创建仓库目录结构和 Python 包；
2. 实现 smcb CLI 与 smcb doctor；
3. 定义并验证最小 scene_program JSON schema；
4. 添加 examples/minimal_scene.json；
5. 实现 Blender headless 编译脚本，支持导入 GLB、设置对象 transform、创建相机和灯光、渲染 3 秒 MP4、导出 GLB；
6. 创建 FastAPI 后端和最小 Three.js Viewer，展示输入视频和导出的 GLB；
7. 提供 scripts/smoke_test.sh，一条命令跑通 JSON → Blender → MP4/GLB → Web API；
8. 编写 README 中的 Linux 安装、运行和 SSH 端口转发步骤。

约束：
- 不实现真实模型推理；
- 不实现复杂场景生成；
- 不引入数据库；
- 不直接开放公网端口；
- 所有路径通过配置或 CLI 参数传入；
- Python 代码使用类型标注和结构化日志；
- 外部命令必须检查返回码并输出清晰错误；
- 每完成一个模块，先添加测试，再进入下一模块；
- 不自行扩大 PLAN.md 中定义的 Phase 0 范围。

完成后请输出：
- 新增文件列表；
- 关键设计说明；
- 运行命令；
- 测试结果；
- 尚未完成和已知限制。
```

---

## 16. 推荐的日常开发命令

```bash
make setup
make lint
make test
make test-blender
make smoke
make web
make serve
```

对应目标建议：

```makefile
setup:
	# 安装 Python 和 Web 依赖

lint:
	# Python + TypeScript 格式和静态检查

test:
	# 不依赖 Blender 的测试

test-blender:
	# Blender 集成测试

smoke:
	# 端到端最小闭环

web:
	# 构建前端

serve:
	# 启动 FastAPI + 静态前端
```

---

## 17. 项目成功判断

项目不是以“生成的视频看起来漂亮”为首要成功标准，而是以下闭环是否稳定：

```text
可复现 Scene Program
→ 可执行 Blender 场景
→ 可验证视频和 3D 真值
→ 模型一次性输出结构化预测
→ 自动编译与评测
→ 网页可诊断错误
```

只要该闭环稳定，后续扩大资产、模板、模型和指标都是增量工作。
