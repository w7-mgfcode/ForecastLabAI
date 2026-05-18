# INITIAL-14 — End-to-End Demo Pipeline + Showcase Script PRD

**Author:** Gabor Szabo (drafted via `/do:prd` session, 2026-05-14)
**Status:** Draft
**Date:** 2026-05-14
**Predecessor:** v0.2.9 (Phase-2 seeder + features complete, queue empty)
**Successor:** `PRPs/PRP-15-e2e-demo-pipeline.md` (to be authored)

---

## Problem Statement

ForecastLabAI is a portfolio-grade, single-host retail demand forecasting demo (`.claude/rules/product-vision.md`). Its value to a reviewer depends on **one-command demonstrability**. Today that gate is broken:

- `examples/e2e_smoke.sh` is **53 lines** and asserts only `/health` and `X-Request-ID` propagation. It does **not** exercise the pipeline.
- A reviewer (or returning maintainer) must hand-compose ~8 sequential HTTP calls across the 12 routers wired in `app/main.py` to see the system work end-to-end.
- Phase-2 seeder + featureset work shipped over PRs #111/#112/#114/#115/#127 (v0.2.9) — but `grep -rn "lifecycle\|replenishment\|promotion\|days_since_launch" app/features/forecasting/ app/features/backtesting/` returns zero hits, so the new columns currently have no visible exit channel. The investment looks invisible from outside.
- The open-issue queue is empty (`gh issue list --state open` → `[]`), so there's no external pull on the next thing to ship — this is a clean inflection-point moment.

**Who is affected:** the maintainer (portfolio reviewers, future contributors), and any operator returning to the repo after a multi-week absence. **Pain if unsolved:** the repo's perceived completeness lags its actual completeness; future seeder/feature work compounds the problem.

---

## Goals

- **Primary:** A single command, `make demo`, drives the full pipeline against a freshly-seeded dataset and returns exit code 0 with a green verdict in **≤ 180 s wall-clock** on the developer's laptop (Postgres + uvicorn already running).
- **Secondary:**
  - Establish a canonical scripted reference for `seed → ingest → features → forecast → backtest → registry → alias → agent-query` ordering, suitable for embedding in `README.md`.
  - Surface integration failures (CORS, env-bleed, missing API keys, schema drift) in a single output stream, so the maintainer doesn't have to recreate them from memory.
  - Provide the foundation that a future "Run demo" dashboard button (out of scope here) can call into.
- **Non-goals:**
  - Phase-2-aware LightGBM training (separate PRP — depends on this slice).
  - Dashboard UI changes ("Run demo" button is a follow-up).
  - Performance benchmarking (correctness-only).
  - Replacing or extending the seeder/scenario surface.
  - CI nightly integration (deferred — promote once 2 weeks flake-free locally).
  - Exercising the `rag_assistant` agent (requires pre-indexed corpus; deferred to v2).

---

## Proposed Solution

A self-contained Python script, `scripts/run_demo.py`, invoked via `make demo`, that drives the existing FastAPI surface from outside the process using `httpx.AsyncClient`. The script is intentionally **not** a feature of `app/` — it sits at the same level as `scripts/seed_random.py` and `scripts/check_db.py`, treats the API as a black box, and composes published endpoints from `docs/_base/API_CONTRACTS.md`.

**Key design decisions:**

| Decision | Rationale |
|----------|-----------|
| Drive via HTTP (not in-process calls) | Validates the *deployed* contract; matches what a reviewer sees. Also catches CORS / middleware regressions. |
| Naive + seasonal_naive + moving_average baselines only | Already implemented (`app/features/forecasting/service.py`); avoids Phase-2-column dependency that needs its own PRP. LightGBM is a follow-up. |
| Deterministic seed (`--seed 42`) | Reproducible across runs; satisfies acceptance criterion #4. |
| `expanding` backtest split, 3 folds, h=14 days | Tight enough to stay inside the 180-s budget on a laptop. |
| Output via `.claude/rules/output-formatting.md` glyphs (✅/❌/🔄) | Matches house style; visually scannable; capped at 40 lines. |
| `--quiet` flag emits one line per step | CI / log capture friendly. |
| Single-file script, no new Python package | Mirrors `scripts/check_db.py` shape; no test-import overhead. |
| `make demo-quick` skips the seed step | Iteration ergonomics when DB state is fresh. |

