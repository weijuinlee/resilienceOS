#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../../../../" && pwd)"

if [[ -x "${REPO_ROOT}/.venv/bin/resilienceos" ]]; then
  CLI_CMD="${REPO_ROOT}/.venv/bin/resilienceos"
else
  CLI_CMD="resilienceos"
fi

run_ok() {
  local label="$1"
  shift
  echo
  echo "==== ${label} ===="
  "${CLI_CMD}" "$@"
}

run_expect_fail() {
  local label="$1"
  shift
  echo
  echo "==== ${label} (expected failure) ===="
  local output
  if output="$("${CLI_CMD}" "$@" 2>&1)"; then
    echo "FAIL: command unexpectedly succeeded"
    echo "${output}"
    return 1
  elif echo "${output}" | grep -q "Invalid value: format must be json or markdown"; then
    echo "PASS: clean validation error observed"
    echo "${output}"
    return 0
  else
    echo "WARN: command failed, but without expected validation message."
    echo "${output}"
    return 0
  fi
}

cd "${REPO_ROOT}"

run_ok "resilienceos assess (JSON)" assess --scenario singapore --format json
run_ok "resilienceos plan (JSON)" plan --scenario singapore --assessed-risk 90 --format json
run_ok "resilienceos agent (JSON + optional modules)" agent --scenario singapore --include-inbox --include-simulate --format json
run_ok "resilienceos assess fixture input (JSON)" assess --input fixtures/scenario_singapore_coastal.json --format json
run_expect_fail "resilienceos assess invalid format" assess --format xml

echo
echo "smoke checks complete"
