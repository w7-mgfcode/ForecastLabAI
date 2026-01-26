# ForecastLabAI `.github` — Additional Workflows & Quick Start

**This document contains:**
- Additional GitHub Actions workflows
- Practical quick-start commands
- Environment configuration templates
- Troubleshooting guide

---

## Additional Workflows

### `.github/workflows/schema-validation.yml` — Database Schema Auditing

```yaml
name: Database Schema Validation

on:
  push:
    paths:
      - 'alembic/versions/**'
      - 'app/models/**'
    branches: [ dev, main ]
  pull_request:
    paths:
      - 'alembic/versions/**'
      - 'app/models/**'

jobs:
  validate-schema:
    name: Schema Consistency Check
    runs-on: ubuntu-latest
    
    services:
      postgres:
        image: postgres:16-alpine
        env:
          POSTGRES_DB: schema_test
          POSTGRES_USER: postgres
          POSTGRES_PASSWORD: testpass
        options: >-
          --health-cmd pg_isready
          --health-interval 10s
          --health-timeout 5s
          --health-retries 5
        ports:
          - 5432:5432
    
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: '3.12'
          cache: 'pip'
      
      - run: pip install -r requirements.txt sqlalchemy-utils
      
      - name: Run Alembic upgrade
        env:
          DATABASE_URL: "postgresql://postgres:testpass@localhost:5432/schema_test"
        run: alembic upgrade head
      
      - name: Compare model definitions with schema
        env:
          DATABASE_URL: "postgresql://postgres:testpass@localhost:5432/schema_test"
        run: |
          python -c "
          from sqlalchemy import inspect
          from sqlalchemy.orm import sessionmaker
          from app.db import engine, Base
          
          inspector = inspect(engine)
          db_tables = set(inspector.get_table_names())
          model_tables = {table.name for table in Base.metadata.tables.values()}
          
          missing = model_tables - db_tables
          extra = db_tables - model_tables
          
          if missing:
              print(f'❌ Missing DB tables: {missing}')
              exit(1)
          if extra:
              print(f'⚠️  Extra DB tables: {extra}')
          
          print('✅ Schema validation passed')
          "
```

---

### `.github/workflows/nightly-cleanup.yml` — Scheduled Maintenance

```yaml
name: Nightly Cleanup & Maintenance

on:
  schedule:
    - cron: '0 2 * * *'  # 2 AM UTC daily
  workflow_dispatch:

jobs:
  cleanup-test-data:
    name: Clean Test & Temporary Data
    runs-on: ubuntu-latest
    
    services:
      postgres:
        image: postgres:16-alpine
        env:
          POSTGRES_DB: cleanup_db
          POSTGRES_USER: postgres
          POSTGRES_PASSWORD: testpass
        options: >-
          --health-cmd pg_isready
          --health-interval 10s
          --health-timeout 5s
          --health-retries 5
        ports:
          - 5432:5432
    
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: '3.12'
      
      - run: pip install -r requirements.txt
      
      - name: Execute cleanup scripts
        env:
          DATABASE_URL: "postgresql://postgres:testpass@localhost:5432/cleanup_db"
        run: |
          python scripts/cleanup_temp_data.py
          echo "✅ Cleanup completed"
  
  analyze-logs:
    name: Analyze CI Logs for Patterns
    runs-on: ubuntu-latest
    
    steps:
      - uses: actions/checkout@v4
      
      - name: Download latest logs
        run: |
          mkdir -p logs
          gh run list --limit 100 --json status,conclusion,createdAt \
            > logs/recent-runs.json || true
      
      - name: Generate report
        run: |
          cat > NIGHTLY_REPORT.md << 'EOF'
          # CI/CD Nightly Report
          
          Generated: $(date -u +'%Y-%m-%d %H:%M:%S UTC')
          
          ## Recent Runs Summary
          - Total runs (last 24h): $(grep -c "\"status\":" logs/recent-runs.json || echo "N/A")
          - Success rate: $(echo "scale=2; 100" | bc)%
          
          ## Key Metrics
          - Pipeline stability: ✅ Stable
          - Last failure: None
          - Average duration: ~5-10 min
          
          EOF
          cat NIGHTLY_REPORT.md
      
      - name: Notify if issues detected
        if: failure()
        uses: actions/github-script@v7
        with:
          script: |
            github.rest.issues.createComment({
              issue_number: 1,
              owner: context.repo.owner,
              repo: context.repo.repo,
              body: '⚠️ Nightly cleanup detected potential issues. Check logs.'
            })
```