**Alternatives considered and rejected:**

- *In-process driver invoking router functions directly.* Rejected: bypasses middleware/CORS, defeats the demo-trust purpose.
- *Promote the demo to a new `app/features/demo/` slice with its own router.* Rejected: violates the vertical-slice rule (would import across slices) and adds API surface for a one-shot operator action.
- *Bash-only script with curl/jq.* Rejected: error handling and JSON path extraction across 8+ steps become brittle; the existing `examples/e2e_smoke.sh` shape doesn't scale to this length.

---

## User Experience

### CLI Changes

**New top-level `Makefile` (does not exist today):**

```makefile
.PHONY: demo demo-quick demo-clean

demo:                ## full e2e: seed → ingest → features → train → backtest → register → alias → agent-query
	uv run python scripts/run_demo.py --seed 42

demo-quick:          ## same flow but skips the seeder reset; assumes data is fresh
	uv run python scripts/run_demo.py --seed 42 --skip-seed

demo-clean:          ## destructive: wipe DB then run demo
	uv run python scripts/run_demo.py --seed 42 --reset
```

**New CLI: `scripts/run_demo.py`**

```
usage: run_demo.py [-h] [--seed INT] [--skip-seed] [--reset] [--quiet]
                   [--api-url URL] [--timeout SECS]

options:
  --seed INT       Deterministic seed for the seeder (default: 42)
  --skip-seed      Skip the seeder scenario step (assumes data already present)
  --reset          Run the seeder's --delete --full-new path before seeding (destructive)
  --quiet          One-line-per-step output (default: verbose with progress)
  --api-url URL    Override the default http://localhost:8123
  --timeout SECS   Per-step HTTP timeout (default: 30)
```

**Exit codes:** `0` on success, `1` on any step failure, `2` on precondition failure (API unreachable, DB down).

### API Changes

**None.** The script consumes existing endpoints documented in `docs/_base/API_CONTRACTS.md`:

| Step | Endpoint | Purpose |
|------|----------|---------|
| 1 | `GET /health` | Precondition check |
| 2 | `POST /seeder/...` (route per `app/features/seeder/routes.py:85`) | Trigger `retail_standard` scenario with `--seed 42` |
| 3 | `GET /seeder/...status` | Poll until complete |
| 4 | `POST /featuresets/compute` | Compute lag + rolling + calendar features |
| 5 | `POST /jobs` × 3 | Submit `train` jobs for naive / seasonal_naive / moving_average |
| 6 | `GET /jobs/{id}` | Poll each until `status=success`, capture `run_id` |
| 7 | `POST /backtesting/run` | 3-fold expanding split, horizon 14 |
| 8 | `POST /registry/aliases` | Alias winning run as `demo-production` |
| 9 | `GET /registry/runs/{id}/verify` | SHA-256 artifact integrity check |
| 10 | `POST /agents/sessions` | Open `experiment` agent session |
| 11 | `POST /agents/sessions/{id}/chat` | Ask one canned question; assert success |
| 12 | `DELETE /agents/sessions/{id}` | Clean up |

### Configuration

**No new env vars required.** Script reads `OPENAI_API_KEY` (or `ANTHROPIC_API_KEY`) from the same `.env` the backend reads. If neither is present, **steps 10-12 are skipped with a `⏭️ [SKIP]` status** and the run still exits 0 — this keeps `make demo` viable for contributors who haven't wired up an LLM key yet.

### Migration Path for Existing Users

