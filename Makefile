HOST ?= ../..
PYTHON ?= $(HOST)/.venv/bin/python
RUFF ?= $(HOST)/.venv/bin/ruff
WEB_BIN = $(HOST)/web-next/node_modules/.bin

.PHONY: check check-python check-web check-host
check: check-python check-web check-host
check-python:
	$(RUFF) check venom_module_cooperation_lab scripts tests
	$(RUFF) format --check venom_module_cooperation_lab scripts tests
	PYTHONPATH=$(HOST):. $(PYTHON) -m mypy venom_module_cooperation_lab --no-incremental --cache-dir=/dev/null
	PYTHONPATH=$(HOST):. $(PYTHON) -m pytest -q --cov=venom_module_cooperation_lab --cov-fail-under=90 --cov-report=term-missing --cov-report=xml:test-results/coverage.xml
check-web:
	$(WEB_BIN)/tsc --project web-next/tsconfig.json --noEmit
	$(WEB_BIN)/eslint web-next tests/web --max-warnings 0 --config web-next/eslint.config.mjs
	node --import $(HOST)/web-next/node_modules/tsx/dist/loader.mjs --test tests/web/*.test.ts
check-host:
	PYTHONPATH=$(HOST):. $(PYTHON) $(HOST)/scripts/check_optional_modules_contracts.py --manifest $(CURDIR)/module.json