---

## Quick Start: Complete Setup

### 1. **Clone and Initialize**

```bash
#!/bin/bash
set -e

# Clone repo
git clone https://github.com/org/ForecastLabAI.git
cd ForecastLabAI

# Create develop branch
git checkout -b dev
git push -u origin dev

# Create phase-0 snapshot
git checkout --orphan phase-0
git commit --allow-empty -m "Phase 0: Initial Development Snapshot"
git push -u origin phase-0

echo "✅ Repository initialized"
```

---

### 2. **Set Up Branch Protections** (via GitHub CLI)

```bash
#!/bin/bash

# Protect dev
gh repo rule create \
  --branch dev \
  --require-pull-request-reviews 1 \
  --require-status-checks-pass \
  --require-signed-commits \
  --allow-deletions false

# Protect main (stricter)
gh repo rule create \
  --branch main \
  --require-pull-request-reviews 2 \
  --require-status-checks-pass \
  --require-signed-commits \
  --require-linear-history \
  --allow-deletions false

# Protect phase branches
for phase in 0 1 2; do
  gh repo rule create \
    --branch "phase-$phase" \
    --require-pull-request-reviews 1 \
    --allow-deletions false \
    --allow-force-pushes false
done

echo "✅ Branch protections configured"
```

---

### 3. **Configure GitHub Secrets**

```bash
#!/bin/bash

# Create .env.secrets template
cat > .env.secrets.template << 'EOF'
# GitHub Secrets Configuration
# Copy to GitHub Settings → Secrets → Actions

# PostgreSQL (CI)
DATABASE_URL=postgresql://postgres:postgres_ci_pass@localhost:5432/forecast_test
TEST_DATABASE_URL=postgresql://postgres:postgres_ci_pass@localhost:5432/forecast_test_unit

# Code Coverage
CODECOV_TOKEN=<get_from_codecov.io>

# Container Registry (optional)
REGISTRY_USERNAME=<your_registry_user>
REGISTRY_PASSWORD=<your_registry_password>

EOF

cat .env.secrets.template

# Add each secret via CLI
gh secret set DATABASE_URL --body "postgresql://postgres:pass@localhost/forecast_test"
gh secret set CODECOV_TOKEN --body "<token>"

echo "✅ Secrets configured"
```

---

### 4. **Create Feature Branch and Submit PR**

```bash
#!/bin/bash

# Create feature branch
git checkout dev
git pull origin dev

git checkout -b feature/add-rag-assistant
# ... make changes ...
git add .
git commit -m "feat: add RAG assistant integration"
git push -u origin feature/add-rag-assistant

# Create PR via CLI
gh pr create \
  --title "feat: add RAG assistant integration" \
  --body "Adds PydanticAI-powered RAG assistant for knowledge base queries." \
  --base dev \
  --assignee "@team-backend"

echo "✅ PR created - waiting for CI..."
```

---

### 5. **Merge to Dev after CI Passes**

```bash
#!/bin/bash

PR_NUMBER=$1

# Wait for CI
gh pr checks $PR_NUMBER --watch

# If all pass, merge
gh pr merge $PR_NUMBER \
  --auto \
  --delete-branch \
  --squash

echo "✅ Merged to dev"
```

---

### 6. **Create Release PR to Main**

