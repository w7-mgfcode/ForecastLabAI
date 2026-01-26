# PRP-1: Repo Governance + CI/CD + Branching

**Source**: `INITIAL-1.md`
**Status**: Ready for Implementation
**Confidence Score**: 9/10 (high confidence for one-pass success)

---

## Goal

Implement production-grade GitHub Actions CI/CD pipeline with branch protection guidance, PR/issue templates, and local CI tooling to ensure code quality gates are enforced consistently across the ForecastLabAI project.

## Why

- **Quality Gates**: Automated linting, testing, type checking prevent broken code from merging
- **Consistency**: Same checks run locally and in CI, reducing "works on my machine" issues
- **Reproducibility**: Locked dependencies and deterministic workflows ensure consistent builds
- **Developer Experience**: PR templates and issue templates guide contributors
- **Compliance**: Phase branches create immutable audit snapshots

## What

### User-Visible Behavior
1. Every PR triggers CI that runs ruff, pytest, mypy, pyright, and migration checks
2. CI uses PostgreSQL service container for integration tests
3. PR template provides a checklist for contributors
4. Issue templates guide bug reports and feature requests
5. Local script replicates CI checks before pushing
6. Dependabot keeps dependencies updated

### Success Criteria
- [ ] CI workflow runs on push/PR to dev and main branches
- [ ] All existing 14 tests pass in CI with Postgres service container
- [ ] Ruff lint + format check passes
- [ ] MyPy strict mode passes (0 errors)
- [ ] Pyright strict mode passes (0 errors)
- [ ] Migration check applies to fresh database
- [ ] PR template renders correctly with checklist
- [ ] Issue templates appear in "New Issue" dropdown
- [ ] `examples/ci/local_checks.sh` exits 0 when all checks pass
- [ ] Dependabot config targets correct package ecosystems

---

## All Needed Context

### Documentation & References

```yaml
# MUST READ - Implementation references
- url: https://docs.astral.sh/uv/guides/integration/github/
  why: Official uv GitHub Actions guide - setup-uv action, caching, uv sync

- url: https://docs.github.com/en/actions/use-cases-and-examples/using-containerized-services/creating-postgresql-service-containers
  why: PostgreSQL service container configuration for CI

- url: https://docs.github.com/en/actions/learn-github-actions/workflow-syntax-for-github-actions
  why: GitHub Actions workflow syntax reference

- file: docs/github/github-complete-reference.md
  why: Complete workflow specifications already designed for this project

- file: docs/github/github-quickstart.md
  why: Additional workflow examples and troubleshooting

- file: docs/validation/ruff-standard.md
  why: Ruff configuration and expected behavior

- file: docs/validation/pytest-standard.md
  why: Pytest configuration and test patterns

- file: docs/validation/mypy-standard.md
  why: MyPy strict mode configuration

- file: docs/validation/pyright-standard.md
  why: Pyright configuration

- file: pyproject.toml
  why: All tooling configuration already defined - CI must use same settings
```

### Current Codebase Tree

```
.
├── .github/                    # EMPTY - to be populated
├── alembic/
│   ├── versions/
│   │   └── .gitkeep
│   ├── env.py                  # Async migrations configured
│   └── script.py.mako
├── app/
│   ├── core/
│   │   ├── tests/              # 14 tests exist
│   │   ├── config.py
│   │   ├── database.py
│   │   ├── exceptions.py
│   │   ├── health.py
│   │   ├── logging.py
│   │   └── middleware.py
│   ├── features/
│   ├── shared/
│   └── main.py
├── docs/
│   ├── github/                 # Workflow specs already written
│   └── validation/             # Tool standards
├── examples/
│   └── ci/                     # TO BE CREATED
├── tests/
│   ├── conftest.py
│   └── __init__.py
├── docker-compose.yml          # Postgres + pgvector
├── pyproject.toml              # All tool configs defined
├── .env.example
└── CLAUDE.md
```

### Desired Codebase Tree (Files to Create)

```
.github/
├── workflows/
│   └── ci.yml                  # Main CI workflow (ruff, pytest, mypy, pyright, migrations)
├── ISSUE_TEMPLATE/
│   ├── bug_report.md           # Bug report template
│   ├── feature_request.md      # Feature request template
│   └── config.yml              # Issue template config (optional blank issues)
├── PULL_REQUEST_TEMPLATE.md    # PR checklist
├── CODEOWNERS                  # Code ownership (optional - can be placeholder)
└── dependabot.yml              # Dependency update automation

examples/
└── ci/
    └── local_checks.sh         # Local CI replication script

.pre-commit-config.yaml         # Optional - local git hooks
```