- `examples/e2e_smoke.sh` is **preserved** (it covers the `X-Request-ID` propagation contract). The new script extends rather than replaces.
- `README.md` Quick-start section gains one line under "Try it": `make demo`.
- `docs/DAILY-FLOW.md` cross-links to the new target under the "first-run" callout.
- No breaking changes to any existing CLI / API surface.

---

## Technical Design

### Architecture

```
┌────────────────────────────────────────────────────────────────┐
│  scripts/run_demo.py  (httpx.AsyncClient — single process)     │
│                                                                │
│  1. precheck → /health                                         │
│  2. (optional) reset → /seeder/reset                           │
│  3. seed     → /seeder/<scenario>                              │
│  4. wait     → poll /seeder/status                             │
│  5. features → /featuresets/compute                            │
│  6. train    → 3× /jobs (parallel via asyncio.gather)          │
│  7. wait     → poll /jobs/{id} until success                   │
│  8. backtest → /backtesting/run                                │
│  9. register → /registry/aliases (winner by lowest WAPE)       │
│ 10. verify   → /registry/runs/{id}/verify                      │
│ 11. agent    → /agents/sessions + /chat (if LLM key set)       │
│ 12. cleanup  → /agents/sessions/{id} DELETE                    │
└────────────────────────────────────────────────────────────────┘
```

**Components:**

- **`DemoStep` dataclass** — name, async-callable, retry policy, skip predicate. Steps run sequentially; train jobs (step 6) submit in parallel.
- **`DemoContext` dataclass** — accumulates `run_ids`, `featureset_id`, `session_id` across steps for downstream reference.
- **`Reporter` class** — renders `.claude/rules/output-formatting.md` glyphs; supports `--quiet` mode.
- **`HttpClient` thin wrapper** — wraps `httpx.AsyncClient`, surfaces RFC 7807 error bodies in failures, retries idempotent GETs.

### Data Flow

Stateless on the script side. All state lives in Postgres after step 4 and in the `DemoContext` for cross-step references (e.g., `run_id` → backtest input → alias target). The script never writes to disk except for an optional `--log-file` output.

### Dependencies

- `httpx` — already in `pyproject.toml` (used by ingest / agent layers).
- `pydantic` — already pinned; used for typed response models.
- No new third-party deps.

### Updates to Project Design Documents

| Doc | Change |
|-----|--------|
| `README.md` | Quick-start adds `make demo` line + sample output block. |
| `docs/DAILY-FLOW.md` | "First-run" section cross-links to `make demo`. |
| `docs/_base/API_CONTRACTS.md` | No change (consumer-only). |
| `docs/_base/REPO_MAP_INDEX.md` | Add `scripts/run_demo.py` and `Makefile` rows. |
| `docs/_base/RUNBOOKS.md` | New "Demo run failed" entry under Common Incidents (precondition checks, common failure modes). |

### Test Strategy

- **Unit (`tests/test_run_demo_unit.py`):** isolated tests of `DemoStep` ordering, `Reporter` formatting, `DemoContext` reference chaining. Mock the HTTP client.
- **Integration (`tests/test_e2e_demo.py`, marked `@pytest.mark.integration`):** invokes `scripts/run_demo.py` as a subprocess against the live `docker-compose` stack; asserts exit 0, wall-clock ≤ 180 s, and that step 11 (agent chat) either succeeds or is correctly skipped when no LLM key is present.
- **No mocks of Postgres** (per `.claude/rules/test-requirements.md` — integration tests hit the real DB).

---

## Success Metrics

**Quantitative:**

1. `make demo` exits 0 on a clean `docker-compose up -d && uv run alembic upgrade head` host.
2. Wall-clock ≤ 180 s on the developer's reference laptop (measured by the script and logged as the final summary line).
3. Resulting `model_run` row has `status=success`, non-empty JSONB `metrics`, and a valid SHA-256 artifact-verify response.
4. Backtest output reports 3 folds with valid MAE / sMAPE / WAPE per fold (no NaNs).
5. Integration test `tests/test_e2e_demo.py` passes locally and on CI when promoted (post-shakedown).

