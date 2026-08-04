# World-Time Canonicalization Direction

The long-term benchmark target is narrower than generic video-to-scene reconstruction:

```text
fixed known scene + fixed known camera + edited observation
    -> video-to-world time mapping + canonical world motion
```

For world state `X(tau)`, an observed video is generated as
`Y(t) = Render(X(phi(t)), C0)`. The primary latent variable is `phi`: presentation time to world
time. Replay, reverse, freeze, jump cuts, and rate changes are represented by the mapping rather
than independent edit labels.

SceneActBench compatibility is an enabling milestone, not the final task. It establishes a
reproducible multi-object animated world, a headless agent execution loop, and an independent 3D
scorer. Once that base passes oracle and perturbation tests, Video2Scene will add temporal-edit
generation on top of the unchanged master rollout.

The first executable prototype now fixes the master rollout to 144 frames at 24 fps and derives
four equally long observations: normal, reverse, freeze, and replay. Each observation ships a
strict piecewise-linear `timeline.json`; the evaluator reports source-time mapping error,
breakpoint F1, direction accuracy, and rate error. This isolates the new benchmark variable before
model integration. SceneAct's 3D score and World-Time's mapping score remain separate reports.

The Core Track will provide asset identities, initial layout, object list, and camera. It will
score dense source-time mapping, temporal breakpoints, direction/rate, canonical event order, and
unwarped 3D trajectories. Asset retrieval, camera estimation, physics, and multi-camera alignment
remain outside the first World-Time benchmark.

See [the runnable demo contract](integrations/worldtime_demo.md) for the exact artifacts and CLI.
