# Video2Scene

Video2Scene is the repository for the SceneMotionCodeBench (`smcb`) project
described in [PLAN.md](PLAN.md). The repository currently contains the Step 1
engineering skeleton: a Python package, CLI diagnostics, reproducible Blender
bootstrap script, and the planned module directories.

## Requirements

- Python 3.11
- Blender 4.5.12 LTS
- ffmpeg
- Node.js LTS for the future web viewer

## Quick start

```bash
python3.11 -m venv .venv
source .venv/bin/activate
python -m pip install -e . -r requirements/dev.txt
smcb doctor
make test
```

Install the pinned Blender build without root access:

```bash
BLENDER_ROOT="$HOME/.local/opt/video2scene" scripts/bootstrap_linux.sh
export BLENDER_BIN="$HOME/.local/opt/video2scene/blender/blender"
export PATH="$(dirname "$BLENDER_BIN"):$PATH"
smcb doctor
```

Machine-specific values belong in `.env.local`, which is ignored by Git. The
existing local `Demo/` directory, generated data, and artifacts are also
intentionally excluded from version control.

## Layout

- `src/smcb/`: Python package and planned pipeline modules
- `blender_scripts/`: Blender entry points
- `web/`: future React/Three.js viewer
- `configs/` and `schemas/`: versioned contracts and defaults
- `data/` and `artifacts/`: generated local state, ignored except placeholders
- `scripts/`: environment and workflow commands
- `tests/`: unit, integration, Blender, golden, and web test suites

The current milestone is repository initialization only. Phase 0 rendering and
viewer behavior remains to be implemented in the order defined by `PLAN.md`.
