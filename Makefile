.PHONY: setup lint test cases check-contracts bench audit ci

setup:
	cd python && python -m pip install --upgrade pip && python -m pip install -e ".[dev]"

lint:
	python spec/build_cases.py --check
	cd python && python -m ruff check . ../spec && python -m ruff format --check . ../spec
	cd js && npm run -s lint

# Contract validation, change classification (shared cases in Python and JS) and the PR check.
test:
	cd python && python -m pytest -q
	cd js && npm test

# Rebuild spec/cases.json after changing spec/build_cases.py.
cases:
	python spec/build_cases.py

# What CI runs on a pull request: compare contracts/ with the published version on BASE.
BASE ?= origin/main
check-contracts:
	datacontract validate contracts/*.yaml
	datacontract check-pr --base $(BASE) contracts

bench:
	@echo "M3: before/after count of data incidents in the demo scenario"

# Known vulnerabilities in the installed Python dependencies.
audit:
	cd python && python -m pip_audit --skip-editable --cache-dir ../.tmp/pip-audit

ci: setup lint test
