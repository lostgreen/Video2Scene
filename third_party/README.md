# Third-Party Dependencies

`sceneactbench/` is a Git submodule used only as an execution and evaluation harness. Local code
must integrate through `src/smcb/integrations/sceneactbench/`; do not patch the submodule for
Video2Scene-specific behavior.

The expected revision is recorded in `sceneactbench.lock.json` and checked by
`video2scene sceneact doctor`. Initialize it with:

```bash
scripts/fetch_sceneactbench.sh
```

Updating the pin requires reviewing the upstream task, run-output, Dynamic scoring, Blender MCP,
and license contracts together. Update the submodule pointer, lock file, attribution constant,
tests, and `NOTICE.md` in the same change.
