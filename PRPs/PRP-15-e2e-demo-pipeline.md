name: "PRP-15 — End-to-End Demo Pipeline + Showcase Script"
description: |
  Author a host-driven E2E demo (`make demo`) that exercises ForecastLabAI's published
  API surface — seed → features → train × 3 → backtest → registry → alias → agent —
  against a freshly-seeded `demo_minimal` scenario, in ≤ 180 s on a developer laptop.
  Includes a leaner seeder preset, a top-level `Makefile`, RFC-7807-aware HTTP driver,
  unit + integration tests, doc updates, and an opt-in nightly CI workflow.

## Purpose
Close the demonstrability gap identified in `INITIAL-14.md` (Phase 0 synthesis of the
2026-05-14 brainstorm session): `examples/e2e_smoke.sh` is health-only, and the Phase-2
seeder/featureset work (PRs #111/#112/#114/#115/#127) has no scripted exit channel.
After this PRP lands, one command runs the full pipeline and prints a green verdict.

## Core Principles
1. **Context is King** — every endpoint shape, schema field, and validator decision is
   linked from the real source files below.
2. **Black-box driver** — script consumes the deployed HTTP contract (`httpx`); no
   in-process imports of `app/features/*` services. Validates the *deployed* behavior.
3. **Additive only** — no schema changes, no migrations, no breaking API edits.
   One new scenario preset; one new script; one new Makefile; doc + CI updates.
4. **Vertical-slice rule respected** — script lives at `scripts/`, not under
   `app/features/`; matches `scripts/seed_random.py` / `scripts/check_db.py` shape.
5. **Strict gates honored** — `ruff` + `mypy --strict` + `pyright --strict` +
   `pytest` all green (per `CLAUDE.md` "Validation gates").

---

## Goal
A single command, `make demo`, drives `docker compose up -d` → `alembic upgrade head`
→ `scripts/run_demo.py`, which walks `seed → status → features → train × 3 → backtest
× 3 → register-winner → alias → verify → agent-roundtrip` against the API on
`http://localhost:8123` and exits **0 with a green verdict in ≤ 180 s** on the
reference dev laptop. A nightly GitHub Actions workflow runs the same path against a
docker-compose Postgres service.

## Why
- Portfolio reviewers (and the maintainer after a multi-week absence) cannot demo the
  system today without hand-composing ~12 sequential curl calls across 12 routers
  (`app/main.py:114-126`).
- v0.2.9 just landed Phase-2 features (lifecycle / replenishment / promotion compute
  methods) but `grep -rn "lifecycle|replenishment|promotion|days_since_launch"
  app/features/forecasting/ app/features/backtesting/` returns 0 hits — the recent
  multi-week investment is invisible end-to-end.
- The open-issue queue is empty (`gh issue list --state open` → `[]`), so this is the
  clean inflection point to invest in the demo loop before the next capability slice
  (Phase-2-aware LightGBM, queued as PRP-16).

## What
A new top-level `Makefile` exposing three targets (`demo`, `demo-quick`, `demo-clean`)
that delegate to a new `scripts/run_demo.py`. The script is a single-file, async,
type-checked Python module that walks the published API, computes the winning model
locally by lowest WAPE, registers it via the public `/registry/runs` two-step flow,
opens a one-turn `experiment` agent conversation (or skips with `⏭️` if no LLM key is
set), and reports per-step status using the `.claude/rules/output-formatting.md`
emoji-status convention.

### Success Criteria
- [ ] `make demo` exits 0 on a clean checkout + `docker compose up -d`.
- [ ] Wall-clock ≤ 180 s on the reference laptop; soft-warn (no fail) if exceeded.
- [ ] Final output line: `runs=3 winner=<model_type> alias=demo-production wall_clock=<t>s`.
- [ ] `GET /registry/aliases/demo-production` returns the winning `run_id`.
- [ ] `GET /registry/runs/{winning_run_id}/verify` returns `verified=true`.
- [ ] The agent step either round-trips a chat call successfully or is skipped with
      `⏭️ [SKIP]` when neither `OPENAI_API_KEY` nor `ANTHROPIC_API_KEY` is set.
- [ ] `tests/test_run_demo_unit.py` and `tests/test_e2e_demo.py` (marked
      `@pytest.mark.integration`) both pass.
- [ ] `ruff check`, `ruff format --check`, `mypy --strict app/`, `pyright app/` clean.
- [ ] A new `.github/workflows/e2e-nightly.yml` runs the same path on a daily cron and
      `workflow_dispatch`; **not** a PR-blocking check.

---

## All Needed Context

### Documentation & References
```yaml
- url: https://www.python-httpx.org/async/
  why: AsyncClient lifecycle, timeout/retry, raise_for_status() patterns
  critical: |
    Always use `async with httpx.AsyncClient(...) as client:` — otherwise connections
    leak. Pass `timeout=httpx.Timeout(30.0, connect=5.0)` per call; do NOT rely on
    the default 5s, the seeder step can take ~30-60 s.

- url: https://www.python-httpx.org/api/#response
  why: Response.raise_for_status() and parsing `application/problem+json` bodies
  critical: |
    On non-2xx the body is RFC 7807 JSON per `app/core/problem_details.py`. Surface
    `type`, `title`, `detail`, `request_id` in error output — don't just echo r.text.

- url: https://docs.pydantic.dev/latest/concepts/models/#validating-data
  why: model_validate() for parsing API responses into typed models
  critical: |
    Use `Model.model_validate(r.json())` — this matches FastAPI's strict-mode policy
    (see SECURITY.md "Pydantic v2 strict mode" — issues #109, #117, #120).

- url: https://www.gnu.org/software/make/manual/html_node/Phony-Targets.html
  why: .PHONY declarations to avoid file-name conflicts with target names

- url: https://docs.pytest.org/en/stable/how-to/capture-stdout-stderr.html
  why: subprocess.run() + capture for integration test that exec's the script
  critical: |
    Use `subprocess.run([...], capture_output=True, text=True, timeout=240)` —
    NOT `subprocess.check_output`; we need to inspect exit code and stdout/stderr
    independently on failure.

- url: https://docs.github.com/en/actions/using-workflows/events-that-trigger-workflows#schedule
  why: cron schedule syntax for nightly workflow (UTC)

- file: scripts/check_db.py
  why: Shape for the new scripts/run_demo.py — argparse + asyncio.run + clean exit-code mapping
  critical: |
    Mirrors `sys.exit(asyncio.run(main()))` pattern. Top-of-file docstring with Usage:
    block (matches `seed_random.py` style).

- file: scripts/seed_random.py
  why: Reference for argparse with date types, scenario picker, dry-run flag
  critical: lines 1-50 — Usage docstring + parse_date helper + Settings injection.

- file: examples/e2e_smoke.sh
  why: Original smoke test — keep this file; the new script is additive, not a replacement
  critical: 53 lines, /health + X-Request-ID only. Don't delete.

- file: tests/conftest.py
  why: Pattern for `client` fixture (ASGITransport) + `db_session` fixture (async engine)
  critical: |
    For unit tests of run_demo.py we will MOCK the HTTP client; we do NOT use this
    ASGI fixture. For the integration test we exec the script as a subprocess against
    the real uvicorn started by the CI workflow (or developer's terminal locally).

- file: app/features/seeder/routes.py
  why: Endpoints + request schemas the demo will call
  critical: |
    - POST /seeder/generate (synchronous, line 85; may take several minutes for full scenarios)
    - GET  /seeder/status   (line 36 — used to confirm presence + grab date range)
    - GET  /seeder/scenarios (line 53)
    - DELETE /seeder/data   (line 193 — scope=all for --reset)
    - POST /seeder/verify   (line 312)
    NO polling needed — generate is synchronous.

- file: app/features/seeder/schemas.py
  why: GenerateParams (scenario, seed, stores, products, start_date, end_date, ...) + GenerateResult
  critical: |
    `scenario` is a free string; service.py:47 maps to `ScenarioPreset(name)`.
    To add `demo_minimal`, must add to `ScenarioPreset` enum (config.py:11) AND to
    `from_scenario()` (config.py:495) AND to `list_scenarios()` (service.py:312)
    AND to `app/shared/seeder/tests/test_config.py`.

- file: app/shared/seeder/config.py
  why: ScenarioPreset enum + SeederConfig.from_scenario branches
  critical: lines 11-19 (enum), 494-608 (branches). New scenario goes here.

- file: app/features/featuresets/routes.py
  why: POST /featuresets/compute (synchronous) — request = ComputeFeaturesRequest
  critical: Single-series compute (one store_id+product_id) — demo runs it for ONE
    pair just to demonstrate; the baseline models below don't need feature columns.

- file: app/features/featuresets/schemas.py
  why: ComputeFeaturesRequest + nested FeatureSetConfig (LagConfig, RollingConfig)
  critical: |
    `cutoff_date` is a `date` Field(strict=False, ...) — accepts ISO strings from
    JSON. (Strict-mode policy — see SECURITY.md and tests/test_strict_mode_policy.py.)

- file: app/features/forecasting/routes.py
  why: POST /forecasting/train (synchronous) returns TrainResponse{model_path, config_hash, n_observations, ...}
  critical: |
    Train is per-(store_id, product_id, model_type). The demo trains 3 model types on
    ONE series in parallel via `asyncio.gather`. LightGBM is feature-flagged off
    (line 68) — do NOT use it; baselines are sufficient.

- file: app/features/forecasting/schemas.py
  why: ModelConfig union (NaiveModelConfig | SeasonalNaiveModelConfig | MovingAverageModelConfig | LightGBMModelConfig)
  critical: |
    For demo: NaiveModelConfig(), SeasonalNaiveModelConfig(season_length=7),
    MovingAverageModelConfig(window_size=7). All have model_type Literal.

- file: app/features/backtesting/routes.py
  why: POST /backtesting/run (synchronous) returns BacktestResponse with fold metrics
  critical: |
    `include_baselines=true` automatically benchmarks naive + seasonal_naive — but
    we want explicit cross-model comparison, so the demo calls /backtesting/run ONCE
    PER MODEL_TYPE (3 calls, sequentially) and picks winner by aggregated WAPE.

- file: app/features/backtesting/schemas.py
  why: BacktestRequest(store_id, product_id, start_date, end_date, config=BacktestConfig)
  critical: |
    SplitConfig defaults: strategy='expanding', n_splits=5, min_train_size=30, gap=0,
    horizon=14. For the demo we override n_splits=3 to stay under the 180-s budget.

- file: app/features/registry/routes.py
  why: Two-step registration: POST /registry/runs (PENDING) → PATCH /registry/runs/{id}
  critical: |
    - POST /registry/runs creates with status=pending
    - PATCH /registry/runs/{id} transitions pending → running → success
    - Aliases can ONLY point to success runs (line 404)
    - Required PATCH fields for the demo: status=success, metrics={...}, artifact_uri,
      artifact_hash, artifact_size_bytes.

- file: app/features/registry/schemas.py
  why: RunCreate (model_config_data ALIAS 'model_config'), RunUpdate, AliasCreate
  critical: |
    RunCreate uses `Field(..., alias="model_config")` — when calling, populate the
    JSON field `model_config` (not `model_config_data`). populate_by_name=True so
    either works on the in-Python side; on the wire JSON key must be `model_config`.
    Valid transitions: pending → running → success (schemas.py:32). MUST take the
    intermediate `running` step; pending → success is invalid.

- file: app/features/registry/storage.py
  why: LocalFSProvider.compute_hash() pattern — the demo script reuses hashlib.sha256
  critical: |
    Artifact files live on the local FS at the path returned by /forecasting/train.
    Single-host system — the script CAN open(model_path, 'rb').read() and compute
    sha256 itself. This is the official way to populate `artifact_hash` for PATCH.

- file: app/features/agents/routes.py
  why: POST /agents/sessions, POST /agents/sessions/{id}/chat, DELETE /agents/sessions/{id}
  critical: |
    SessionCreateRequest(agent_type='experiment'|'rag_assistant', initial_context).
    For demo: agent_type='experiment'. ChatRequest requires `message` (min_length=1).
    410 Gone on expired session — handle separately from 404.

- file: app/core/config.py
  why: Settings + get_settings() — script reads OPENAI_API_KEY/ANTHROPIC_API_KEY presence
  critical: |
    Use `settings = get_settings()` and check `bool(settings.openai_api_key)` /
    `bool(settings.anthropic_api_key)`. Per security-patterns.md, NEVER log the value;
    log only the boolean presence.

- file: app/core/problem_details.py
  why: Error response shape (RFC 7807) — the HttpClient wrapper parses these
  critical: Fields: type, title, status, detail, instance, request_id, errors

- file: .claude/rules/output-formatting.md
  why: Emoji glyphs + section headers + summary block
  critical: |
    ✅/❌/⚠️/⏭️/🔄 prefixes; 40-line cap; "👉 Next steps:" footer when failure.

- file: .claude/rules/security-patterns.md
  why: No log of secret VALUES; only key NAMES. No subprocess(shell=True). Pydantic at boundaries.

- file: .claude/rules/test-requirements.md
  why: Mark integration tests `@pytest.mark.integration`; no DB mocks in integration.

- file: .claude/rules/commit-format.md
  why: Every commit needs `type(scope): description (#issue)` — open the tracking issue FIRST.
```

### Current Codebase tree (relevant)
```bash
.
├── Makefile                          # DOES NOT EXIST — create
├── scripts/
│   ├── check_db.py                   # pattern to mirror
│   ├── seed_random.py                # pattern to mirror (argparse + Settings)
│   └── run_demo.py                   # DOES NOT EXIST — create
├── examples/
│   └── e2e_smoke.sh                  # keep (health-only smoke for X-Request-ID)
├── tests/
│   ├── conftest.py                   # fixtures (ASGITransport + db_session)
│   ├── test_run_demo_unit.py         # DOES NOT EXIST — create
│   └── test_e2e_demo.py              # DOES NOT EXIST — create
├── app/
│   ├── core/
│   │   ├── config.py                 # Settings.openai_api_key / anthropic_api_key
│   │   └── problem_details.py        # RFC 7807 error shape
│   ├── features/
│   │   ├── seeder/{routes,schemas,service}.py
│   │   ├── featuresets/{routes,schemas}.py
│   │   ├── forecasting/{routes,schemas}.py
│   │   ├── backtesting/{routes,schemas}.py
│   │   ├── registry/{routes,schemas,storage}.py
│   │   └── agents/{routes,schemas}.py
│   └── shared/seeder/
│       ├── config.py                 # ScenarioPreset enum + from_scenario branches
│       └── tests/test_config.py      # add demo_minimal test
├── .github/workflows/
│   ├── ci.yml                        # 4 required jobs (don't extend; nightly is separate)
│   └── e2e-nightly.yml               # DOES NOT EXIST — create (cron, not PR-blocking)
└── docs/
    ├── DAILY-FLOW.md                 # cross-link `make demo`
    └── _base/{REPO_MAP_INDEX,RUNBOOKS}.md  # row + incident entry
```

### Desired Codebase tree (files added/changed)
```bash
NEW   Makefile                                       # demo / demo-quick / demo-clean targets
NEW   scripts/run_demo.py                            # ~400 lines, single-file async driver
NEW   tests/test_run_demo_unit.py                    # mock-HTTP unit coverage of the driver
NEW   tests/test_e2e_demo.py                         # @pytest.mark.integration subprocess test
NEW   .github/workflows/e2e-nightly.yml              # cron + workflow_dispatch
MOD   app/shared/seeder/config.py                    # +DEMO_MINIMAL enum value + from_scenario branch
MOD   app/features/seeder/service.py                 # +ScenarioInfo entry in list_scenarios()
MOD   app/shared/seeder/tests/test_config.py         # +test_from_scenario_demo_minimal
MOD   README.md                                      # Quick-start "Try it" line
MOD   docs/DAILY-FLOW.md                             # First-run cross-link
MOD   docs/_base/RUNBOOKS.md                         # New "Demo run failed" incident
MOD   docs/_base/REPO_MAP_INDEX.md                   # Rows for Makefile + scripts/run_demo.py
KEEP  examples/e2e_smoke.sh                          # unchanged (X-Request-ID smoke remains)
```

### Known Gotchas of our codebase & Library Quirks
```python
# CRITICAL: /seeder/generate is SYNCHRONOUS — returns GenerateResult directly.
#   Do NOT loop on GET /seeder/status expecting it to flip; status is for after.
#   Source: app/features/seeder/routes.py:85-136 (no 202; returns 201 with body).

# CRITICAL: /forecasting/train is SYNCHRONOUS too — returns TrainResponse with model_path.
#   Do NOT submit via /jobs; that's for the agentic/background queue, not the synchronous baselines.
#   Source: app/features/forecasting/routes.py:24-131.

# CRITICAL: Pydantic strict-mode policy on request bodies — fields typed `date` /
#   `datetime` / `UUID` / `Decimal` MUST carry `Field(strict=False, ...)` because
#   FastAPI calls validate_python (not validate_json) on the parsed dict.
#   Effect on caller: passing ISO date STRINGS in JSON is fine; the server unwraps them.
#   Source: docs/_base/SECURITY.md "Pydantic v2 strict mode" + issue #117/PR #119.

# CRITICAL: Registry transitions are pending → running → success. You MUST patch
#   intermediate `running` even though the script does the training synchronously.
#   pending → success is rejected by InvalidTransitionError (registry/schemas.py:32-38).

# CRITICAL: RunCreate uses Field(alias="model_config") — on-the-wire JSON key is
#   `model_config`, not `model_config_data`. Use httpx `json=` and write
#   "model_config": <dict> in the payload. (registry/schemas.py:68)

# CRITICAL: Aliases can ONLY point to runs in SUCCESS status. Trying to alias a
#   PENDING/RUNNING run returns 400. Order matters: alias AFTER patch-to-success.
#   (registry/routes.py:404)

# CRITICAL: artifact_hash computation — the demo script reads the file at model_path
#   (returned by /forecasting/train) and computes sha256 client-side. This works only
#   because we're single-host; the script and the API share the FS. Mirror
#   LocalFSProvider.compute_hash() logic (registry/storage.py).

# CRITICAL: Agent step needs OPENAI_API_KEY or ANTHROPIC_API_KEY. If neither is set,
#   the agent service will fail at first chat call. SKIP gracefully with ⏭️ when
#   neither is present. Use bool(settings.openai_api_key) — never log the value.

# CRITICAL: Backtest with strategy="expanding" + n_splits=3 + horizon=14 + min_train_size=30
#   needs the seeded date range to be ≥ 30 + 3*14 = 72 days. The demo_minimal scenario
#   must cover ≥ 90 days to stay safe. Recommended: 2024-10-01 → 2024-12-31 (92 days).

# CRITICAL: Seeder is BLOCKED in production unless seeder_allow_production=true. The
#   demo MUST run on a host where settings.app_env != "production" (default), or with
#   the override. The script should NOT touch that env var; document the requirement.
#   (app/features/seeder/routes.py:21-33)

# CRITICAL: Makefile recipes — tab indentation, NOT spaces. Use `.PHONY: ...` for all
#   targets (they're not file outputs). `uv run` prefixes every Python invocation per
#   CLAUDE.md "Commands".

# CRITICAL: Output formatting — use the .claude/rules/output-formatting.md glyphs
#   (✅/❌/⚠️/⏭️/🔄). Cap report at 40 lines. End with `👉 Next steps:` footer on
#   any non-success path.

# GOTCHA: httpx default timeout is 5 seconds, which is too short for /seeder/generate
#   (can take ~30-60 s for retail_standard, ~10-20 s for demo_minimal). Use
#   `httpx.Timeout(60.0, connect=5.0)` per call OR set the client-wide timeout.

# GOTCHA: pyproject.toml ruff per-file-ignores already gives `scripts/**/*.py` a
#   pass on T201 (print()) and ANN — but `scripts/run_demo.py` IS the script, so
#   prints are intentional. (pyproject.toml:97)

# GOTCHA: The integration test subprocess invocation needs `cwd=repo_root` so
#   `uv run python scripts/run_demo.py` resolves; pass via Path(__file__).parent.parent.

# GOTCHA: CI nightly — uvicorn must be backgrounded (& or `uvicorn ... &`). Use
#   `until curl -fs http://127.0.0.1:8123/health; do sleep 2; done` to wait, capped
#   at 30 s. Don't use `sleep 30 && curl` blindly — fragile.

# GOTCHA: Every commit referencing the new files needs an issue number per
#   commit-format.md. Open the tracking issue BEFORE the first commit:
#   `gh issue create --title "feat(api,docs): e2e demo pipeline + showcase script"
#    --body "Implements PRP-15 / INITIAL-14"`.
```

---

## Implementation Blueprint

### Data models and structure

```python
# scripts/run_demo.py — module-level types

from dataclasses import dataclass, field
from collections.abc import Awaitable, Callable
from typing import Any

@dataclass
class DemoContext:
    """Accumulator threaded through every step.

    Holds cross-step references (store_id, product_id, train run_ids, winner) so
    later steps can use earlier outputs without recomputing. The script never
    mutates the API state via this struct — it is read-side cache only.
    """
    api_url: str
    seed: int
    skip_seed: bool
    reset: bool
    quiet: bool
    timeout: float
    store_id: int = 1          # seeded as 1..N by demo_minimal
    product_id: int = 1
    date_start: str | None = None  # populated after seed (ISO)
    date_end: str | None = None
    train_results: dict[str, dict[str, Any]] = field(default_factory=dict)
    backtest_results: dict[str, dict[str, Any]] = field(default_factory=dict)
    winner_model_type: str | None = None
    winner_wape: float | None = None
    winning_run_id: str | None = None
    session_id: str | None = None
    wall_clock_start: float = 0.0

@dataclass
class StepOutcome:
    name: str
    status: str  # "pass" | "fail" | "skip" | "warn"
    detail: str
    duration_ms: float
```

### Task list (in execution order)

```yaml
Task 1 — Open tracking GitHub issue (REQUIRED per commit-format.md):
  RUN:
    gh issue create \
      --title "feat(api,docs): e2e demo pipeline + showcase script" \
      --body "Implements PRP-15 / INITIAL-14. Single command 'make demo' drives seed → features → train × 3 → backtest → registry → alias → agent in ≤ 180 s. Adds demo_minimal scenario, top-level Makefile, scripts/run_demo.py, unit + integration tests, nightly CI."
  CAPTURE: issue number (e.g. #128) — use in ALL commits below.

Task 2 — Add DEMO_MINIMAL scenario:
  MODIFY app/shared/seeder/config.py:
    - INJECT enum value at line 19 (after SPARSE):
        DEMO_MINIMAL = "demo_minimal"
    - INJECT from_scenario branch after line 605 (after SPARSE branch):
        if scenario == ScenarioPreset.DEMO_MINIMAL:
            return cls(
                seed=seed,
                start_date=date(2024, 10, 1),
                end_date=date(2024, 12, 31),
                dimensions=DimensionConfig(stores=3, products=10),
                time_series=TimeSeriesConfig(
                    base_demand=100, trend="linear",
                    trend_slope=0.0005, noise_sigma=0.10,
                ),
                retail=RetailPatternConfig(
                    promotion_probability=0.1, stockout_probability=0.02,
                ),
            )
  MODIFY app/features/seeder/service.py:list_scenarios (line 312):
    - INJECT ScenarioInfo entry after sparse (line 366):
        schemas.ScenarioInfo(
            name="demo_minimal",
            description="Tiny preset for the make demo target (3 stores × 10 products × 92 days)",
            stores=3, products=10,
            start_date=date(2024, 10, 1), end_date=date(2024, 12, 31),
        ),
  MODIFY app/shared/seeder/tests/test_config.py:
    - ADD test_from_scenario_demo_minimal mirroring test_from_scenario_retail_standard
    - UPDATE test_all_scenario_names to include "demo_minimal"

Task 3 — Create scripts/run_demo.py skeleton:
  CREATE scripts/run_demo.py:
    - MIRROR docstring + argparse pattern from scripts/seed_random.py lines 1-50
    - MIRROR exit-code pattern from scripts/check_db.py lines 67-72
    - ADD argparse for: --seed (int, default 42), --skip-seed (flag),
      --reset (flag), --quiet (flag), --api-url (str, default http://localhost:8123),
      --timeout (float, default 60.0)
    - ADD module-level DemoContext + StepOutcome dataclasses (above)
    - ADD Reporter class with `step_start(name)`, `step_pass/fail/warn/skip(detail)`,
      `summary(outcomes)` methods using the rules/output-formatting.md glyphs
    - ADD HttpClient wrapper: httpx.AsyncClient with timeout, plus a helper that
      raises a typed StepError on non-2xx surfacing problem+json type/title/detail/request_id

Task 4 — Implement steps 1-4 (health + reset + seed + status):
  IN scripts/run_demo.py:
    - precheck_health(ctx, client): GET /health → 200 / status="ok" else exit 2
    - maybe_reset(ctx, client): if --reset, DELETE /seeder/data {scope:"all", dry_run:false}
    - seed_dataset(ctx, client): POST /seeder/generate with body
        {"scenario":"demo_minimal", "seed":ctx.seed, "stores":3, "products":10,
         "start_date":"2024-10-01", "end_date":"2024-12-31",
         "sparsity":0.0, "dry_run":false}
      (skipped if --skip-seed). Stash records_created counts on ctx.
    - confirm_status(ctx, client): GET /seeder/status → populate ctx.date_start/date_end.
      Pick (store_id=1, product_id=1) — the first record in demo_minimal.

Task 5 — Implement step 5 (featureset compute, demo-only):
  IN scripts/run_demo.py:
    - compute_features_demo(ctx, client): POST /featuresets/compute with body
        {"store_id":1, "product_id":1, "cutoff_date": ctx.date_end,
         "lookback_days":60, "config":{"lag_config":{"lags":[1,7,14]},
                                       "rolling_config":{"windows":[7,14], "aggregations":["mean","std"]},
                                       "calendar_config":{"include":["dow","month","quarter"]}}}
      Surface row_count + null_counts to the report; do NOT pass features to train
      (baselines don't consume them; this step is demonstration-only).

Task 6 — Implement step 6 (train × 3 in parallel):
  IN scripts/run_demo.py:
    - train_all(ctx, client): asyncio.gather of 3 train calls:
        POST /forecasting/train with bodies:
          {"store_id":1, "product_id":1,
           "train_start_date": ctx.date_start, "train_end_date": <ctx.date_end - 14 days>,
           "config":{"model_type":"naive"}}
          ... seasonal_naive (season_length=7) ...
          ... moving_average (window_size=7) ...
      Stash each TrainResponse on ctx.train_results[model_type].
      train_end_date = date_end - horizon to leave room for backtest test windows.

Task 7 — Implement step 7 (backtest × 3 sequentially; pick winner):
  IN scripts/run_demo.py:
    - backtest_all(ctx, client): for each model_type in [naive, seasonal_naive, moving_average]:
        POST /backtesting/run with body
          {"store_id":1, "product_id":1,
           "start_date": ctx.date_start, "end_date": ctx.date_end,
           "config":{"split_config":{"strategy":"expanding","n_splits":3,
                                     "min_train_size":30,"gap":0,"horizon":14},
                     "model_config_main":{"model_type": model_type, ...},
                     "include_baselines": false,   # already comparing apples-to-apples
                     "store_fold_details": false}} # save bytes
      Stash aggregated_metrics on ctx.backtest_results[model_type].
      ctx.winner_model_type = argmin of aggregated_metrics["wape"] across 3 models.
      ctx.winner_wape = winning WAPE.

Task 8 — Implement step 8 (registry create-run + update + alias):
  IN scripts/run_demo.py:
    - register_winner(ctx, client):
        a) Read winner's model_path → compute sha256 hash + size in bytes.
           Use pathlib.Path(model_path).read_bytes() then hashlib.sha256(...).hexdigest().
        b) POST /registry/runs with payload (NOTE: JSON key "model_config", NOT "model_config_data"):
            {"model_type": ctx.winner_model_type,
             "model_config": <the full ModelConfig dict that was trained>,
             "feature_config": null,
             "data_window_start": ctx.date_start, "data_window_end": ctx.date_end,
             "store_id":1, "product_id":1,
             "agent_context": null, "git_sha": null}
           Capture run_id from response.
        c) PATCH /registry/runs/{run_id} with {"status":"running"}   (required transition)
        d) PATCH /registry/runs/{run_id} with:
            {"status":"success",
             "metrics": ctx.backtest_results[ctx.winner_model_type],
             "artifact_uri": model_path,
             "artifact_hash": <sha256_hex>,
             "artifact_size_bytes": <size>}
        e) POST /registry/aliases with {"alias_name":"demo-production", "run_id": run_id}.

