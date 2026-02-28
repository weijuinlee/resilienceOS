SHELL := /bin/bash

PYTHON ?= python3
VENV ?= .venv
VENV_BIN := $(VENV)/bin
SCENARIO ?= singapore

.PHONY: help install install-offline smoke smoke-direct smoke-installed smoke-fast smoke-agent smoke-fail smoke-input smoke-skill codex-link clean

help:
	@echo "Targets:"
	@echo "  install        - create .venv and install package in editable mode"
	@echo "  install-offline - create .venv with system-site-packages and install in editable mode (no dependency downloads)"
	@echo "  smoke          - run JSON smoke checks via direct PYTHONPATH fallback"
	@echo "  smoke-installed - run smoke checks via installed resilienceos CLI (if available)"
	@echo "  smoke-skill    - run deterministic skill smoke checks using the skill helper script"
	@echo "  smoke-fast     - run the 2-minute hackathon demo flow with expected failure path"
	@echo "  smoke-agent    - run assess/plan/agent bundle smoke checks"
	@echo "  smoke-fail     - run invalid format failure path (expected)"
	@echo "  smoke-input    - run fixture file smoke check"
	@echo "  codex-link     - link repo as ~/.codex/skills/resilienceOS"
	@echo "  clean          - remove .venv"

install:
	$(PYTHON) -m venv $(VENV)
	$(VENV_BIN)/python -m pip install -e . --no-build-isolation --no-deps || $(VENV_BIN)/python setup.py develop

install-offline:
	$(PYTHON) -m venv --system-site-packages $(VENV)
	$(VENV_BIN)/python -m pip install -e . --no-build-isolation --no-deps || $(VENV_BIN)/python setup.py develop

smoke-direct:
	PYTHONPATH=src $(PYTHON) -m resilienceos.cli assess --scenario $(SCENARIO) --format json
	PYTHONPATH=src $(PYTHON) -m resilienceos.cli plan --scenario $(SCENARIO) --assessed-risk 90 --format json
	PYTHONPATH=src $(PYTHON) -m resilienceos.cli agent --scenario $(SCENARIO) --include-inbox --include-simulate --format json

smoke-fail:
	- PYTHONPATH=src $(PYTHON) -m resilienceos.cli assess --format xml

smoke-input:
	PYTHONPATH=src $(PYTHON) -m resilienceos.cli assess --input fixtures/scenario_singapore_coastal.json --format json

smoke: smoke-direct smoke-fail smoke-input

smoke-installed:
	$(VENV_BIN)/resilienceos assess --scenario $(SCENARIO) --format json
	$(VENV_BIN)/resilienceos plan --scenario $(SCENARIO) --assessed-risk 90 --format json
	$(VENV_BIN)/resilienceos agent --scenario $(SCENARIO) --include-inbox --include-simulate --format json
	- $(VENV_BIN)/resilienceos assess --format xml
	$(VENV_BIN)/resilienceos assess --input fixtures/scenario_singapore_coastal.json --format json

smoke-fast:
	$(VENV_BIN)/resilienceos assess --scenario $(SCENARIO) --format json | jq '.risk_score, .readiness_scores'
	$(VENV_BIN)/resilienceos plan --scenario $(SCENARIO) --assessed-risk 90 --format json | jq '.time_horizon_plan["6h"], .task_assignment_matrix[:2]'
	$(VENV_BIN)/resilienceos agent --scenario $(SCENARIO) --include-inbox --include-simulate --format json | jq '.scenario, .immediate_actions, .watchlist'
	$(VENV_BIN)/resilienceos explain --scenario $(SCENARIO) --format json | jq '.plain_language_rationale'
	$(VENV_BIN)/resilienceos assess --format xml || true

smoke-skill:
	bash .agents/skills/resilienceos/scripts/resilienceos-smoke-checks.sh

smoke-agent: smoke-direct

codex-link:
	mkdir -p ~/.codex/skills
	ln -sfn "$(CURDIR)" ~/.codex/skills/resilienceOS

clean:
	rm -rf $(VENV)
