SHELL := /bin/bash

PYTHON ?= python3
VENV ?= .venv
VENV_BIN := $(VENV)/bin
SCENARIO ?= singapore
DEMO_COMMAND ?= agent
DEMO_SCENARIO ?= singapore
DEMO_INCLUDE_INBOX ?= true
DEMO_INCLUDE_SIMULATE ?= true
DEMO_ASSESSED_RISK ?= 90
DEMO_SCREENSHOT ?= outputs/resilienceos-dashboard-demo.png
DEMO_PORT ?= 8501
DEMO_PRESET ?= scripts/demo-presets/judge.env

.PHONY: help install install-offline smoke smoke-direct smoke-installed smoke-fast smoke-agent smoke-fail smoke-input smoke-skill skill-health ui demo-ui demo-shot demo-local demo-local-judge demo-local-highrisk demo-local-shot demo-shot-highrisk codex-link clean

help:
	@echo "Targets:"
	@echo "  install        - create .venv and install package in editable mode"
	@echo "  install-offline - create .venv with system-site-packages and install in editable mode (no dependency downloads)"
	@echo "  smoke          - run JSON smoke checks via direct PYTHONPATH fallback"
	@echo "  smoke-installed - run smoke checks via installed resilienceos CLI (if available)"
	@echo "  smoke-skill    - run deterministic skill smoke checks using the skill helper script"
	@echo "  skill-health   - run the Codex skill healthcheck with structured pass/fail output"
	@echo "  smoke-fast     - run the 2-minute hackathon demo flow with expected failure path"
	@echo "  smoke-agent    - run assess/plan/agent bundle smoke checks"
	@echo "  smoke-fail     - run invalid format failure path (expected)"
	@echo "  smoke-input    - run fixture file smoke check"
	@echo "  ui             - launch Streamlit dashboard (installs streamlit if missing in venv)"
	@echo "  demo-ui        - launch one-click Streamlit judge demo with preloaded command/scenario"
	@echo "  demo-local     - one-click judge preset demo (no env vars needed)"
	@echo "  demo-local-shot - one-click judge preset screenshot capture (requires Playwright)"
	@echo "  demo-local-judge - explicit one-click judge preset run"
	@echo "  demo-local-highrisk - one-click high-risk preset demo"
	@echo "  demo-shot-highrisk - one-click high-risk screenshot capture (requires Playwright)"
	@echo "  demo-shot      - run one-click demo and capture screenshot (requires Playwright)"
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
	@set -euo pipefail; \
	SCENARIO_NAME="$(SCENARIO)"; \
	TIMESTAMP="$$(date -u +%Y%m%dT%H%M%SZ)"; \
	LOG_FILE="outputs/smoke-fast-$${TIMESTAMP}.log"; \
	mkdir -p outputs; \
	if [ -x "$(VENV_BIN)/resilienceos" ]; then \
		CLI="$(VENV_BIN)/resilienceos"; \
	elif command -v resilienceos >/dev/null 2>&1; then \
		CLI="resilienceos"; \
	else \
		echo "resilienceos CLI not found. Run: make install-offline"; \
		exit 1; \
	fi; \
	run_view() { \
		label="$$1"; shift; \
		expr="$$1"; shift; \
		echo "==== $$label (scenario=$${SCENARIO_NAME}) ====" | tee -a "$$LOG_FILE"; \
		if command -v jq >/dev/null 2>&1; then \
			"$$CLI" "$$@" --format json | jq -r "$$expr" | tee -a "$$LOG_FILE"; \
		else \
			echo "WARN: jq not installed; showing raw JSON for $$label" | tee -a "$$LOG_FILE"; \
			"$$CLI" "$$@" --format json | tee -a "$$LOG_FILE"; \
		fi; \
	}; \
	run_view "Assess" ".risk_score, .readiness_scores" assess --scenario "$${SCENARIO_NAME}" ; \
	run_view "Plan 6h+" ".time_horizon_plan[\"6h\"], .task_assignment_matrix[:2]" plan --scenario "$${SCENARIO_NAME}" --assessed-risk 90; \
	run_view "Agent focus" ".scenario, .immediate_actions, .watchlist" agent --scenario "$${SCENARIO_NAME}" --include-inbox --include-simulate; \
	run_view "Explain" ".plain_language_rationale" explain --scenario "$${SCENARIO_NAME}"; \
	if "$$CLI" assess --format xml >/tmp/smoke-fast-xml-$${TIMESTAMP}.txt 2>&1; then \
		echo "FAIL: assess xml unexpectedly succeeded" | tee -a "$$LOG_FILE"; \
		exit 1; \
	else \
		echo "PASS: invalid format failure observed" | tee -a "$$LOG_FILE"; \
		echo "Output: $$(cat /tmp/smoke-fast-xml-$${TIMESTAMP}.txt | sed -n '1,4p' )" | tee -a "$$LOG_FILE"; \
		rm -f /tmp/smoke-fast-xml-$${TIMESTAMP}.txt; \
	fi; \
	echo "Smoke-fast log: $$LOG_FILE"