Task 9 — Implement step 9 (verify) + step 10 (agent if key set) + step 11 (cleanup):
  IN scripts/run_demo.py:
    - verify_artifact(ctx, client): GET /registry/runs/{ctx.winning_run_id}/verify;
      assert response["verified"] == True.
    - chat_with_agent_if_keys_set(ctx, client):
        from app.core.config import get_settings
        s = get_settings()
        if not (s.openai_api_key or s.anthropic_api_key):
            return StepOutcome(name="agent", status="skip",
                detail="No OPENAI_API_KEY/ANTHROPIC_API_KEY set", duration_ms=0.0)
        POST /agents/sessions {"agent_type":"experiment"} → session_id
        POST /agents/sessions/{session_id}/chat {"message":"List the latest model runs"}
        Assert 200; capture tool_calls_count + total_tokens_used for the report.
        DELETE /agents/sessions/{session_id} (cleanup, ignore 204).

Task 10 — Wire main() + summary:
  IN scripts/run_demo.py:
    - main_async(args): instantiate DemoContext + Reporter + HttpClient;
      run steps in order; collect StepOutcomes; print summary block
      formatted per .claude/rules/output-formatting.md including
      "runs=3 winner=<model_type> alias=demo-production wall_clock=<t>s" final line.
      If wall_clock > 180s, ⚠️ WARN but do not fail (per INITIAL-14 risk mitigation).
    - main(): sys.exit(asyncio.run(main_async(parse_args())))