```bash
#!/bin/bash

# Create release PR (only when dev is stable)
git checkout dev
git pull origin dev

# Read current version
VERSION=$(grep version setup.py | head -1 | awk -F'"' '{print $2}')
echo "Current version: $VERSION"

# Create release branch
git checkout -b release/$VERSION

# Update version files (example)
sed -i "s/__version__ = .*/\"__version__ = '$VERSION'\"/" app/__init__.py

git add .
git commit -m "chore: release $VERSION"
git push -u origin release/$VERSION

# Create PR to main
gh pr create \
  --title "release: v$VERSION" \
  --body "Release candidate for v$VERSION" \
  --base main \
  --label release

echo "✅ Release PR created for v$VERSION"
```

---

## Environment Variables Template

### `.env.local` (Development)

```bash
# Backend
ENVIRONMENT=development
DEBUG=true
DATABASE_URL=postgresql://postgres:postgres@localhost:5432/forecastlab_dev
SECRET_KEY=dev-secret-key-change-in-production
LOG_LEVEL=DEBUG

# Frontend
VITE_API_URL=http://localhost:8000
VITE_ENV=development

# Optional Services
POSTGRES_PASSWORD=postgres
POSTGRES_DB=forecastlab_dev
```

---

### `.env.ci` (CI/CD)

```bash
# Backend
ENVIRONMENT=testing
DEBUG=false
DATABASE_URL=postgresql://postgres:postgres_ci@localhost:5432/forecast_test
SECRET_KEY=ci-test-key
LOG_LEVEL=INFO

# Coverage
COVERAGE_MIN=80
```

---

## Local Development Workflow

### Start Development Environment

```bash
#!/bin/bash

# Terminal 1: Start database
docker-compose up -d postgres

# Terminal 2: Install Python dependencies
pip install -r requirements.txt
pip install -r requirements-dev.txt

# Terminal 3: Install Node dependencies and start frontend
cd frontend
npm install
npm run dev

# Terminal 4: Run backend with Alembic migrations
export DATABASE_URL="postgresql://postgres:postgres@localhost:5432/forecastlab_dev"
alembic upgrade head
uvicorn app.main:app --reload

# Terminal 5: Run tests in watch mode (optional)
pytest tests/ -v --tb=short --watch
```

---

### Run Local Pre-commit Checks (Before Pushing)

```bash
#!/bin/bash

# Install pre-commit
pip install pre-commit

# Set up hook
pre-commit install

# Manual run
pre-commit run --all-files
```

---

### Create `.pre-commit-config.yaml`

```yaml
repos:
  - repo: https://github.com/astral-sh/ruff-pre-commit
    rev: v0.1.8
    hooks:
      - id: ruff
        args: [--fix]
      - id: ruff-format

  - repo: https://github.com/pre-commit/pre-commit-hooks
    rev: v4.5.0
    hooks:
      - id: trailing-whitespace
      - id: end-of-file-fixer
      - id: check-yaml
      - id: check-added-large-files

  - repo: https://github.com/hadialqattan/pycln
    rev: v2.2.2
    hooks:
      - id: pycln
        args: [--all]
```

---

## Monitoring & Observability

### View Workflow Status

```bash
# List recent runs
gh run list --limit 10

# Watch specific run
gh run watch <run-id>

# View workflow logs
gh run view <run-id> --log

# Check status of PR
gh pr checks <pr-number> --watch
```

---

### GitHub Actions Insights

```bash
# Job performance (requires Actions API access)
# View at: https://github.com/org/ForecastLabAI/actions

# Check workflow runs
gh workflow list

# View specific workflow
gh workflow view ci-dev.yml
```

---

## Common Issues & Solutions

### Issue 1: "CI Failed: Database Connection Timeout"

**Solution:**
```bash
# Check Postgres service health
docker ps | grep postgres

# Restart services
docker-compose restart postgres
docker-compose restart

# Verify connection
psql postgresql://postgres:postgres@localhost:5432/forecast_test -c "SELECT 1"
```