smoke-skill:
	bash .agents/skills/resilienceos/scripts/resilienceos-smoke-checks.sh

skill-health:
	bash .agents/skills/resilienceos/scripts/resilienceos-healthcheck.sh

ui:
	@if [ ! -x "$(VENV_BIN)/streamlit" ]; then \
		echo "Installing Streamlit into .venv"; \
		$(VENV_BIN)/python -m pip install streamlit; \
	fi
	$(VENV_BIN)/streamlit run frontend/app.py

demo-ui:
	DEMO_COMMAND=$(DEMO_COMMAND) \
	DEMO_SCENARIO=$(DEMO_SCENARIO) \
	DEMO_INCLUDE_INBOX=$(DEMO_INCLUDE_INBOX) \
	DEMO_INCLUDE_SIMULATE=$(DEMO_INCLUDE_SIMULATE) \
	DEMO_ASSESSED_RISK=$(DEMO_ASSESSED_RISK) \
	DEMO_PORT=$(DEMO_PORT) \
	VENV_BIN=$(VENV_BIN) \
	bash scripts/resilienceos-demo-ui.sh

demo-shot:
	DEMO_COMMAND=$(DEMO_COMMAND) \
	DEMO_SCENARIO=$(DEMO_SCENARIO) \
	DEMO_INCLUDE_INBOX=$(DEMO_INCLUDE_INBOX) \
	DEMO_INCLUDE_SIMULATE=$(DEMO_INCLUDE_SIMULATE) \
	DEMO_ASSESSED_RISK=$(DEMO_ASSESSED_RISK) \
	DEMO_PORT=$(DEMO_PORT) \
	DEMO_SCREENSHOT=$(DEMO_SCREENSHOT) \
	VENV_BIN=$(VENV_BIN) \
	bash scripts/resilienceos-demo-shot.sh

demo-local:
	@if [ ! -x "$(VENV_BIN)/python" ]; then \
		echo "Missing python in $(VENV_BIN). Run make install-offline first."; \
		exit 1; \
	fi; \
	if [ ! -x "$(VENV_BIN)/streamlit" ]; then \
		echo "Streamlit not installed in $(VENV_BIN). Run make ui once to install it."; \
		exit 1; \
	fi; \
	if [ -f "$(DEMO_PRESET)" ]; then \
		set -a; . "$(DEMO_PRESET)"; set +a; \
	else \
		echo "Missing preset file: $(DEMO_PRESET)"; \
		exit 1; \
	fi; \
	VENV_BIN=$(VENV_BIN) \
	bash scripts/resilienceos-demo-ui.sh

demo-local-judge:
	@DEMO_PRESET=scripts/demo-presets/judge.env $(MAKE) demo-local

demo-local-highrisk:
	@DEMO_PRESET=scripts/demo-presets/high-risk.env $(MAKE) demo-local

demo-local-shot:
	@set -a; \
	if [ -f "$(DEMO_PRESET)" ]; then \
		. "$(DEMO_PRESET)"; \
	else \
		echo "Missing preset file: $(DEMO_PRESET)"; \
		exit 1; \
	fi; \
	set +a; \
	VENV_BIN=$(VENV_BIN) \
	bash scripts/resilienceos-demo-shot.sh

demo-shot-highrisk:
	@DEMO_PRESET=scripts/demo-presets/high-risk.env $(MAKE) demo-local-shot

smoke-agent: smoke-direct

codex-link:
	mkdir -p ~/.codex/skills
	ln -sfn "$(CURDIR)" ~/.codex/skills/resilienceOS

clean:
	rm -rf $(VENV)
