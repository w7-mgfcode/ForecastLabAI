#!/usr/bin/env bash
# scripts/dogfood-browser.sh — wrapper that prepares the environment for
# native-Python Playwright dogfooding against snap chromium.
#
# Background: on the maintainer's WSL host, the Playwright MCP and
# `npx playwright install` both fail; the only path that works is native
# Python Playwright pointed at `/snap/bin/chromium`. This script removes
# the rediscovery cost. See issue #262 and PRP-31 system review §
# "Update Browser-Dogfood automation".
#
# Usage:
#   ./scripts/dogfood-browser.sh                   # verify prereqs + print launch snippet
#   ./scripts/dogfood-browser.sh path/to/script.py # verify prereqs + exec the script with uv

set -euo pipefail

CHROMIUM_PATH="${CHROMIUM_PATH:-/snap/bin/chromium}"
LAUNCH_ARGS='["--no-sandbox", "--disable-setuid-sandbox", "--disable-dev-shm-usage"]'

echo "scripts/dogfood-browser.sh"
echo "================================================================"

# 1. snap chromium present?
if [ ! -x "$CHROMIUM_PATH" ]; then
  echo "ERROR: $CHROMIUM_PATH not found or not executable" >&2
  echo "Install with: sudo snap install chromium" >&2
  exit 1
fi
echo "OK   chromium executable: $CHROMIUM_PATH"

# 2. playwright importable from the project venv?
if ! uv run python -c "from playwright.sync_api import sync_playwright" >/dev/null 2>&1; then
  echo "WARN playwright not importable from .venv — installing now"
  uv pip install playwright
fi
echo "OK   playwright importable: $(uv run python -c 'import playwright; print(playwright.__version__)' 2>/dev/null)"

# 3. backend + frontend up?
if ! curl -s -m 3 http://localhost:8123/health >/dev/null 2>&1; then
  echo "WARN uvicorn :8123 unreachable — start with 'uv run uvicorn app.main:app --port 8123'"
fi
if ! curl -s -m 3 -o /dev/null -w '%{http_code}' http://localhost:5173/ | grep -q 200 2>/dev/null; then
  echo "WARN vite :5173 unreachable — start with 'cd frontend && ./node_modules/.bin/vite --host 0.0.0.0'"
fi

echo "================================================================"
echo "Use this Playwright launch snippet in your dogfood script:"
echo ""
echo "    from playwright.sync_api import sync_playwright"
echo "    with sync_playwright() as p:"
echo "        browser = p.chromium.launch("
echo "            headless=True,"
echo "            executable_path=\"$CHROMIUM_PATH\","
echo "            args=$LAUNCH_ARGS,"
echo "        )"
echo ""

# Optional: exec a passed script
if [ "$#" -ge 1 ]; then
  echo "================================================================"
  echo "Executing: uv run python $*"
  exec uv run python "$@"
fi