Task 11 — Create top-level Makefile:
  CREATE Makefile:
    - .PHONY: demo demo-quick demo-clean help
    - help: print available targets (default goal)
    - demo:   docker compose up -d  &&  uv run alembic upgrade head  &&  \
              uv run python scripts/run_demo.py --seed 42
    - demo-quick: uv run python scripts/run_demo.py --seed 42 --skip-seed
    - demo-clean: docker compose up -d  &&  uv run alembic upgrade head  &&  \
                  uv run python scripts/run_demo.py --seed 42 --reset
    Use tab indentation; line-continuation with backslash + tab on next line.

Task 12 — Unit tests:
  CREATE tests/test_run_demo_unit.py:
    - Import the run_demo module: `import scripts.run_demo as run_demo`
      (add scripts/__init__.py if needed — check first; scripts/seed_random.py
       doesn't require it because it's run as a script, but for imports we need it).
    - Test Reporter glyph mapping: pass=✅, fail=❌, skip=⏭️, warn=⚠️.
    - Test DemoContext default field values.
    - Test argparse parsing of --seed/--skip-seed/--reset/--quiet/--api-url/--timeout.
    - Test winner selection: given three backtest_results dicts with different WAPE,
      assert winner_model_type is the argmin.
    - Mock the HttpClient with unittest.mock.AsyncMock and verify per-step request
      payloads match the documented JSON shapes.

