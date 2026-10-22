HOST ?= ../..
HOST := $(abspath $(HOST))
PYTHON ?= $(HOST)/.venv/bin/python
RUFF ?= $(HOST)/.venv/bin/ruff
WEB_BIN = $(HOST)/web-next/node_modules/.bin
NEW_CODE_DIFF_BASE ?= origin/main
NEW_CODE_CHANGED_LINES_MIN ?=
CHECK_DIRS = venom_module_cooperation_lab tests $(if $(wildcard scripts/*.py),scripts,)

.PHONY: check check-python check-web check-host
check: check-python check-web check-host
check-python:
	$(RUFF) check $(CHECK_DIRS)
	$(RUFF) format --check $(CHECK_DIRS)
	PYTHONPATH=$(HOST):. $(PYTHON) -m mypy venom_module_cooperation_lab --no-incremental --cache-dir=/dev/null
	PYTHONPATH=$(HOST):. $(PYTHON) -m pytest -q --cov=venom_module_cooperation_lab --cov-fail-under=90 --cov-report=term-missing --cov-report=xml:test-results/coverage.xml
	$(PYTHON) scripts/test_metadata.py coverage-stamp
check-web:
	node scripts/check-web.mjs $(HOST)
check-host:
	PYTHONPATH=$(HOST):. $(PYTHON) $(HOST)/scripts/check_optional_modules_contracts.py --manifest $(CURDIR)/module.json

# Module-owned metadata and coverage. The host checker hardcodes venom_core.
.PHONY: pr-fast test-catalog-sync test-groups-sync test-catalog-check test-groups-check check-new-code-coverage-diagnostics
pr-fast: test-catalog-check test-groups-check
	$(MAKE) --no-print-directory check HOST=$(HOST)
	$(MAKE) --no-print-directory check-new-code-coverage-diagnostics HOST=$(HOST)
test-catalog-sync:
	$(PYTHON) scripts/test_metadata.py catalog-sync
test-groups-sync:
	$(PYTHON) scripts/test_metadata.py groups-sync
test-catalog-check:
	$(PYTHON) scripts/test_metadata.py catalog-check
test-groups-check:
	$(PYTHON) scripts/test_metadata.py groups-check
check-new-code-coverage-diagnostics:
	$(PYTHON) scripts/test_metadata.py coverage --host $(HOST) --diff-base $(NEW_CODE_DIFF_BASE) $(if $(NEW_CODE_CHANGED_LINES_MIN),--min-coverage $(NEW_CODE_CHANGED_LINES_MIN),)