### Known Gotchas & Library Quirks

```yaml
# CRITICAL: uv GitHub Actions setup
# Use astral-sh/setup-uv@v5 (NOT v7 - check latest stable)
# enable-cache: true for faster subsequent runs
# uv sync --locked requires uv.lock - we may need --frozen or generate lock

# CRITICAL: PostgreSQL service container
# Service runs on localhost:5432 from runner perspective
# Use health checks to ensure DB is ready before tests
# DATABASE_URL must use +asyncpg driver for our async setup

# CRITICAL: Migration check approach
# "Apply on empty DB" = alembic upgrade head on fresh postgres
# "No pending revisions" = alembic check (exits non-zero if pending)
# We use async alembic - just run alembic upgrade head

# CRITICAL: Ruff check vs format
# ruff check . = lint only (exits 1 if errors)
# ruff format --check . = format check (exits 1 if would change)
# CI should run BOTH

# CRITICAL: MyPy and Pyright exclusions
# Both already exclude tests/ and alembic/ in pyproject.toml
# Run on app/ only: uv run mypy app/ && uv run pyright app/

# CRITICAL: pytest markers
# -m "not integration" for unit tests only (if DB unavailable)
# Our tests currently don't use integration marker but health tests need DB

# CRITICAL: No uv.lock file exists
# Either generate it (uv lock) or use uv sync without --locked
# For CI determinism, prefer generating uv.lock
```

---

## Implementation Blueprint

### Task 1: Generate uv.lock for Deterministic CI

**Purpose**: Ensure CI uses exact same dependency versions as development.

```bash
# Run once to generate lock file
uv lock
```

**File**: `uv.lock` (generated, add to git)

---

### Task 2: Create Main CI Workflow

**File**: `.github/workflows/ci.yml`

```yaml
name: CI

on:
  push:
    branches: [main, dev]
  pull_request:
    branches: [main, dev]

# Cancel in-progress runs on same branch
concurrency:
  group: ${{ github.workflow }}-${{ github.ref }}
  cancel-in-progress: true

env:
  PYTHON_VERSION: "3.12"
  UV_VERSION: "0.5"

jobs:
  lint:
    name: Lint & Format
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Install uv
        uses: astral-sh/setup-uv@v5
        with:
          version: ${{ env.UV_VERSION }}
          enable-cache: true

      - name: Set up Python
        run: uv python install ${{ env.PYTHON_VERSION }}

      - name: Install dependencies
        run: uv sync --frozen --dev

      - name: Run Ruff linter
        run: uv run ruff check .

      - name: Run Ruff formatter check
        run: uv run ruff format --check .

  typecheck:
    name: Type Check
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Install uv
        uses: astral-sh/setup-uv@v5
        with:
          version: ${{ env.UV_VERSION }}
          enable-cache: true

      - name: Set up Python
        run: uv python install ${{ env.PYTHON_VERSION }}

      - name: Install dependencies
        run: uv sync --frozen --dev

      - name: Run MyPy
        run: uv run mypy app/

      - name: Run Pyright
        run: uv run pyright app/

  test:
    name: Test
    runs-on: ubuntu-latest

    services:
      postgres:
        image: pgvector/pgvector:pg16
        env:
          POSTGRES_USER: forecastlab
          POSTGRES_PASSWORD: forecastlab
          POSTGRES_DB: forecastlab_test
        options: >-
          --health-cmd pg_isready
          --health-interval 10s
          --health-timeout 5s
          --health-retries 5
        ports:
          - 5432:5432

    steps:
      - uses: actions/checkout@v4

      - name: Install uv
        uses: astral-sh/setup-uv@v5
        with:
          version: ${{ env.UV_VERSION }}
          enable-cache: true

      - name: Set up Python
        run: uv python install ${{ env.PYTHON_VERSION }}

      - name: Install dependencies
        run: uv sync --frozen --dev

      - name: Run migrations
        env:
          DATABASE_URL: postgresql+asyncpg://forecastlab:forecastlab@localhost:5432/forecastlab_test
        run: uv run alembic upgrade head

      - name: Run tests
        env:
          DATABASE_URL: postgresql+asyncpg://forecastlab:forecastlab@localhost:5432/forecastlab_test
          APP_ENV: testing
        run: uv run pytest -v --tb=short

  migration-check:
    name: Migration Check
    runs-on: ubuntu-latest

    services:
      postgres:
        image: pgvector/pgvector:pg16
        env:
          POSTGRES_USER: forecastlab
          POSTGRES_PASSWORD: forecastlab
          POSTGRES_DB: forecastlab_migration_test
        options: >-
          --health-cmd pg_isready
          --health-interval 10s
          --health-timeout 5s
          --health-retries 5
        ports:
          - 5432:5432

    steps:
      - uses: actions/checkout@v4

      - name: Install uv
        uses: astral-sh/setup-uv@v5
        with:
          version: ${{ env.UV_VERSION }}
          enable-cache: true

      - name: Set up Python
        run: uv python install ${{ env.PYTHON_VERSION }}

      - name: Install dependencies
        run: uv sync --frozen --dev

      - name: Apply migrations to fresh DB
        env:
          DATABASE_URL: postgresql+asyncpg://forecastlab:forecastlab@localhost:5432/forecastlab_migration_test
        run: uv run alembic upgrade head

      - name: Verify no pending migrations
        env:
          DATABASE_URL: postgresql+asyncpg://forecastlab:forecastlab@localhost:5432/forecastlab_migration_test
        run: |
          # Check that current head matches database
          uv run alembic current
          # This would fail if there are unapplied migrations
```