Task 13 — Integration test:
  CREATE tests/test_e2e_demo.py:
    - @pytest.mark.integration on the class/function.
    - Skip if docker compose Postgres is unreachable
      (try: `await asyncpg.connect(settings.database_url)` with 2-second timeout).
    - Start uvicorn as a fixture: subprocess.Popen(["uv","run","uvicorn","app.main:app","--port","8124"], ...);
      wait for http://127.0.0.1:8124/health via polling (cap 30s).
      Use port 8124 to avoid colliding with a developer's already-running server.
    - Run: subprocess.run(["uv","run","python","scripts/run_demo.py","--seed","42",
      "--reset","--api-url","http://127.0.0.1:8124","--timeout","60"],
      capture_output=True, text=True, timeout=240).
    - Assert: returncode == 0, "demo-production" in stdout, wall_clock < 180 (soft).
    - Teardown: terminate uvicorn; clean alias via DELETE /registry/aliases/demo-production.

Task 14 — Nightly CI workflow:
  CREATE .github/workflows/e2e-nightly.yml:
    - Triggers: schedule (cron '0 7 * * *' = 07:00 UTC daily) + workflow_dispatch.
    - Job 'e2e-demo': ubuntu-latest with services.postgres (pgvector/pgvector:pg16)
      pinned same way as ci.yml `test` job.
    - Steps: checkout @v6, setup-uv @<sha>, install deps `uv sync --frozen --all-extras`,
      `uv run alembic upgrade head`, start uvicorn in background with `&` + wait-loop,
      `uv run python scripts/run_demo.py --seed 42 --api-url http://127.0.0.1:8123 --timeout 60`.
    - permissions: contents: read.
    - Pin third-party actions by SHA per .claude/rules/security-patterns.md.
    - NOT a required check on dev/main.

