#!/usr/bin/env bash
set -euo pipefail

: "${VENV_BIN:=.venv/bin}"
: "${DEMO_COMMAND:=agent}"
: "${DEMO_SCENARIO:=singapore}"
: "${DEMO_PORT:=8501}"
: "${DEMO_INCLUDE_INBOX:=true}"
: "${DEMO_INCLUDE_SIMULATE:=true}"
: "${DEMO_ASSESSED_RISK:=90}"
: "${DEMO_OVERRIDE_RISK:=true}"
: "${DEMO_SCREENSHOT:=outputs/resilienceos-dashboard-demo.png}"
: "${DEMO_PRESET_NAME:=}"
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

if ! "${VENV_BIN}/python" -c "import importlib.util, sys; sys.exit(0 if importlib.util.find_spec('playwright') else 1)"; then
  echo "Playwright not installed in ${VENV_BIN}."
  echo "Manual step: run 'make demo-ui' and take a screenshot with your OS tool."
  echo "Optional automation:"
  echo "  ${VENV_BIN}/python -m pip install playwright && playwright install chromium"
  echo "  make demo-shot"
  exit 0
fi

if [ ! -x "${VENV_BIN}/streamlit" ]; then
  echo "Streamlit not found in ${VENV_BIN}. Run 'make install-offline' first."
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

DEMO_URL="http://127.0.0.1:${DEMO_PORT}/?command=${DEMO_COMMAND}&scenario=${DEMO_SCENARIO}&include_inbox=${DEMO_INCLUDE_INBOX}&include_simulate=${DEMO_INCLUDE_SIMULATE}&autostart=1&${DEMO_OVERRIDE_PARAM}${DEMO_PRESET_PARAM}"
export DEMO_URL

(
  cd "$(cd "$(dirname "$0")/.." && pwd)" || exit 1
  "${VENV_BIN}/streamlit" run frontend/app.py --server.port "${DEMO_PORT}"
) &

DEMO_PID=$!
trap 'kill "${DEMO_PID}" >/dev/null 2>&1 || true' EXIT

sleep 2.2
"${VENV_BIN}/python" - <<'PY'
import os
from playwright.sync_api import sync_playwright

url = os.environ["DEMO_URL"]
output = os.environ.get("DEMO_SCREENSHOT", "outputs/resilienceos-dashboard-demo.png")

with sync_playwright() as p:
    browser = p.chromium.launch()
    page = browser.new_page(viewport={"width": 1600, "height": 1200})
    page.goto(url, wait_until="networkidle", timeout=60000)
    page.screenshot(path=output, full_page=True)
    browser.close()

print(f"Saved demo screenshot: {output}")
PY

wait "${DEMO_PID}"
