HOST ?= ../..
HOST := $(abspath $(HOST))
PYTHON ?= $(HOST)/.venv/bin/python
RUFF ?= $(HOST)/.venv/bin/ruff
WEB_BIN = $(HOST)/web-next/node_modules/.bin
CHECK_DIRS = venom_module_cooperation_lab tests $(if $(wildcard scripts/*.py),scripts,)

.PHONY: check check-python check-web check-host
check: check-python check-web check-host
check-python:
	$(RUFF) check $(CHECK_DIRS)
	$(RUFF) format --check $(CHECK_DIRS)
	PYTHONPATH=$(HOST):. $(PYTHON) -m mypy venom_module_cooperation_lab --no-incremental --cache-dir=/dev/null
	PYTHONPATH=$(HOST):. $(PYTHON) -m pytest -q --cov=venom_module_cooperation_lab --cov-fail-under=90 --cov-report=term-missing --cov-report=xml:test-results/coverage.xml
check-web:
	node scripts/check-web.mjs $(HOST)
check-host:
	PYTHONPATH=$(HOST):. $(PYTHON) $(HOST)/scripts/check_optional_modules_contracts.py --manifest $(CURDIR)/module.json
