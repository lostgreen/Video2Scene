PYTHON ?= $(if $(SMCB_PYTHON),$(SMCB_PYTHON),python3)

.PHONY: setup lint test doctor smoke

setup:
	$(PYTHON) -m pip install -e . -r requirements/dev.txt

lint:
	ruff check src tests blender_scripts
	ruff format --check src tests blender_scripts
	mypy src

test:
	PYTHONPATH=src $(PYTHON) -m pytest

doctor:
	PYTHONPATH=src $(PYTHON) -m smcb.cli doctor

smoke:
	scripts/smoke_test.sh