Task 15 — Docs updates:
  MODIFY README.md:
    - Add `make demo` line under "Quick start" / "Try it" section (find the existing
      block by grepping for "uv run uvicorn" or "docker compose up").
  MODIFY docs/DAILY-FLOW.md:
    - Cross-link `make demo` from the "first-run" section.
  MODIFY docs/_base/RUNBOOKS.md:
    - Add a new "Common Incidents" entry: "make demo fails at step X" with diagnosis
      tree (precondition checks, missing key handling, scenario presence).
  MODIFY docs/_base/REPO_MAP_INDEX.md:
    - Add table rows for `Makefile` and `scripts/run_demo.py` under "Document Index".

Task 16 — Commit + PR:
  Branch: feat/api-e2e-demo (off dev, per .claude/rules/branch-naming.md)
  Commits (each referencing the issue from Task 1):
    1. `feat(data): add demo_minimal scenario preset (#<issue>)` — tasks 2
    2. `feat(api,docs): scripts/run_demo.py end-to-end pipeline driver (#<issue>)` — tasks 3-10
    3. `feat(repo): top-level Makefile with demo / demo-quick / demo-clean (#<issue>)` — task 11
    4. `test(api): unit + integration coverage for run_demo (#<issue>)` — tasks 12-13
    5. `ci(repo): nightly e2e demo workflow (#<issue>)` — task 14
    6. `docs(docs): cross-link make demo from README + RUNBOOKS + REPO_MAP_INDEX (#<issue>)` — task 15