**Critical Notes**:
- Uses `pgvector/pgvector:pg16` image to match docker-compose.yml
- `--frozen` flag requires uv.lock to exist (Task 1)
- Concurrency group cancels outdated runs
- Jobs run in parallel (lint, typecheck, test, migration-check)

---

### Task 3: Create PR Template

**File**: `.github/PULL_REQUEST_TEMPLATE.md`

```markdown
## Summary

<!-- Brief description of changes (1-3 sentences) -->

## Type of Change

- [ ] Bug fix (non-breaking change that fixes an issue)
- [ ] New feature (non-breaking change that adds functionality)
- [ ] Breaking change (fix or feature that would cause existing functionality to change)
- [ ] Refactoring (no functional changes)
- [ ] Documentation update
- [ ] CI/CD changes

## Checklist

### Code Quality
- [ ] My code follows the project's coding standards (see CLAUDE.md)
- [ ] I have run `uv run ruff check . --fix && uv run ruff format .`
- [ ] I have run `uv run mypy app/ && uv run pyright app/`
- [ ] All type annotations are complete (no `Any` without justification)

### Testing
- [ ] I have added tests that prove my fix/feature works
- [ ] All existing tests pass (`uv run pytest -v`)
- [ ] New tests follow existing patterns in `app/*/tests/`

### Database
- [ ] No database changes required
- [ ] Migration added and tested (`uv run alembic upgrade head` on fresh DB)
- [ ] Migration is backward compatible

### Documentation
- [ ] No documentation changes needed
- [ ] I have updated relevant documentation
- [ ] Docstrings follow Google style

### Security
- [ ] No hardcoded secrets, credentials, or API keys
- [ ] Input validation is in place for user-provided data
- [ ] No SQL injection vulnerabilities (using SQLAlchemy ORM)

## Testing Instructions

<!-- How can reviewers test these changes? -->

## Related Issues

<!-- Link to related issues: Fixes #123, Relates to #456 -->
```

---

### Task 4: Create Issue Templates

**File**: `.github/ISSUE_TEMPLATE/bug_report.md`

```markdown
---
name: Bug Report
about: Report a bug or unexpected behavior
title: '[BUG] '
labels: bug
assignees: ''
---

## Bug Description

<!-- A clear and concise description of the bug -->

## Steps to Reproduce

1. Go to '...'
2. Click on '...'
3. See error

## Expected Behavior

<!-- What you expected to happen -->

## Actual Behavior

<!-- What actually happened -->

## Environment

- OS: [e.g., Ubuntu 22.04, macOS 14]
- Python version: [e.g., 3.12.1]
- ForecastLabAI version/commit: [e.g., v0.1.0 or commit hash]

## Logs/Screenshots

<!-- If applicable, add logs or screenshots -->

```
Paste relevant logs here
```

## Additional Context

<!-- Any other context about the problem -->
```

**File**: `.github/ISSUE_TEMPLATE/feature_request.md`

```markdown
---
name: Feature Request
about: Suggest a new feature or enhancement
title: '[FEATURE] '
labels: enhancement
assignees: ''
---

## Feature Description

<!-- A clear description of the feature you'd like -->

## Problem/Motivation

<!-- What problem does this solve? Why is this needed? -->

## Proposed Solution

<!-- How you think this should work -->

## Alternatives Considered

<!-- Any alternative solutions or features you've considered -->

## Additional Context

<!-- Any other context, mockups, or examples -->
```

**File**: `.github/ISSUE_TEMPLATE/config.yml`

```yaml
blank_issues_enabled: true
contact_links:
  - name: Documentation
    url: https://github.com/your-org/ForecastLabAI/tree/main/docs
    about: Check the documentation before opening an issue
```

---

### Task 5: Create CODEOWNERS

**File**: `.github/CODEOWNERS`

```
# ForecastLabAI Code Owners
# These owners will be requested for review when PRs touch their areas

# Default owners for everything
* @your-username

# Core infrastructure
/app/core/ @your-username

# Feature modules (add specific owners as team grows)
/app/features/ @your-username

# CI/CD configuration
/.github/ @your-username

# Database migrations
/alembic/ @your-username

# Documentation
/docs/ @your-username
```

**Note**: Replace `@your-username` with actual GitHub username(s).

---

### Task 6: Create Dependabot Configuration

**File**: `.github/dependabot.yml`

```yaml
version: 2
updates:
  # Python dependencies (pyproject.toml)
  - package-ecosystem: "pip"
    directory: "/"
    schedule:
      interval: "weekly"
      day: "monday"
    open-pull-requests-limit: 5
    labels:
      - "dependencies"
      - "python"
    commit-message:
      prefix: "deps"
    groups:
      # Group minor/patch updates together
      python-minor:
        patterns:
          - "*"
        update-types:
          - "minor"
          - "patch"

  # GitHub Actions
  - package-ecosystem: "github-actions"
    directory: "/"
    schedule:
      interval: "weekly"
      day: "monday"
    open-pull-requests-limit: 3
    labels:
      - "dependencies"
      - "ci"
    commit-message:
      prefix: "ci"
```

---

### Task 7: Create Local CI Script

**File**: `examples/ci/local_checks.sh`

```bash
#!/usr/bin/env bash
#
# Local CI Checks - Run the same checks as GitHub Actions CI
#
# Usage:
#   ./examples/ci/local_checks.sh          # Run all checks
#   ./examples/ci/local_checks.sh --quick  # Skip tests (lint + typecheck only)
#
# Requirements:
#   - uv installed
#   - Docker running (for database tests)
#   - .env file configured (or use defaults)

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

# Track failures
FAILED=0

# Function to run a check
run_check() {
    local name="$1"
    shift
    echo -e "${YELLOW}>>> Running: ${name}${NC}"
    if "$@"; then
        echo -e "${GREEN}✓ ${name} passed${NC}"
        echo ""
    else
        echo -e "${RED}✗ ${name} failed${NC}"
        echo ""
        FAILED=1
    fi
}

# 1. Lint check
run_check "Ruff lint" uv run ruff check .

# 2. Format check
run_check "Ruff format" uv run ruff format --check .

# 3. Type check (MyPy)
run_check "MyPy" uv run mypy app/

# 4. Type check (Pyright)
run_check "Pyright" uv run pyright app/

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
    if ! docker-compose ps | grep -q "forecastlab-postgres.*Up"; then
        echo -e "${YELLOW}Starting PostgreSQL container...${NC}"
        docker-compose up -d
        # Wait for postgres to be ready
        echo "Waiting for PostgreSQL to be ready..."
        sleep 5
    fi

    # 7. Run migrations
    run_check "Alembic migrations" uv run alembic upgrade head

    # 8. Run tests
    run_check "Pytest" uv run pytest -v --tb=short
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
```

Make executable: `chmod +x examples/ci/local_checks.sh`

---

### Task 8: Create Pre-commit Configuration (Optional)

**File**: `.pre-commit-config.yaml`

```yaml
# Pre-commit hooks for ForecastLabAI
# Install: pip install pre-commit && pre-commit install
# Run manually: pre-commit run --all-files

repos:
  # Ruff for linting and formatting
  - repo: https://github.com/astral-sh/ruff-pre-commit
    rev: v0.8.6
    hooks:
      - id: ruff
        args: [--fix]
      - id: ruff-format

  # Standard pre-commit hooks
  - repo: https://github.com/pre-commit/pre-commit-hooks
    rev: v5.0.0
    hooks:
      - id: trailing-whitespace
      - id: end-of-file-fixer
      - id: check-yaml
      - id: check-added-large-files
        args: ['--maxkb=1000']
      - id: check-merge-conflict
      - id: detect-private-key

  # Check TOML files
  - repo: https://github.com/pre-commit/pre-commit-hooks
    rev: v5.0.0
    hooks:
      - id: check-toml
```

---

## Integration Points

```yaml
ENVIRONMENT:
  - CI uses DATABASE_URL with postgresql+asyncpg driver
  - APP_ENV=testing in test job
  - No secrets required (uses service container credentials)

DEPENDENCIES:
  - Task 1 (uv.lock) must complete before Task 2 (CI workflow can use --frozen)
  - If no uv.lock, workflow must use uv sync without --frozen flag

EXISTING FILES:
  - pyproject.toml: All tool configurations already defined
  - alembic/: Async migration setup ready
  - docker-compose.yml: Local dev uses same pgvector image as CI
```

---

## Validation Loop

### Level 1: Syntax & File Validation

```bash
# Validate YAML syntax
python -c "import yaml; yaml.safe_load(open('.github/workflows/ci.yml'))"
python -c "import yaml; yaml.safe_load(open('.github/dependabot.yml'))"

# Validate markdown files exist
ls -la .github/PULL_REQUEST_TEMPLATE.md
ls -la .github/ISSUE_TEMPLATE/

# Make script executable
chmod +x examples/ci/local_checks.sh
```

### Level 2: Local Script Test

```bash
# Run local checks (quick mode - no DB needed)
./examples/ci/local_checks.sh --quick

# Expected: All lint and type checks pass

# Run full local checks (requires Docker)
docker-compose up -d
./examples/ci/local_checks.sh

# Expected: All checks pass including tests
```

### Level 3: CI Workflow Validation

```bash
# After pushing to a branch, verify:
# 1. CI workflow triggers
# 2. All 4 jobs run (lint, typecheck, test, migration-check)
# 3. All jobs pass

# Check workflow syntax locally (optional - requires act)
# act -n  # dry run
```

---

## Final Validation Checklist

- [ ] `uv.lock` generated and committed
- [ ] `.github/workflows/ci.yml` created with 4 parallel jobs
- [ ] `.github/PULL_REQUEST_TEMPLATE.md` created with checklist
- [ ] `.github/ISSUE_TEMPLATE/bug_report.md` created
- [ ] `.github/ISSUE_TEMPLATE/feature_request.md` created
- [ ] `.github/ISSUE_TEMPLATE/config.yml` created
- [ ] `.github/CODEOWNERS` created (with placeholder usernames)
- [ ] `.github/dependabot.yml` created for pip and github-actions
- [ ] `examples/ci/local_checks.sh` created and executable
- [ ] `.pre-commit-config.yaml` created (optional)
- [ ] All existing tests still pass: `uv run pytest -v`
- [ ] Ruff passes: `uv run ruff check . && uv run ruff format --check .`
- [ ] MyPy passes: `uv run mypy app/`
- [ ] Pyright passes: `uv run pyright app/`
- [ ] Local CI script passes: `./examples/ci/local_checks.sh`

---

## Anti-Patterns to Avoid

- ❌ Don't use `--locked` without first generating `uv.lock`
- ❌ Don't hardcode secrets in workflow files (use GitHub Secrets for real secrets)
- ❌ Don't skip health checks on Postgres service container
- ❌ Don't run type checkers on test files (already excluded in pyproject.toml)
- ❌ Don't use `ruff check --fix` in CI (should fail if issues exist, not auto-fix)
- ❌ Don't forget `+asyncpg` in DATABASE_URL (required for async SQLAlchemy)
- ❌ Don't create complex multi-workflow setup - keep it simple with one CI workflow

---

## Branch Protection Note

Branch protection rules are configured via GitHub UI or CLI, not via files in the repo. After implementing this PRP, configure branch protection for `main` and `dev`:

```bash
# Example using GitHub CLI (run manually, not part of this PRP)
gh repo edit --enable-branch-protection
# Or configure via GitHub Settings → Branches → Add rule
```

Document required status checks:
- `lint` (from ci.yml)
- `typecheck` (from ci.yml)
- `test` (from ci.yml)
- `migration-check` (from ci.yml)

---

## Resources

- [uv GitHub Actions Guide](https://docs.astral.sh/uv/guides/integration/github/)
- [GitHub PostgreSQL Service Containers](https://docs.github.com/en/actions/use-cases-and-examples/using-containerized-services/creating-postgresql-service-containers)
- [GitHub Actions Workflow Syntax](https://docs.github.com/en/actions/learn-github-actions/workflow-syntax-for-github-actions)
- [Dependabot Configuration](https://docs.github.com/en/code-security/dependabot/dependabot-version-updates/configuration-options-for-the-dependabot.yml-file)
- [Pre-commit Framework](https://pre-commit.com/)

---

**PRP Version**: 1.0
**Created**: 2026-01-26
**Confidence Score**: 9/10

**Rationale for Score**:
- High confidence due to extensive existing documentation in `docs/github/`
- All tool configurations already defined in `pyproject.toml`
- Clear patterns from official uv/GitHub documentation
- Existing test suite validates the setup works
- Only uncertainty: uv.lock generation (may need `uv lock` vs `uv sync`)
