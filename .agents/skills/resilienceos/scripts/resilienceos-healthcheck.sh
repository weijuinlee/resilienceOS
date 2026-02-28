#!/usr/bin/env bash
set -u

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../../../../" && pwd)"
CODEX_SKILL_PATH="${HOME}/.codex/skills/resilienceOS"
OUTPUT_DIR="${REPO_ROOT}/outputs"
TIMESTAMP="$(date -u +%Y%m%dT%H%M%SZ)"
LOG_FILE="${OUTPUT_DIR}/resilienceos-healthcheck-${TIMESTAMP}.log"

mkdir -p "${OUTPUT_DIR}"
: >"${LOG_FILE}"

FAIL_COUNT=0

log() {
  echo "$1" | tee -a "${LOG_FILE}"
}

info() {
  log ""
  log "==== $1 ===="
}

run_json_check() {
  local label="$1"
  local required_key="$2"
  shift 2

  info "${label}"
  local output
  if output="$("$@" 2>&1)"; then
    if command -v jq >/dev/null 2>&1; then
      if ! echo "${output}" | jq -e 'type=="object"' >/dev/null 2>&1; then
        log "FAIL: output is not JSON object"
        log "${output}"
        FAIL_COUNT=$((FAIL_COUNT + 1))
        return 1
      fi

      if [ -n "${required_key}" ] && ! echo "${output}" | jq -e "${required_key}" >/dev/null 2>&1; then
        log "FAIL: missing expected key ${required_key}"
        log "${output}"
        FAIL_COUNT=$((FAIL_COUNT + 1))
        return 1
      fi
    else
      log "WARN: jq not found, skipping structural JSON checks."
    fi
    log "${output}"
    log "PASS"
  else
    log "${output}"
    log "FAIL"
    FAIL_COUNT=$((FAIL_COUNT + 1))
    return 1
  fi
}

run_cmd() {
  local label="$1"
  shift
  info "${label}"
  local output
  if output="$("$@" 2>&1)"; then
    log "${output}"
    log "PASS"
  else
    log "FAIL: command could not execute"
    log "${output}"
    FAIL_COUNT=$((FAIL_COUNT + 1))
    return 1
  fi
}

run_cli_or_hint() {
  local cli_bin="$1"
  shift

  if [ -x "${cli_bin}" ]; then
    "${cli_bin}" "$@"
  elif command -v "${cli_bin}" >/dev/null 2>&1; then
    "${cli_bin}" "$@"
  else
    echo "MISSING CLI: ${cli_bin}"
    return 1
  fi
}

cd "${REPO_ROOT}"

info "Healthcheck report"
log "Repo root: ${REPO_ROOT}"
log "Log file: ${LOG_FILE}"

if [ -d ".venv" ]; then
  log ".venv detected."
else
  log "No .venv directory found. Install with:"
  log "- make install-offline"
  log "- make install"
fi

if command -v python3 >/dev/null 2>&1; then
  log "PASS: python3 found"
else
  log "WARN: python3 missing"
fi

if command -v jq >/dev/null 2>&1; then
  log "PASS: jq found"
else
  log "WARN: jq missing (JSON key assertions skipped)"
fi

CLI_BIN=""
if [ -x "${REPO_ROOT}/.venv/bin/resilienceos" ]; then
  CLI_BIN="${REPO_ROOT}/.venv/bin/resilienceos"
elif command -v resilienceos >/dev/null 2>&1; then
  CLI_BIN="resilienceos"
else
  log "Unable to locate resilienceos CLI."
  log "Run: make install-offline"
  exit 1
fi
log "Using CLI: ${CLI_BIN}"

info "Expected positive paths"
run_json_check "assess JSON" ".plugin_version" run_cli_or_hint "${CLI_BIN}" assess --scenario singapore --format json
run_json_check "plan JSON (risk override)" ".assessed_risk" run_cli_or_hint "${CLI_BIN}" plan --scenario singapore --assessed-risk 90 --format json
run_json_check "agent JSON (inbox+simulate)" ".scenario" run_cli_or_hint "${CLI_BIN}" agent --scenario singapore --include-inbox --include-simulate --format json
run_json_check "fixture input JSON" ".plugin_version" run_cli_or_hint "${CLI_BIN}" assess --input fixtures/scenario_singapore_coastal.json --format json

info "Expected failure path"
if output="$(run_cli_or_hint "${CLI_BIN}" assess --format xml 2>&1)"; then
  log "FAIL: invalid format unexpectedly succeeded"
  log "${output}"
  FAIL_COUNT=$((FAIL_COUNT + 1))
else
  if echo "${output}" | grep -q "Invalid value: format must be json or markdown"; then
    log "PASS: clean validation error observed"
  else
    log "WARN: expected error text not found"
    log "${output}"
    FAIL_COUNT=$((FAIL_COUNT + 1))
  fi
fi

info "Codex discovery"
if [ -L "${CODEX_SKILL_PATH}" ]; then
  resolved_target="$(readlink -f "${CODEX_SKILL_PATH}")"
  if [ "${resolved_target}" = "${REPO_ROOT}" ]; then
    log "PASS: ${CODEX_SKILL_PATH} -> ${resolved_target}"
  else
    log "WARN: Codex link points elsewhere: ${resolved_target}"
    FAIL_COUNT=$((FAIL_COUNT + 1))
  fi
else
  log "WARN: ${CODEX_SKILL_PATH} not a symlink"
  FAIL_COUNT=$((FAIL_COUNT + 1))
fi

if [ -f "${CODEX_SKILL_PATH}/resilienceos.skill.json" ]; then
  log "PASS: resilienceos.skill.json found via Codex discovery path"
else
  log "WARN: resilienceos.skill.json missing from Codex discovery path"
  FAIL_COUNT=$((FAIL_COUNT + 1))
fi

info "Healthcheck summary"
log "Failures: ${FAIL_COUNT}"
if [ "${FAIL_COUNT}" -eq 0 ]; then
  log "Result: PASS"
  log "Done."
  exit 0
else
  log "Result: FAIL"
  log "Recommendation: run rm -rf .venv && make install-offline && make codex-link, then retry."
  exit 1
fi