```

### Per-task pseudocode (HttpClient wrapper — the load-bearing piece)

```python
# scripts/run_demo.py — HttpClient wrapper

class StepError(Exception):
    """Surfaces RFC 7807 problem+json bodies as a typed failure."""
    def __init__(self, step: str, status_code: int, problem: dict[str, Any]) -> None:
        self.step = step
        self.status_code = status_code
        self.problem = problem
        super().__init__(
            f"{step}: HTTP {status_code} — {problem.get('title','?')}: "
            f"{problem.get('detail','?')} (request_id={problem.get('request_id','?')})"
        )

class HttpClient:
    def __init__(self, base_url: str, timeout: float) -> None:
        # CRITICAL: explicit timeout — default 5s is too short for /seeder/generate
        self._client = httpx.AsyncClient(
            base_url=base_url,
            timeout=httpx.Timeout(timeout, connect=5.0),
        )

    async def __aenter__(self) -> "HttpClient": ...
    async def __aexit__(self, *exc: object) -> None:
        await self._client.aclose()

    async def request(self, step: str, method: str, path: str, **kw: Any) -> dict[str, Any]:
        # PATTERN: never log secret VALUES per security-patterns.md — log path + status only
        r = await self._client.request(method, path, **kw)
        if r.status_code >= 400:
            try:
                problem = r.json()
            except json.JSONDecodeError:
                problem = {"title": "Non-JSON error", "detail": r.text[:200]}
            raise StepError(step, r.status_code, problem)
        # GOTCHA: 204 No Content — DELETE /agents/sessions returns no body
        if r.status_code == 204:
            return {}
        return r.json()