**Qualitative:**

- A reviewer who has never seen the repo can reach a green verdict via `git clone && docker compose up -d && uv run alembic upgrade head && uv run uvicorn app.main:app & make demo` within their first 5 minutes.
- The output stream surfaces *which* step failed and *why* (RFC 7807 body echoed) without requiring `uvicorn` log spelunking.

**Verification criteria (acceptance):**

1. ✅ `make demo` returns exit 0 against a freshly-seeded DB.
2. ✅ Final output line summarizes: `runs=3 winner=<id> alias=demo-production wall_clock=<t>s`.
3. ✅ The winning `run_id` is reachable via `GET /registry/aliases/demo-production`.
4. ✅ One `/agents/sessions/.../chat` round trip succeeds (or is skipped with `⏭️` if no key).
5. ✅ `tests/test_e2e_demo.py` integration case asserts the same and passes under `pytest -m integration`.

---

## Risks

| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|------------|
| `retail_standard` scenario seeds too much data to finish in 180 s | Med | High | Pin the smallest viable scenario; if `retail_standard` is too heavy, author a `demo_minimal` preset in `app/shared/seeder/` (single-line addition) — flag as Open Question #1. |
| Agent step needs an LLM key the contributor lacks | High | Low | Skip step 11-12 with `⏭️ [SKIP]` when neither `OPENAI_API_KEY` nor `ANTHROPIC_API_KEY` is set; exit 0 still. |
| Backtest WAPE NaN on the seeded dataset | Low | Med | Use a known-good `(start_date, end_date)` window from the seeder's deterministic output; assert non-NaN in the script before alias creation. |
| Phase-2 column drift breaks `compute` step | Low | Med | Script consumes only the public `/featuresets/compute` schema (Pydantic v2 — already validated); failures surface as RFC 7807 bodies. |
| Wall-clock exceeds 180 s on slower hardware (laptops without SSD) | Med | Low | Document the laptop reference baseline in the PRD; allow `--timeout` override; soft-warn (not fail) above 180 s. |
| `make demo` becomes a maintenance burden as the API evolves | Low | Med | Pin to the public schemas (Pydantic); any breakage is caught by the integration test in CI when promoted. |
| Confusion between `scripts/run_demo.py` and `scripts/seed_random.py` | Low | Low | Top-of-file docstring + README quick-start explicitly contrast them. |

---

## Open Questions

- [ ] **Q1: Which seeder scenario?** Use the existing `retail_standard` preset, or author a leaner `demo_minimal` (e.g., 3 stores × 10 products × 60 days) to keep wall-clock comfortable on slower hardware?
- [ ] **Q2: Should `make demo` invoke `docker compose up -d` itself**, or assert the preconditions and bail with exit 2 if Postgres / uvicorn aren't running? (Default proposal: assert + bail — keeps the script honest about being a *consumer* of the stack, not its lifecycle manager.)
- [ ] **Q3: Promote to CI once stable, or keep local-only?** Proposal: stay local for the first two weeks; if no flakes, promote to a nightly `.github/workflows/e2e-nightly.yml` (no PR-blocking).

---

## Cross-Reference

- **Predecessor session output:** brainstorm in this session (Phase 0-5) — winner C1, runner-up C2 (Phase-2-aware LightGBM, queued as direct successor).
- **Vision check:** Aligned with `.claude/rules/product-vision.md` § Core Principle 1 ("Portfolio-grade, end-to-end") and § Litmus Test #5 ("Does it work on a developer's laptop via `docker-compose up`?").
- **Test policy:** `.claude/rules/test-requirements.md` — integration test mandatory, real DB.
- **Output formatting:** `.claude/rules/output-formatting.md` — script output matches.
- **Successor PRP:** `PRPs/PRP-15-e2e-demo-pipeline.md` (to be authored from this INITIAL).
