PYTHON_RUN = scripts/run_python.sh
V2S = $(PYTHON_RUN) -m smcb.cli
ASSET_LIMIT ?= 30

.PHONY: setup lint test doctor smoke assets asset-previews scene-smoke dataset-smoke dataset-mvp dataset-check schema

setup:
	$(PYTHON_RUN) -m pip install -e . -r requirements/dev.txt

lint:
	$(PYTHON_RUN) -m ruff check src tests blender_scripts
	$(PYTHON_RUN) -m ruff format --check src tests blender_scripts
	$(PYTHON_RUN) -m mypy src

test:
	$(PYTHON_RUN) -m pytest

doctor:
	$(V2S) doctor

smoke:
	scripts/smoke_test.sh

assets:
	$(V2S) assets fetch
	$(V2S) assets normalize --limit $(ASSET_LIMIT)

asset-previews:
	$(V2S) assets previews --limit $(ASSET_LIMIT)

scene-smoke:
	$(V2S) generate --config configs/dataset/scene_smoke.yaml --num-samples 1

dataset-smoke:
	$(V2S) generate --config configs/dataset/smoke.yaml --num-samples 4

dataset-mvp:
	$(V2S) generate --config configs/dataset/mvp.yaml --num-samples 100 --seed 42

dataset-check:
	$(V2S) validate-dataset

schema:
	$(V2S) write-schema