```

### Integration Points
```yaml
DATABASE:
  - migration: NONE (no schema change)
  - data: demo_minimal scenario reads from existing tables; no new tables

CONFIG:
  - No new env vars (Q1 answered "yes — add demo_minimal preset"; Q2 answered
    "yes — make demo invokes docker compose up -d itself"; Q3 answered
    "yes — promote to nightly CI as part of this PRP")

ROUTES:
  - No new API routes (script consumes existing surface only)

DOCS:
  - README.md, docs/DAILY-FLOW.md, docs/_base/RUNBOOKS.md, docs/_base/REPO_MAP_INDEX.md

CI:
  - new .github/workflows/e2e-nightly.yml (cron 07:00 UTC + workflow_dispatch)
  - NOT a required-status-check on dev or main
```

---

## Validation Loop

### Level 1: Syntax & Style
```bash
# Fix-on-fail, then re-run
uv run ruff check . --fix
uv run ruff format .
uv run mypy app/
uv run pyright app/
# Expected: zero errors. Strict mode is enforced (pyproject.toml:114-126 + 149-172).
# For scripts/, pyright EXCLUDES tests but INCLUDES scripts since they import app.* —
# verify scripts/run_demo.py passes mypy/pyright too:
uv run mypy scripts/run_demo.py
uv run pyright scripts/run_demo.py
```

### Level 2: Unit tests
```bash
uv run pytest -v -m "not integration" tests/test_run_demo_unit.py \
                                     app/shared/seeder/tests/test_config.py
# Expected: all green. Tests are pure-Python; no DB. Mock httpx.AsyncClient.
```

### Level 3: Integration test (REAL DB + REAL uvicorn)
```bash
# Bring up Postgres + apply migrations
docker compose up -d
uv run alembic upgrade head

