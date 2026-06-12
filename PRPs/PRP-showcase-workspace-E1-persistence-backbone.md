name: "PRP — Showcase Workspace E1: Persistence Backbone (issue #390)"
description: |

## Purpose

Implement the Foundation epic of the showcase-workspace initiative (umbrella #389):
the demo slice gains its first persistence — a `showcase_workspace` table + Alembic
migration + additive Optional `preservation`/`workspace_name` fields on
`DemoRunRequest` + pipeline recording of every created object id into the workspace
row. Blocks epics #391 (presets), #392 (tags), #393 (restore/replay).

## Core Principles

1. **Context is King**: every reference below was verified against the live code on 2026-06-12.
2. **Validation Loops**: each level is executable as written.
3. **Information Dense**: patterns cite exact file:line.
4. **Progressive Success**: schema fields → model+migration → service → pipeline hook → tests.
5. **Global rules**: follow CLAUDE.md / AGENTS.md; all five CI gates must pass.

---

## Goal

A demo/showcase run started with `preservation="keep"` creates exactly one
`showcase_workspace` row that records the run configuration (seed, scenario, reset,
skip_seed, name) and — when the pipeline finishes — every object the run created
(winning/V2 registry run ids, alias, scenario plan ids, batch id, agent session id,
artifact paths, store/product grain, date window) plus a result summary. A run
without the new fields behaves **byte-identically to today** (no row, same events,
same responses). Legacy WS/HTTP clients keep working unchanged.

**Deliverable** (all additive, backend-only — no frontend changes in E1):

- `app/features/demo/models.py` — new `ShowcaseWorkspace` ORM model (first table owned by the demo slice).
- `alembic/versions/<new>_create_showcase_workspace_table.py` — forward migration + clean downgrade.
- `alembic/env.py` — one added model-registration import.
- `app/features/demo/schemas.py` — `DemoRunRequest` gains `preservation` + `workspace_name`.
- `app/features/demo/workspace.py` — new module: create/finalize (+ get/list helpers for tests and E4).
- `app/features/demo/pipeline.py` — `DemoContext.workspace_id` field + create/finalize hooks in `run_pipeline`; `pipeline_complete.data` gains additive `workspace_id`.
- Tests: schema unit tests, model constraint/CRUD integration tests, workspace-service integration tests, pipeline unit tests, route passthrough tests.
- `docs/_base/API_CONTRACTS.md` — additive contract notes for the two request fields and the `workspace_id` summary key.

**Success definition**: all Success Criteria below check off, the five CI gates are
green, and a manual `POST /demo/run` with `{"preservation": "keep", "workspace_name":
"e1-smoke"}` against a seeded local stack produces a `completed` workspace row whose
`created_objects` JSONB contains the run's real ids.

## Why

- The cleanup step deletes nothing (`app/features/demo/pipeline.py:2045` `step_cleanup` only closes the agent session and restores the `demo-production` alias), so showcase objects already persist — but unlabeled and unfindable. E1 gives that de-facto preservation explicit semantics and discoverability.
- Umbrella #389 decomposition: E1 is the Foundation; #391/#392/#393 all build on the table and the request fields added here.
- The only run memory today is a localStorage FIFO-5 in the frontend (`frontend/src/pages/showcase.tsx:166`) — server-side workspace rows are the prerequisite for restore/replay (E4).

## What

### User-visible behavior

- `POST /demo/run` and the `WS /demo/stream` start frame accept two new **optional** fields:
  - `preservation`: `"ephemeral"` (default — today's behavior, no row) or `"keep"` (create + finalize a workspace row).
  - `workspace_name`: optional human label, `^[a-z0-9][a-z0-9\-_]*$`, ≤100 chars (same pattern as registry alias names, `app/features/registry/schemas.py:213`). Only allowed with `preservation="keep"` — supplying it with `"ephemeral"` is a 422.
- The final `pipeline_complete` event's `data` dict gains an additive `workspace_id` key (`null` on ephemeral runs).
- No new public endpoints in E1 (list/load is epic #393/E4). `workspace.py` ships `get_workspace`/`list_workspaces` helpers for tests and E4 reuse, unrouted.

### Technical requirements

- Workspace row is created (status `running`) before the first step executes and finalized (status `completed`/`failed` + collected ids) before `pipeline_complete` is yielded — including the mid-run-failure path, so a partial run still records what it created.
- Workspace DB writes are **warn-and-continue**: a DB failure must never break the demo pipeline (mirror the lifespan pattern at `app/main.py:62-71`).
- **No ForeignKeys** to `model_run` / `scenario_plan` / `batch_job` / `agent_session` — recorded ids are opaque soft references. A cross-slice FK would couple the demo slice's schema to four other slices and break independent deletion. This is a deliberate design decision; document it in the model docstring.
- The demo slice still never imports another feature slice (`app/features/demo/` imports only `app.core.*`, `app.shared.*`, and stdlib/3rd-party — verified: the pipeline drives everything through ASGITransport).

### Success Criteria

- [ ] `DemoRunRequest()` (no args) serializes identically to today's defaults plus `preservation="ephemeral"`, `workspace_name=None`; a start frame without the new keys validates (legacy compatibility).
- [ ] `preservation="keep"` run → exactly one `showcase_workspace` row: status `completed` on a green run, `failed` when a step fails; `created_objects` carries the ids the run produced; `result_summary` carries winner/wape/wall-clock.
- [ ] `preservation="ephemeral"` (or omitted) → zero rows written, zero workspace queries issued.
- [ ] `workspace_name` with `preservation="ephemeral"` → 422 `application/problem+json`.
- [ ] `pipeline_complete.data.workspace_id` present (string on keep runs, `null` otherwise).
- [ ] Migration applies AND downgrades cleanly on a fresh DB; `schema-validation.yml` autogenerate drift check sees the model (env.py import added).
- [ ] `uv run ruff check . && uv run ruff format --check . && uv run mypy app/ && uv run pyright app/ && uv run pytest -v -m "not integration"` all green; integration suite green against docker-compose Postgres.

## All Needed Context

### Documentation & References

```yaml
# MUST READ — codebase patterns (all verified 2026-06-12, branch dev @ 2c71928)

- file: app/features/demo/schemas.py
  why: |
    DemoRunRequest lives at lines 29-61. ConfigDict(strict=True) at line 38.
    The `scenario` field (line 57) shows the Field(strict=False) override pattern
    for enum-on-the-wire; the NEW fields are JSON-native (str/Literal) so they
    need NO strict=False. Copy the comment style used for the PRP-38 scenario field.

- file: app/features/demo/pipeline.py
  why: |
    DemoContext dataclass at line 212 (add `workspace_id: str | None = None` after
    the PRP-41 fields at line 256). Orchestrator run_pipeline at line 2554: ctx is
    built at 2582-2587; the _Client context opens at 2595; the fail-path alias
    restore at 2661-2668; pipeline_complete is yielded at 2671-2691 — finalize the
    workspace BEFORE this yield and add "workspace_id" to its data dict (line 2681).
    The orchestrator MUST NEVER raise (contract in docstring, lines 2557-2558).

- file: app/features/demo/service.py
  why: |
    Single-flight asyncio.Lock at line 19 — only one pipeline runs at a time, so
    workspace-row writes have no concurrency races. run_pipeline_sync (line 46)
    builds DemoRunResult from the pipeline_complete event — no change needed there
    unless you surface workspace_id on DemoRunResult (optional, recommended:
    additive `workspace_id: str | None = None` field mirroring `winning_run_id`).

- file: app/features/demo/routes.py
  why: |
    POST /demo/run (line 38) and WS /demo/stream (line 57). The WS start frame is
    validated via DemoRunRequest.model_validate(raw) at line 73 — pydantic default
    (no extra="forbid") IGNORES unknown keys, so old/new clients interoperate.
    Routes have NO DB dependency today and need none — the workspace module opens
    its own sessions.

- file: app/features/batch/models.py
  why: |
    THE precedent for "a slice owns its own table": Base + TimestampMixin imports
    (lines 42-43), Mapped[]/mapped_column patterns, String(32) unique external id
    (line 143), JSONB columns (lines 145-146, 159-160), CheckConstraint +
    composite Index in __table_args__ (lines 166-180). Mirror this file's shape.

- file: app/features/scenarios/models.py
  why: |
    Second precedent: JSONB with server_default text("'[]'::jsonb") (lines 74-76),
    CHECK constraint naming convention ck_<table>_<col> (lines 102-115).
    GOTCHA in its docstring: SQLAlchemy reserves attribute name `metadata` —
    never name a column/attribute that.

- file: app/shared/models.py
  why: TimestampMixin (created_at/updated_at, server_default=func.now()) — use it.

- file: alembic/env.py
  why: |
    Lines 15-24: every slice with models registers via
    `from app.features.<slice> import models as <slice>_models  # noqa: F401`.
    ADD `from app.features.demo import models as demo_models  # noqa: F401`
    in alphabetical position (after data_platform, before explainability).

- file: alembic/versions/e4f5a6b7c8d9_add_model_selection_decision_promotion.py
  why: |
    CURRENT HEAD revision is e4f5a6b7c8d9 (verified `uv run alembic heads`).
    Your new migration's down_revision = "e4f5a6b7c8d9". Copy the header/docstring
    format, the typing (`revision: str`, `down_revision: str | None`), and the
    upgrade()/downgrade() docstring style.

- file: alembic/versions/43e35957a248_create_scenario_plan_table.py
  why: |
    create_table + named CheckConstraint + op.create_index (incl. GIN with
    postgresql_using='gin', lines 62-70) — the create-table migration to mirror.

- file: app/core/database.py
  why: |
    Base class + get_session_maker(). The workspace module opens sessions via
    get_session_maker() (NOT a request dependency) because run_pipeline is not
    request-scoped. Precedent: app/main.py:63-65 (lifespan) and the agents
    websocket per-message sessions.

- file: app/main.py
  why: |
    Lines 62-71 — the warn-and-continue pattern ("config must never block
    startup"): try/except Exception + logger.warning with error & error_type.
    Workspace writes use exactly this pattern ("workspace must never break the demo").

- file: app/features/scenarios/service.py
  why: |
    create_plan (line 354) — canonical async service write: build ORM object,
    db.add, await db.commit() (line 423), await db.refresh (line 424).
    Follow for create_workspace/finalize_workspace.

- file: app/core/exceptions.py
  why: |
    ForecastLabError subclasses → RFC 7807 via registered handlers. The 422 on
    workspace_name+ephemeral comes FREE from pydantic validation at the boundary
    (FastAPI → 422 problem+json via the validation handler); no manual raise needed.

- file: app/features/demo/tests/conftest.py
  why: |
    The demo test client fixture (ASGITransport over app.main.app); route tests
    monkeypatch the demo service so the real pipeline never runs.

- file: app/features/demo/tests/test_schemas.py
  why: |
    Existing DemoRunRequest tests INCLUDING the JSON-path convention
    (Model.model_validate({json-shaped dict}) — mandated by
    .claude/rules/security-patterns.md § strict mode). Extend this file.

- file: app/features/scenarios/tests/conftest.py
  why: |
    Integration DB fixture precedent (async_sessionmaker over create_async_engine,
    line 52-59) — copy for the workspace/model integration tests.

- file: docs/_base/API_CONTRACTS.md
  why: |
    The POST /demo/run row and "WebSocket Events (/demo/stream)" section document
    the start-frame fields — add the two new Optional fields + the additive
    pipeline_complete data.workspace_id key, in the same additive-note style as
    the PRP-38 scenario field.

# Issue / initiative context
- url: https://github.com/w7-mgfcode/ForecastLabAI/issues/390
  why: The epic this PRP implements (Foundation; blocks #391 #392 #393).
- url: https://github.com/w7-mgfcode/ForecastLabAI/issues/389
  why: Umbrella — success criteria + out-of-scope list (no export, no per-phase config, no endpoints beyond recording in E1).
```

### Current Codebase tree (relevant subset)

```bash
app/features/demo/
├── __init__.py
├── pipeline.py        # 2692 lines; DemoContext @212; run_pipeline @2554
├── routes.py          # POST /demo/run @38; WS /demo/stream @57
├── schemas.py         # DemoRunRequest @29; StepEvent @64; DemoRunResult @106
├── service.py         # asyncio.Lock single-flight @19
└── tests/
    ├── conftest.py    # ASGITransport client fixture
    ├── test_pipeline.py
    ├── test_routes.py
    └── test_schemas.py
alembic/
├── env.py             # model imports @15-24 (NO demo import yet)
└── versions/          # head: e4f5a6b7c8d9
```

### Desired Codebase tree (files added/modified)

```bash
app/features/demo/
├── models.py                          # NEW — ShowcaseWorkspace ORM (+ status constants)
├── workspace.py                       # NEW — create/finalize/get/list (session-maker based)
├── schemas.py                         # MOD — DemoRunRequest +preservation +workspace_name (+model_validator);
│                                      #       DemoRunResult +workspace_id (additive Optional)
├── pipeline.py                        # MOD — DemoContext.workspace_id; create/finalize hooks in run_pipeline
├── service.py                         # MOD — surface workspace_id on DemoRunResult (1 line in the final build)
└── tests/
    ├── test_schemas.py                # MOD — new-field defaults, JSON path, pattern, ephemeral+name=422, legacy frame
    ├── test_models.py                 # NEW — constraint + CRUD (integration)
    ├── test_workspace.py              # NEW — create/finalize/get/list (integration)
    ├── test_pipeline.py               # MOD — keep-mode creates+finalizes (workspace fns monkeypatched); ephemeral writes nothing
    └── test_routes.py                 # MOD — passthrough of new fields (service monkeypatched); WS legacy frame
alembic/
├── env.py                             # MOD — +demo models import
└── versions/a1b2c3d4e5f6_create_showcase_workspace_table.py   # NEW (id illustrative — generate your own 12-hex)
docs/_base/API_CONTRACTS.md            # MOD — additive contract notes
```

### Known Gotchas & Library Quirks

```python
# CRITICAL — strict mode: DemoRunRequest has ConfigDict(strict=True) (schemas.py:38).
#   The new fields are JSON-native (Literal[str] / str|None) → NO Field(strict=False)
#   needed. test_strict_mode_policy.py (AST walker) only fires on
#   date/datetime/time/UUID/Decimal — neither new field triggers it.

# CRITICAL — the orchestrator must NEVER raise (pipeline.py:2557 contract).
#   Wrap every workspace DB call in try/except Exception + logger.warning
#   (pattern: app/main.py:62-71). A dead Postgres must not kill the demo stream.

# CRITICAL — pipeline_complete is ALWAYS emitted (even on step failure via the
#   break at pipeline.py:2668). Finalize the workspace row BEFORE the final yield
#   at 2671 so the failure path records partial created_objects too.

# CRITICAL — NO ForeignKeys on showcase_workspace. ids are soft references.
#   ctx.winning_run_id et al. are plain strings produced by HTTP responses; the
#   referenced rows can be deleted independently (e.g. DELETE /registry/runs/{id}).

# GOTCHA — SQLAlchemy reserves the declarative attr name `metadata`
#   (scenarios/models.py:9-10). Use `created_objects` / `result_summary`.

# GOTCHA — external-id convention is uuid.uuid4().hex (32 chars, python-side),
#   String(32) unique+index — NOT server-side gen_random_uuid(). Matches
#   batch_job.batch_id (batch/models.py:143) and scenario_plan.scenario_id.

# GOTCHA — alembic/env.py MUST import the new models module (noqa: F401) or the
#   schema-validation autogenerate drift check will not see the table and a later
#   autogenerate would try to DROP it.

# GOTCHA — alembic revision ids in this repo are hand-written 12-hex strings
#   continuing the chain (head = e4f5a6b7c8d9). Either run
#   `uv run alembic revision -m "create showcase_workspace table"` and keep the
#   generated id, or hand-write one — but down_revision MUST be "e4f5a6b7c8d9".

# GOTCHA — WS start frame: DemoRunRequest.model_validate(raw) at routes.py:73 with
#   default model_config IGNORES unknown keys. Do NOT add extra="forbid" — that
#   would break forward/backward compatibility deliberately relied upon.

# GOTCHA — repo has mixed CRLF/LF line endings; check `git diff --stat` before
#   committing to avoid whole-file noise diffs (Write/Edit emit LF — fine for NEW
#   files; for schemas.py/pipeline.py edits, verify the diff is surgical).

# GOTCHA — mypy --strict AND pyright --strict both gate merge. New modules need
#   full annotations incl. return types on fixtures and `-> None` on tests.

# CONVENTION — commits: `feat(api): ... (#390)`; branch off dev:
#   feat/showcase-workspace-persistence-backbone (≤50 chars, kebab).
#   NO AI co-author trailer (hook-enforced).

# RUNTIME-VERIFICATION LOG (per prp-create step 3):
#   - `uv run alembic heads` → e4f5a6b7c8d9 (verified 2026-06-12)
#   - DemoRunRequest strict config + scenario strict=False → schemas.py:38,57 (read)
#   - No FastAPI/SQLAlchemy/Pydantic API is cited here beyond patterns already
#     working in-repo (JSONB, CheckConstraint, async_sessionmaker) — no external
#     library claims requiring a one-off import probe.
```

## Implementation Blueprint

### Data models and structure

```python
# app/features/demo/models.py  (NEW — mirror batch/models.py shape)
"""Showcase workspace ORM model.

First table owned by the demo slice (precedent: app/features/batch/models.py).
A row = one preserved showcase run: its configuration and the ids of every
object the pipeline created. All recorded ids are OPAQUE SOFT REFERENCES —
deliberately no ForeignKey to model_run / scenario_plan / batch_job /
agent_session, so cross-slice schema coupling stays zero and referenced rows
remain independently deletable.
"""
from __future__ import annotations
import datetime as _dt
from typing import Any
from sqlalchemy import CheckConstraint, Date, Index, Integer, String, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column
from app.core.database import Base
from app.shared.models import TimestampMixin

WORKSPACE_STATUS_RUNNING = "running"
WORKSPACE_STATUS_COMPLETED = "completed"
WORKSPACE_STATUS_FAILED = "failed"

class ShowcaseWorkspace(TimestampMixin, Base):
    __tablename__ = "showcase_workspace"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    workspace_id: Mapped[str] = mapped_column(String(32), unique=True, index=True)  # uuid4().hex
    name: Mapped[str | None] = mapped_column(String(100), nullable=True, index=True)
    status: Mapped[str] = mapped_column(
        String(20), default=WORKSPACE_STATUS_RUNNING, nullable=False, index=True
    )
    # Run configuration — replay inputs (E4 reads these verbatim).
    seed: Mapped[int] = mapped_column(Integer, nullable=False)
    scenario: Mapped[str] = mapped_column(String(40), nullable=False)   # ScenarioPreset.value
    reset: Mapped[bool] = mapped_column(nullable=False, default=False)
    skip_seed: Mapped[bool] = mapped_column(nullable=False, default=True)
    # Grain + window discovered by the status/seed steps (nullable: unknown on early failure).
    store_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    product_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    date_start: Mapped[_dt.date | None] = mapped_column(Date, nullable=True)
    date_end: Mapped[_dt.date | None] = mapped_column(Date, nullable=True)
    # Everything the run created — flexible JSONB (soft references, see module docstring).
    created_objects: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict, server_default=text("'{}'::jsonb")
    )
    # winner_model_type / winner_wape / wall_clock_s / any_fail — display payload.
    result_summary: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)

    __table_args__ = (
        CheckConstraint(
            "status IN ('running', 'completed', 'failed')",
            name="ck_showcase_workspace_status",
        ),
        Index("ix_showcase_workspace_status_created", "status", "created_at"),
    )
```

```python
# app/features/demo/schemas.py — DemoRunRequest additions (after `scenario`, line 61)
    # E1 (#390): preservation policy. Default "ephemeral" keeps legacy behaviour
    # byte-identical (no workspace row). Both fields are JSON-native, so the
    # model-level strict=True needs no per-field override.
    preservation: Literal["ephemeral", "keep"] = Field(
        default="ephemeral",
        description="'keep' records this run as a showcase_workspace row.",
    )
    workspace_name: str | None = Field(
        default=None,
        max_length=100,
        pattern=r"^[a-z0-9][a-z0-9\-_]*$",   # same pattern as registry alias_name
        description="Optional workspace label; requires preservation='keep'.",
    )

    @model_validator(mode="after")
    def _workspace_name_requires_keep(self) -> DemoRunRequest:
        if self.workspace_name is not None and self.preservation != "keep":
            raise ValueError("workspace_name requires preservation='keep'")
        return self
```

### List of tasks (dependency order)

```yaml
Task 1 — branch & issue hygiene:
  RUN: git switch dev && git pull && git switch -c feat/showcase-workspace-persistence-backbone
  VERIFY: gh issue view 390 --json state   # open

Task 2 — CREATE app/features/demo/models.py:
  - MIRROR shape: app/features/batch/models.py (Base+TimestampMixin, __table_args__)
  - CONTENT: ShowcaseWorkspace + 3 status constants (see blueprint above)
  - DOCSTRING: state the no-FK soft-reference decision explicitly

Task 3 — MODIFY alembic/env.py:
  - INSERT (alphabetical, after data_platform import at line 18):
    from app.features.demo import models as demo_models  # noqa: F401

Task 4 — CREATE migration alembic/versions/<rev>_create_showcase_workspace_table.py:
  - down_revision = "e4f5a6b7c8d9"
  - MIRROR: 43e35957a248_create_scenario_plan_table.py (create_table + named CHECK
    + op.create_index incl. unique index on workspace_id + composite status/created_at)
  - downgrade(): drop indexes then op.drop_table("showcase_workspace")
  - VERIFY locally: uv run alembic upgrade head && uv run alembic downgrade -1 && uv run alembic upgrade head

Task 5 — MODIFY app/features/demo/schemas.py:
  - ADD model_validator import from pydantic
  - ADD the two fields + validator to DemoRunRequest (blueprint above)
  - ADD to DemoRunResult: workspace_id: str | None = Field(default=None, description=...)
  - UPDATE DemoRunRequest docstring (the "every field is JSON-native" claim still holds — say so)

Task 6 — CREATE app/features/demo/workspace.py:
  - Module docstring: warn-and-continue contract; session-maker (not request-scoped)
  - async def create_workspace(req: DemoRunRequest) -> str | None
      # opens get_session_maker()() session; inserts row (uuid4().hex, status=running,
      # config from req); commit; returns workspace_id. On ANY Exception:
      # logger.warning("demo.workspace_create_failed", error=..., error_type=...); return None
  - async def finalize_workspace(workspace_id: str, ctx: DemoContext, *, failed: bool) -> None
      # loads row by workspace_id, sets status, store_id/product_id/date_start/date_end,
      # created_objects (see pseudocode), result_summary; commit. Warn-and-continue.
      # NOTE: import DemoContext under TYPE_CHECKING to avoid runtime import cycles
      # (pipeline imports workspace; workspace needs only the ctx type).
  - async def get_workspace(db: AsyncSession, workspace_id: str) -> ShowcaseWorkspace | None
  - async def list_workspaces(db: AsyncSession, *, limit: int = 50, offset: int = 0) -> list[ShowcaseWorkspace]
      # newest-first; unrouted in E1 — consumed by tests now, E4 routes later

Task 7 — MODIFY app/features/demo/pipeline.py:
  - DemoContext: ADD `workspace_id: str | None = None` after line 256 (PRP-41 block),
    with an `# E1 (#390)` comment matching the per-PRP comment convention
  - run_pipeline: AFTER ctx construction (line 2587):
      if req.preservation == "keep":
          ctx.workspace_id = await workspace.create_workspace(req)
  - run_pipeline: BEFORE the pipeline_complete yield (line 2671):
      if ctx.workspace_id is not None:
          await workspace.finalize_workspace(ctx.workspace_id, ctx, failed=any_fail)
  - pipeline_complete data dict: ADD "workspace_id": ctx.workspace_id
  - import: from app.features.demo import workspace  (module import, monkeypatch-friendly)

Task 8 — MODIFY app/features/demo/service.py:
  - run_pipeline_sync: thread workspace_id from final.data into DemoRunResult
    (mirror the winning_run_id line at service.py:77)

Task 9 — tests (see Validation Loop for the full matrix):
  - MODIFY tests/test_schemas.py  (unit)
  - CREATE tests/test_models.py   (@pytest.mark.integration)
  - CREATE tests/test_workspace.py(@pytest.mark.integration)
  - MODIFY tests/test_pipeline.py (unit — monkeypatch workspace.create_workspace/finalize_workspace)
  - MODIFY tests/test_routes.py   (unit — service monkeypatched)

Task 10 — MODIFY docs/_base/API_CONTRACTS.md:
  - POST /demo/run row: append "E1 (#390) — body accepts additive Optional
    `preservation: 'ephemeral'|'keep'` (default 'ephemeral') and `workspace_name`;
    `workspace_name` without `preservation='keep'` → 422."
  - WS /demo/stream section: same note on the start frame + "`pipeline_complete.data`
    gains additive `workspace_id` (string|null)."

Task 11 — gates, commit, PR:
  - RUN the five gates + integration suite (Validation Loop)
  - git diff --stat  # confirm surgical diffs (CRLF noise check)
  - COMMITS (reference #390, no AI trailer), e.g.:
      feat(api): add showcase_workspace model and migration (#390)
      feat(api): record demo run objects into showcase workspace (#390)
      docs(api): document preservation and workspace_name fields (#390)
  - PR into dev; title `feat(api): showcase workspace persistence backbone (#390)`
```

### Per-task pseudocode — the finalize payload (Task 6)

```python
def _collect_created_objects(ctx: DemoContext) -> dict[str, Any]:
    """Map DemoContext accumulator fields -> created_objects JSONB.

    Every value is already a plain str/None on ctx (HTTP response payloads).
    Drop None values so the JSONB stays sparse and greppable.
    """
    raw: dict[str, Any] = {
        "winning_run_id": ctx.winning_run_id,          # pipeline.py:234
        "v2_run_id": ctx.v2_run_id,                    # :237
        "v2_model_path": ctx.v2_model_path,            # :238  (artifact path)
        "alias": "demo-production" if ctx.winning_run_id else None,  # DEMO_ALIAS
        "agent_session_id": ctx.session_id,            # :235
        "batch_id": ctx.batch_id,                      # :245
        "scenario_plan_ids": [
            s for s in (ctx.price_cut_scenario_id, ctx.holiday_scenario_id) if s
        ],                                             # :250-251
        "scenario_artifact_key": ctx.scenario_artifact_key,  # :249
        "train_model_types": sorted(ctx.train_results),      # :230 (keys only)
        "stale_alias_run_id": ctx.stale_alias_run_id,  # :243 (PRP-39 controlled row)
    }
    return {k: v for k, v in raw.items() if v not in (None, [])}

# finalize_workspace core (warn-and-continue wrapper around ALL of it):
async def finalize_workspace(workspace_id: str, ctx: "DemoContext", *, failed: bool) -> None:
    try:
        session_maker = get_session_maker()
        async with session_maker() as db:
            row = (await db.execute(
                select(ShowcaseWorkspace).where(ShowcaseWorkspace.workspace_id == workspace_id)
            )).scalar_one_or_none()
            if row is None:        # create failed earlier — nothing to finalize
                return
            row.status = WORKSPACE_STATUS_FAILED if failed else WORKSPACE_STATUS_COMPLETED
            row.store_id, row.product_id = ctx.store_id, ctx.product_id
            row.date_start, row.date_end = ctx.date_start, ctx.date_end
            row.created_objects = _collect_created_objects(ctx)
            row.result_summary = {
                "winner_model_type": ctx.winner_model_type,
                "winner_wape": ctx.winner_wape,
            }
            await db.commit()
    except Exception as exc:  # workspace must never break the demo (app/main.py:62 pattern)
        logger.warning("demo.workspace_finalize_failed",
                       workspace_id=workspace_id, error=str(exc), error_type=type(exc).__name__)
```

### Integration Points

```yaml
DATABASE:
  - migration: create showcase_workspace (PK id, unique workspace_id, CHECK status,
    composite ix status+created_at, JSONB created_objects/result_summary)
  - registration: alembic/env.py demo models import (Task 3)

CONFIG: none — no new settings, no env vars.

ROUTES: none added in E1. Existing /demo/run + /demo/stream gain fields via schema only.

FRONTEND: none in E1 (epic #393/E4 wires the UI; adding the optional fields to
  frontend/src/types/api.ts DemoRunRequest interface is additive whenever needed).

DOCS: docs/_base/API_CONTRACTS.md additive notes (Task 10). RUNBOOKS/DOMAIN_MODEL
  sweeps belong to the E5 release gate — do not scope-creep them here.
```

## Validation Loop

### Level 1: Syntax & Style

```bash
uv run ruff check . && uv run ruff format --check .
uv run mypy app/ && uv run pyright app/
# Expected: clean. Both type checkers are --strict and gate merge.
```

### Level 2: Unit Tests (no DB)

```python
# tests/test_schemas.py — add:
def test_demo_run_request_new_field_defaults() -> None: ...
    # DemoRunRequest() -> preservation == "ephemeral", workspace_name is None

def test_demo_run_request_json_path_keep_with_name() -> None: ...
    # DemoRunRequest.model_validate({"preservation": "keep", "workspace_name": "bf-demo"})
    # — the MANDATORY json-dict path per security-patterns.md

def test_demo_run_request_legacy_frame_still_validates() -> None: ...
    # model_validate({"seed": 7}) — no new keys — passes; defaults applied

def test_demo_run_request_workspace_name_requires_keep() -> None: ...
    # pytest.raises(ValidationError): model_validate({"workspace_name": "x"})

def test_demo_run_request_workspace_name_pattern_rejected() -> None: ...
    # "Black Friday!" and "-leading-dash" both raise ValidationError

# tests/test_pipeline.py — add (monkeypatch app.features.demo.pipeline.workspace):
async def test_run_pipeline_keep_creates_and_finalizes_workspace(...) -> None: ...
    # stub create_workspace -> "ws123"; run with canned _Client responses;
    # assert finalize called once with failed matching outcome;
    # assert pipeline_complete data["workspace_id"] == "ws123"

async def test_run_pipeline_ephemeral_touches_no_workspace(...) -> None: ...
    # stubs assert_not_called

async def test_run_pipeline_workspace_create_failure_does_not_break_run(...) -> None: ...
    # create_workspace returns None (its warn path) -> pipeline still completes,
    # data["workspace_id"] is None

# tests/test_routes.py — add (service monkeypatched per existing pattern):
async def test_run_demo_accepts_preservation_fields(client) -> None: ...
async def test_run_demo_rejects_name_without_keep_422(client) -> None: ...
    # response.status_code == 422; content-type application/problem+json
```

```bash
uv run pytest app/features/demo -v -m "not integration"
uv run pytest app/core/tests/test_strict_mode_policy.py -v   # AST walker still green
```

### Level 3: Integration (real Postgres)

```python
# tests/test_models.py + tests/test_workspace.py — @pytest.mark.integration,
# session fixture copied from app/features/scenarios/tests/conftest.py:52-59.
# Cases: insert/read roundtrip incl. JSONB; duplicate workspace_id -> IntegrityError;
# status CHECK violation -> IntegrityError; create_workspace persists config;
# finalize_workspace(failed=True/False) sets status + payloads; finalize on a
# missing id is a silent no-op; list_workspaces newest-first + limit/offset.
```

```bash
docker compose up -d
uv run alembic upgrade head
uv run alembic downgrade -1 && uv run alembic upgrade head   # downgrade is clean
uv run pytest app/features/demo -v -m integration
```

### Level 4: Manual smoke (seeded local stack, uvicorn on :8123)

```bash
curl -s -X POST http://localhost:8123/demo/run \
  -H 'Content-Type: application/json' \
  -d '{"skip_seed": true, "preservation": "keep", "workspace_name": "e1-smoke"}' | python3 -m json.tool | head -20
# Expect overall_status pass + workspace_id non-null. Then:
docker exec forecastlab-postgres psql -U forecastlab -d forecastlab -c \
  "SELECT workspace_id, name, status, created_objects FROM showcase_workspace ORDER BY created_at DESC LIMIT 1;"
# Expect: status=completed, created_objects with winning_run_id etc.
curl -s -X POST http://localhost:8123/demo/run -H 'Content-Type: application/json' \
  -d '{"workspace_name": "bad"}' | python3 -m json.tool   # 422 problem+json
```

## Final validation Checklist

- [ ] All five gates green: `uv run ruff check . && uv run ruff format --check . && uv run mypy app/ && uv run pyright app/ && uv run pytest -v -m "not integration"`
- [ ] Integration suite green: `uv run pytest -v -m integration` (fresh docker-compose DB)
- [ ] Migration upgrade + downgrade clean on a fresh DB; env.py imports demo models
- [ ] Legacy start frame (`{"seed": 42}`) behaves byte-identically (no row, no workspace key absent — `workspace_id: null` present in pipeline_complete data is the ONLY delta, and it is additive)
- [ ] Manual smoke (Level 4) passes: keep→row recorded, ephemeral→no row, name-without-keep→422
- [ ] `git diff --stat` shows surgical diffs (no CRLF whole-file noise)
- [ ] docs/_base/API_CONTRACTS.md updated additively
- [ ] Commits formatted `feat(api)/docs(api): ... (#390)`, no AI trailer; PR into dev

---

## Anti-Patterns to Avoid

- ❌ Don't add ForeignKeys from showcase_workspace to other slices' tables — soft references only.
- ❌ Don't let a workspace DB error propagate out of run_pipeline — warn-and-continue, always.
- ❌ Don't add `extra="forbid"` to DemoRunRequest — unknown-key tolerance is the WS compat contract.
- ❌ Don't add list/get HTTP routes — that's epic #393 (E4); E1 ships the helpers unrouted.
- ❌ Don't touch the localStorage history or any frontend file — E1 is backend-only.
- ❌ Don't edit existing migrations — new revision off head e4f5a6b7c8d9.
- ❌ Don't import another feature slice from app/features/demo/ — core/shared only.

## Confidence Score

**9/10** for one-pass implementation success. Every pattern has a verified in-repo
precedent (batch models, scenarios migration, lifespan warn-and-continue, demo test
monkeypatching); the two open judgment calls (exact `created_objects` key set and
whether `DemoRunResult.workspace_id` is surfaced) are both specified above and both
additive — a wrong guess costs a follow-up field, not a rework. The −1 is for the
pipeline-unit-test fixtures: canned `_Client` response sequences are fiddly and may
need iteration against the existing `test_pipeline.py` harness.