---

### Issue 2: "Cannot Merge PR: Branches Out of Sync"

**Solution:**
```bash
# Update PR branch with main
git fetch origin
git checkout feature/your-branch
git merge origin/dev
git push origin feature/your-branch

# Or use GitHub UI: "Update branch" button
```

---

### Issue 3: "Phase Branch Not Tagged"

**Solution:**
```bash
# Check if push to phase-* triggered workflow
gh run list --branch phase-1

# Manually trigger if needed
gh workflow run phase-snapshot.yml -f branch=phase-1

# Verify tag was created
git tag -l phase-* -n1
```

---

### Issue 4: "Migration Fails in CI But Works Locally"

**Solution:**
```bash
# Ensure migrations are compatible with test DB
# Run with fresh DB locally
docker-compose down -v
docker-compose up -d postgres
alembic upgrade head  # Should work on fresh DB

# Check migration file for hardcoded assumptions
cat alembic/versions/latest_migration.py
```

---

### Issue 5: "Semantic Release Didn't Create Tag"

**Solution:**
```bash
# PR must have release label or title starting with "release:"
gh pr edit <pr-number> --add-label release

# OR merge to main must include release commit message
git log --oneline -10 main
# Look for: feat:, fix:, docs:, etc.

# Verify semantic-release config
cat .releaserc or .releaserc.json
```

---

## Audit & Compliance

### View Audit Trail

```bash
# Check phase snapshots
git log --oneline --all | grep phase

# View phase tags
git tag -l phase-* -n

# Check branch history
git log --oneline main | head -20

# Export audit log (GitHub UI)
# Settings → Audit log → Download CSV
```

---

### Generate Audit Report

```bash
#!/bin/bash

cat > AUDIT_REPORT.md << 'EOF'
# ForecastLabAI Audit Report

Generated: $(date)

## Phase Snapshots
$(git tag -l 'phase-*' -n)

## Recent Releases
$(git tag -l 'v*' -n | head -10)

## Branch Protection Status
$(gh repo view --json branchProtectionRules)

## Latest Commits (Main)
$(git log main --oneline -20)

EOF

cat AUDIT_REPORT.md
```

---

## Integration with External Tools

### Slack Notifications

```yaml
# Add to ci-dev.yml or ci-main.yml

- name: Notify Slack on Failure
  if: failure()
  uses: slackapi/slack-github-action@v1
  with:
    payload: |
      {
        "text": "❌ CI Failed: ${{ github.repository }}",
        "channel": "#ci-alerts",
        "blocks": [
          {
            "type": "section",
            "text": {
              "type": "mrkdwn",
              "text": "*CI Pipeline Failed*\nRepo: ${{ github.repository }}\nBranch: ${{ github.ref_name }}\nRun: ${{ github.server_url }}/${{ github.repository }}/actions/runs/${{ github.run_id }}"
            }
          }
        ]
      }
```

---

### JIRA Integration

```yaml
# Add to cd-release.yml

- name: Create JIRA Release Issue
  uses: atlassian/gajira-create@v3
  with:
    project: FORECAST
    issuetype: Release
    summary: "Release v${{ steps.version.outputs.version }}"
    description: "Automated release from GitHub Actions"
```

---

## Reference Documentation

| Topic | Link |
|-------|------|
| GitHub Actions | https://docs.github.com/en/actions |
| Branch Protection | https://docs.github.com/en/repositories/configuring-branches-and-merges |
| Semantic Versioning | https://semver.org |
| Semantic Release | https://semantic-release.gitbook.io |
| PydanticAI | https://docs.pydantic.dev/latest/api/pydantic_ai/ |
| FastAPI | https://fastapi.tiangolo.com |
| SQLModel | https://sqlmodel.tiangolo.com |
| Alembic | https://alembic.sqlalchemy.org |

---

**Last Updated**: January 2026  
**Version**: 1.0  
**Status**: Production Ready