# Run the integration test (spins up uvicorn on :8124 as a subprocess, then exec's the demo)
uv run pytest -v -m integration tests/test_e2e_demo.py
# Expected: PASS; the test asserts:
#   - returncode == 0
#   - "demo-production" appears in stdout
#   - wall-clock under 180s (soft assertion / warn-only)
```

### Level 4: Manual end-to-end verification
```bash
# Smoke the maintainer's actual UX
docker compose up -d
uv run alembic upgrade head
uv run uvicorn app.main:app --port 8123 &     # background
until curl -fs http://127.0.0.1:8123/health; do sleep 2; done

make demo
# Expected output (abbreviated, formatted per .claude/rules/output-formatting.md):
#
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#   🔍 ForecastLabAI Demo
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# ✅ Step  1/11: precheck — /health ok
# ✅ Step  2/11: reset — skipped (no --reset)
# ✅ Step  3/11: seed — 3 stores × 10 products × 92 days
# ✅ Step  4/11: status — date_range=2024-10-01..2024-12-31
# ✅ Step  5/11: features — 60 rows, lag+rolling+calendar
# ✅ Step  6/11: train × 3 — naive, seasonal_naive, moving_average
# ✅ Step  7/11: backtest × 3 — winner=seasonal_naive wape=0.18
# ✅ Step  8/11: register — run_id=abc123 alias=demo-production
# ✅ Step  9/11: verify — sha256 OK
# ⏭️ Step 10/11: agent — SKIP (no LLM key set)
# ✅ Step 11/11: cleanup — done
# ────────────────────────────────────────────
#   ✅ Result: GREEN
# ────────────────────────────────────────────
# runs=3 winner=seasonal_naive alias=demo-production wall_clock=87s
```

---

## Final Validation Checklist
- [ ] `uv run ruff check . && uv run ruff format --check .` clean
- [ ] `uv run mypy app/` clean (strict)
- [ ] `uv run pyright app/` clean (strict)
- [ ] `uv run pytest -v -m "not integration"` all green
- [ ] `uv run pytest -v -m integration tests/test_e2e_demo.py` green
- [ ] `make demo` exits 0 against a clean DB; wall-clock ≤ 180s
- [ ] `GET /registry/aliases/demo-production` returns the winner
- [ ] `GET /registry/runs/{winner_run_id}/verify` returns `verified=true`
- [ ] Agent step either succeeds or correctly emits `⏭️ [SKIP]`
- [ ] `.github/workflows/e2e-nightly.yml` syntactically valid (`actionlint` or
      `gh workflow view e2e-nightly.yml`); third-party actions SHA-pinned per
      `.claude/rules/security-patterns.md`
- [ ] README + DAILY-FLOW + RUNBOOKS + REPO_MAP_INDEX updated
- [ ] `examples/e2e_smoke.sh` untouched (regression check)
- [ ] No new env vars added to `.env.example` (verified: not needed)
- [ ] No AI co-author trailers on any commit (per `.claude/rules/commit-format.md`)
- [ ] Every commit references the tracking issue from Task 1
- [ ] Branch named `feat/api-e2e-demo` (per `.claude/rules/branch-naming.md`)

---

## Anti-Patterns to Avoid
- ❌ Don't call services in-process — defeats demo-trust purpose; use HTTP.
- ❌ Don't reuse `scripts/seed_random.py` directly — different abstraction (CLI vs HTTP driver).
- ❌ Don't `sleep` in tight loops; use `asyncio.sleep` + bounded retries.
- ❌ Don't log API keys or RFC 7807 bodies that may contain them (echo `title`/`detail`/`request_id` only).
- ❌ Don't skip the intermediate `pending → running` registry transition; it's required by the state machine.
- ❌ Don't add `lightgbm` to the demo — it's feature-flagged off and Phase-2 column
   integration is PRP-16 scope.
- ❌ Don't introduce a new `feature_view` abstraction "while we're here" — out of scope.
- ❌ Don't `os.environ[...]` directly in scripts/ — use `app.core.config.get_settings()`.
- ❌ Don't make the nightly CI workflow PR-blocking — it's informational only this PRP.
- ❌ Don't `git push --force` on dev/main; don't AI-co-author the commits.
- ❌ Don't expand the seeder API contract — `demo_minimal` is purely a scenario preset on the existing surface.

---

## Confidence Score

**8 / 10** for one-pass implementation success.

**Why high:**
- API surface is fully cataloged with file paths + line numbers (every endpoint
  the script calls is documented above with its schema location).
- All gotchas are written down (synchronous seeder, registry 2-step, alias-after-success
  ordering, strict-mode date fields, model_config alias, hashlib for artifact, default
  httpx timeout trap, Makefile tab indentation, scripts ruff exemption).
- Validation gates are concrete commands an agent can run + fix loop on.
- No external dependencies added; no migrations; no breaking changes.
- Failure modes are all surfaced via RFC 7807 with `request_id` for log correlation.

**Why not 10:**
- The integration test that subprocess-spawns uvicorn on port 8124 is fiddly (port
  collision detection, process teardown, CI flakiness around `until curl …`); first
  pass may need a retry loop tuned.
- `demo_minimal` scenario's exact `base_demand` / seasonality may need one tweak to
  produce a non-NaN WAPE on every backtest fold (the SPARSE preset has had this trap
  before — see `app/shared/seeder/tests/test_phase1_regression.py`).
- The wall-clock budget of 180 s is laptop-dependent; the CI nightly job may need a
  bumped timeout vs. the local target.

If the agent hits any of those three, the validation loop above will catch it
deterministically and the fix is local (retry tuning, scenario parameters, CI timeout).
