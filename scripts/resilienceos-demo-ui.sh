#!/usr/bin/env bash
set -euo pipefail

: "${VENV_BIN:=.venv/bin}"
: "${DEMO_COMMAND:=agent}"
: "${DEMO_SCENARIO:=singapore}"
: "${DEMO_PORT:=8501}"
: "${DEMO_INCLUDE_INBOX:=true}"
: "${DEMO_INCLUDE_SIMULATE:=true}"
: "${DEMO_ASSESSED_RISK:=90}"
: "${DEMO_INPUT:=}"
: "${DEMO_OVERRIDE_RISK:=true}"
: "${DEMO_PRESET_NAME:=}"
: "${DEMO_SHOW_CONCISE_BRIEF:=1}"
: "${DEMO_SHOW_RAW_JSON:=1}"
: "${DEMO_SHOW_RATIONALE:=1}"
DEMO_ORIG_PORT="${DEMO_PORT}"

DEMO_PORT="$(
  "${VENV_BIN}/python" - <<PY
import os
import socket

base = int(os.environ.get("DEMO_PORT", "8501"))
for offset in range(15):
    port = base + offset
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        sock.bind(("127.0.0.1", port))
        sock.close()
        print(port)
        raise SystemExit(0)
    except OSError:
        sock.close()
        continue
print(base)
PY
)"

if [ "${DEMO_ORIG_PORT}" != "${DEMO_PORT}" ]; then
  echo "Port ${DEMO_ORIG_PORT} was in use; using ${DEMO_PORT} instead."
fi

if [ ! -x "${VENV_BIN}/streamlit" ]; then
  echo "Streamlit not found in ${VENV_BIN}. Run 'make install-offline' or 'make install' first."
  exit 1
fi

if [ "${DEMO_OVERRIDE_RISK}" = "true" ]; then
  DEMO_OVERRIDE_PARAM="override_risk=true&assessed_risk=${DEMO_ASSESSED_RISK}"
else
  DEMO_OVERRIDE_PARAM="override_risk=false"
fi
DEMO_PRESET_PARAM=""
if [ -n "${DEMO_PRESET_NAME}" ]; then
  DEMO_PRESET_PARAM="&preset=${DEMO_PRESET_NAME}"
fi
DEMO_VISUAL_PARAMS="show_concise_brief=${DEMO_SHOW_CONCISE_BRIEF}&show_raw_json=${DEMO_SHOW_RAW_JSON}&show_rationale=${DEMO_SHOW_RATIONALE}"

DEMO_URL="http://127.0.0.1:${DEMO_PORT}/?command=${DEMO_COMMAND}&scenario=${DEMO_SCENARIO}&include_inbox=${DEMO_INCLUDE_INBOX}&include_simulate=${DEMO_INCLUDE_SIMULATE}&autostart=1&${DEMO_OVERRIDE_PARAM}&${DEMO_VISUAL_PARAMS}${DEMO_PRESET_PARAM}"

if [ -n "${DEMO_INPUT}" ]; then
  ENCODED_INPUT="$(python3 - <<'PY'
import urllib.parse
import os
print(urllib.parse.quote(os.environ["DEMO_INPUT"]))
PY
)"
  DEMO_URL="${DEMO_URL}&input=${ENCODED_INPUT}"
fi

export DEMO_URL
(
  cd "$(cd "$(dirname "$0")/.." && pwd)" || exit 1
  "${VENV_BIN}/streamlit" run frontend/app.py --server.port "${DEMO_PORT}"
) &

DEMO_PID=$!
trap 'kill "${DEMO_PID}" >/dev/null 2>&1 || true' EXIT

sleep 1.8
echo "Demo UI: ${DEMO_URL}"

# Open browser when possible; ignore if no GUI is available.
python3 - <<PY
import os
import webbrowser

url = os.environ.get("DEMO_URL", "")
if url:
    try:
        webbrowser.open(url, new=1)
    except Exception:
        pass
PY

wait "${DEMO_PID}"
