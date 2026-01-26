#!/usr/bin/env bash
#
# Local CI Checks - Run the same checks as GitHub Actions CI
#
# Usage:
#   ./examples/ci/local_checks.sh          # Run all checks
#   ./examples/ci/local_checks.sh --quick  # Skip tests (lint + typecheck only)
#
# Requirements:
#   - Python 3.12+ with dependencies installed (pip or uv)
#   - Docker running (for database tests)
#   - .env file configured (or use defaults)
#
# Note: This script works with both uv and pip/venv setups.
# It detects uv and uses it if available, otherwise falls back to venv.

set -euo pipefail

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Parse arguments
QUICK_MODE=false
if [[ "${1:-}" == "--quick" ]]; then
    QUICK_MODE=true
fi

echo "========================================"
echo "ForecastLabAI - Local CI Checks"
echo "========================================"
echo ""

# Detect if uv is available, otherwise use venv
if command -v uv &> /dev/null; then
    RUN_CMD="uv run"
    echo "Using: uv"
elif [[ -f ".venv/bin/activate" ]]; then
    # shellcheck source=/dev/null
    source .venv/bin/activate
    RUN_CMD=""
    echo "Using: .venv"
else
    echo -e "${RED}Error: Neither uv nor .venv found. Install dependencies first.${NC}"
    exit 1
fi
echo ""

# Track failures
FAILED=0

# Function to run a check
run_check() {
    local name="$1"
    shift
    echo -e "${YELLOW}>>> Running: ${name}${NC}"
    if $RUN_CMD "$@"; then
        echo -e "${GREEN}✓ ${name} passed${NC}"
        echo ""
    else
        echo -e "${RED}✗ ${name} failed${NC}"
        echo ""
        FAILED=1
    fi
}

# 1. Lint check
run_check "Ruff lint" ruff check .

# 2. Format check
run_check "Ruff format" ruff format --check .

# 3. Type check (MyPy)
run_check "MyPy" mypy app/

# 4. Type check (Pyright)
run_check "Pyright" pyright app/

if [[ "$QUICK_MODE" == "true" ]]; then
    echo "========================================"
    echo "Quick mode: Skipping tests and migrations"
    echo "========================================"
else
    # 5. Check if Docker is running
    if ! docker info > /dev/null 2>&1; then
        echo -e "${RED}Docker is not running. Start Docker to run tests.${NC}"
        echo "Run with --quick to skip tests."
        exit 1
    fi

    # 6. Ensure database is running
    if ! docker-compose ps 2>/dev/null | grep -q "forecastlab-postgres.*Up"; then
        echo -e "${YELLOW}Starting PostgreSQL container...${NC}"
        docker-compose up -d
        # Wait for postgres to be ready
        echo "Waiting for PostgreSQL to be ready..."
        sleep 5
    fi

    # 7. Run migrations
    run_check "Alembic migrations" alembic upgrade head

    # 8. Run tests
    run_check "Pytest" pytest -v --tb=short
fi

# Summary
echo "========================================"
if [[ "$FAILED" -eq 0 ]]; then
    echo -e "${GREEN}All checks passed!${NC}"
    exit 0
else
    echo -e "${RED}Some checks failed. Fix issues before pushing.${NC}"
    exit 1
fi
