# Code architecture

A tour of `app/`: nineteen vertical slices, the shared layers beneath them, and the one import rule that holds it together.

**Purpose:** find the code that owns a behavior, and understand why the boundaries are where they are.
**Intended reader:** integrators reading or extending the backend.

## What you'll accomplish

The ability to locate any capability in the tree, and to add code without violating the structure.

## The shape

```
app/
├─ main.py          FastAPI app: lifespan, middleware, router wiring
├─ core/            cross-cutting infrastructure
├─ shared/          domain code shared across slices
└─ features/        19 vertical slices
```

## Vertical slices

Every domain lives under `app/features/<slice>/` and owns its full stack:

```
app/features/<slice>/
├─ models.py     SQLAlchemy ORM (Mapped[] + mapped_column())
├─ schemas.py    Pydantic v2 request/response contracts
├─ service.py    business logic
├─ routes.py     the HTTP surface
└─ tests/        the slice's tests
```

The nineteen slices:

| Group | Slices |
|---|---|
| **Platform** | `data_platform`, `ingest`, `dimensions`, `analytics`, `seeder`, `config` |
| **Modelling** | `featuresets`, `forecasting`, `backtesting`, `model_selection`, `explainability`, `scenarios` |
| **Orchestration** | `jobs`, `batch`, `registry`, `ops`, `demo` |
| **Conversational** | `rag`, `agents` |

Routers are wired in `app/main.py` — twenty `include_router` calls, since `agents` contributes both a REST router and a WebSocket router.

## The one rule

> **A slice may not import from another slice.**

Cross-cutting code goes through `app/core/` or `app/shared/`. The import graph is one-way: `app/features/* → app/shared/` and `app/features/* → app/core/`, never sideways.

This is the constraint that keeps nineteen slices legible. Without it, `forecasting` reaches into `registry`, `registry` reaches back into `forecasting`, and within a few features the system has no boundaries left to reason about.

### What the rule actually prevents — a real example

`ModelFamily` and `model_family_for` originally lived in the `forecasting` slice. But `registry.schemas` needed `ModelFamily` at module scope for the `RunResponse.model_family` computed field.

That single cross-slice import forced lazy-import workarounds across the registry boundary — because the eager import created a `forecasting ↔ registry` cycle that broke Alembic cold-boot. The fix was to move the enum to `app/shared/model_taxonomy.py`, restoring the one-way graph.

The lesson generalises: when two slices need the same domain type, the type belongs in `app/shared/`, not in whichever slice defined it first.

## `app/core/` — infrastructure

| Module | Owns |
|---|---|
| `config.py` | The `Settings` class and the cached `get_settings()`. |
| `database.py` | Async engine and session maker. |
| `exceptions.py` | The `ForecastLabError` hierarchy. |
| `problem_details.py` | The RFC 7807 envelope and the `type` URI registry. |
| `logging.py` | structlog configuration and `get_logger`. |
| `middleware.py` | `RequestIdMiddleware`. |
| `health.py` | The unprefixed `/health` router. |

`exceptions.py` defines the domain error hierarchy — `NotFoundError`, `ValidationError`, `DatabaseError`, `ConflictError`, `BadRequestError`, `UnprocessableEntityError`, `GatewayTimeoutError`, `EmbeddingProviderAuthError`, `AgentFallbackExhaustedError` — and `problem_details.py` maps each to a stable `type` URI. Raising a domain exception anywhere produces a correctly-shaped problem response without the route knowing anything about HTTP error formatting.

## `app/shared/` — shared domain code

| Module | Owns |
|---|---|
| `model_taxonomy.py` | `ModelFamily`, `model_family_for`, `KNOWN_MODEL_TYPES`. |
| `feature_frames/` | The V2 feature contract: `FeatureGroup`, group ordering, column manifests. |
| `seeder/` | The Forge: scenario presets, generators, config. |

`KNOWN_MODEL_TYPES` is a public allow-list derived from the canonical family map, so a slice that must validate a `model_type` (the `demo` slice, for instance) can check membership without importing a sibling slice. It is derived rather than duplicated — it cannot drift — and a test locks that.

## `app/main.py` — composition

The application factory: configures logging, re-applies persisted runtime config overrides onto the `Settings` singleton, registers exception handlers, adds CORS and `RequestIdMiddleware`, and wires every router.

The startup override re-application is what makes `/admin` → AI Models changes survive a restart: the same mechanism that applies a live change also replays stored overrides at boot.

## Conventions

**ORM** — SQLAlchemy 2.0 with `Mapped[]` and `mapped_column()`, async sessions throughout.

**Validation** — Pydantic v2 at every boundary: HTTP, agent tools, seeder config.

**Configuration** — always `get_settings()`. **Never `os.environ` in feature code.** That rule is what makes the [configuration reference](../configuration.md) a complete list rather than a best guess.

**Paths** — `pathlib.Path`, never `os.path`.

**Errors** — raise a domain exception from `app/core/exceptions.py`. Never a bare `HTTPException` with a raw string; never an ad-hoc error shape.

**Migrations** — every schema change ships an Alembic migration, and migrations are **forward-only once merged**.

**Time-safety** — feature engineering must prevent leakage: `shift(lag)`, `shift(1).rolling()`, entity-aware `groupby`. `app/features/featuresets/tests/test_leakage.py` is the specification, and weakening it is forbidden.

## Two flows through the package

**A forecast request:** `main.py` (startup, once) → `RequestIdMiddleware` assigns the correlation id → `forecasting/routes.py` → `schemas` validates → `forecasting/service.py` → the fitted artifact → `schemas` validates the response → structured log event.

**A champion selection:** `model_selection/routes.py` accepts and returns `202` → the async runner backtests each candidate under a global concurrency bound → results rank by WAPE with the fixed tie-break chain → `train-winner` or `train-selected` fits the chosen model → `promote` writes a `model_run` through the `registry` slice's *HTTP-independent* service boundary and records a `promotion_decision` audit.

Note the asymmetry in the second flow: sequencing lives in the slice's service, while the modules it calls stay individually testable. That is the same division the demo script makes at a larger scale — `scripts/run_demo.py` drives only the published HTTP surface and never imports `app.features.*`, so drift between the deployed API and its runtime behavior shows up as a real failure rather than passing silently.

## Frontend

`frontend/` is React 19 + TypeScript with Vite 7, Tailwind 4, shadcn/ui, TanStack Query and Table, React Router 7, and Recharts. Pages live in `frontend/src/pages/`, mirroring the dashboard nav — `explorer/`, `visualize/`, plus top-level pages.

It talks to the backend over the same public REST API documented in [API reference](api-reference.md); there is no privileged channel.

## Next

- [Data model](data-model.md) — the tables these slices own.
- [Extending ForecastLabAI](extending.md) — adding to this structure safely.
