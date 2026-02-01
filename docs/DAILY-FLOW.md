# Daily Development Flow

A napi fejlesztési munkafolyamat a ForecastLabAI projekthez.

---

## Branch Stratégia

```
main (protected)     <- Production releases only
  │
  └── dev            <- Integration branch
        │
        └── feat/*   <- Feature branches
```

---

## Napi Fejlesztési Ciklus

### 1. Munka Kezdése

```bash
# Frissítsd a dev branchet
git checkout dev
git pull origin dev

# Hozz létre feature branchet
git checkout -b feat/prp-X-feature-name
```

### 2. Fejlesztés Közben

```bash
# Rendszeres commitok
git add <files>
git commit -m "feat(module): description"

# Lokális ellenőrzések
uv run ruff check .
uv run ruff format .
uv run mypy app/
uv run pyright app/
uv run pytest -v
```

### 3. PR Létrehozása

```bash
# Push feature branch
git push origin feat/prp-X-feature-name

# PR létrehozása dev-be
gh pr create --base dev --title "feat(module): description" --body "..."
```

### 4. CI Ellenőrzések

A PR-nek át kell mennie:
- [ ] Lint & Format
- [ ] Type Check (MyPy + Pyright)
- [ ] Test
- [ ] Migration Check
- [ ] Code Review (Sourcery, CodeRabbit)

### 5. Merge to Dev

```bash
# Review után merge
gh pr merge <PR_NUMBER> --squash --delete-branch
```

---

## Dev → Main Merge (Feature Complete)

Amikor egy feature teljesen kész:

```bash
# Checkout dev
git checkout dev
git pull origin dev

# PR létrehozása main-be
gh pr create --base main --head dev --title "feat(module): merge feature to main"

# CI ellenőrzések után merge
gh pr merge <PR_NUMBER> --squash
```

---

## Release Flow

A `main` branch-re történő merge után a `release-please` automatikusan:
1. Létrehoz egy Release PR-t (version bump + CHANGELOG)
2. CI lefut a Release PR-en
3. Merge után GitHub Release + tag jön létre

```bash
# Release PR ellenőrzése
gh pr list --label "autorelease: pending"

# CI trigger ha szükséges
git checkout <release-branch>
git commit --allow-empty -m "chore: trigger CI"
git push

# Merge release PR
gh pr merge <PR_NUMBER> --squash --delete-branch
```

---

## Commit Message Konvenció

```
<type>(<scope>): <description>

Types:
- feat:     Új feature
- fix:      Bug fix
- docs:     Dokumentáció
- refactor: Refaktorálás
- test:     Teszt hozzáadás/módosítás
- chore:    Build, CI, dependencies

Scope (opcionális):
- data-platform
- ingest
- forecasting
- backtesting
- registry
- rag
- dashboard
```

---

## Gyors Parancsok

```bash
# Status check
git status && git log --oneline -5

# Lint + format
uv run ruff check --fix . && uv run ruff format .

# Type check
uv run mypy app/ && uv run pyright app/

# Tesztek
uv run pytest -v
uv run pytest -v -m integration  # DB szükséges

# PR checks
gh pr checks <PR_NUMBER>

# Watch workflow
gh run watch <RUN_ID>
```

---

## Következő Phases (INITIAL-9 → INITIAL-11)

A projekt a moduláris három-fázisú roadmap szerint halad:

```
Phase 8: RAG Knowledge Base ("The Memory")
         ↓
Phase 9: Agentic Layer ("The Brain")
         ↓
Phase 10: ForecastLab Dashboard ("The Face")
```

### Phase 8: RAG Knowledge Base (INITIAL-9)
- pgvector embeddings + semantic retrieval
- Markdown/OpenAPI chunking
- POST /rag/index, POST /rag/retrieve endpoints

### Phase 9: Agentic Layer (INITIAL-10)
- PydanticAI agents (Experiment Orchestrator, RAG Assistant)
- Tool orchestration + structured outputs
- WebSocket streaming

### Phase 10: Dashboard (INITIAL-11)
- React 19 + Vite + shadcn/ui
- Data tables + time series charts
- Agent chat interface
