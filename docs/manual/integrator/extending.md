# Extending ForecastLabAI

What to change, how to change it, and the short list of things that must not change.

**Purpose:** add capability without breaking the guarantees the rest of the manual describes.
**Intended reader:** integrators contributing code.

## What you'll accomplish

A change that fits the architecture, ships with its tests and migration, and passes the gates on the first try.

## Before anything: what must not change

These are not style preferences. Each one, if broken, silently invalidates something the system claims.

| Invariant | Why it exists |
|---|---|
| **Never weaken `app/features/featuresets/tests/test_leakage.py`.** | It *is* the leakage specification. Weakening it makes every accuracy number unfalsifiable. |
| **Never edit a merged Alembic migration.** | Migrations are forward-only. Editing one diverges every database that already applied it. Add a new migration. |
| **Never import one feature slice from another.** | The one-way import graph is what keeps 19 slices tractable. Shared types go in `app/shared/`. |
| **Never read `os.environ` in feature code.** | `get_settings()` is what makes the [configuration reference](../configuration.md) complete rather than approximate. |
| **Never build SQL by string concatenation.** | Parameter binding only. |
| **Never add a managed-cloud SDK to `app/`.** | It violates the single-host vision that makes `docker compose up` sufficient. |
| **Never widen an agent's mutation surface without adding the tool to `agent_require_approval`.** | That list is the human-in-the-loop boundary. |
| **Never skip Ruff, mypy `--strict`, or pyright `--strict`.** | All three gate merge. |
| **Never mock the database in integration tests.** | They must run against real Compose Postgres or they prove nothing. |
| **Never add an AI co-author or "Generated with" commit trailer.** | A hook enforces this. |

The full list lives in [AGENTS.md](../../../AGENTS.md); this is the subset an extension is most likely to hit.

## Adding a forecasting model

The model taxonomy is deliberately small to change:

1. **Implement the model** in `app/features/forecasting/`, following the existing model classes.
2. **Add the `model_type` literal** to the `ModelType` union in `app/features/forecasting/models.py`.
3. **Add the mapping** to `_MODEL_FAMILY_MAP` in `app/shared/model_taxonomy.py`. A drift-lock test asserts the map covers every known model type — miss this and it fails.
4. **Gate it if it needs an optional dependency**: add a `forecast_enable_<model>` setting and a `pyproject.toml` extra, following `lightgbm` and `xgboost`. Pure-scikit-learn models need only the flag, like `random_forest`.
5. **Decide the feature frame.** A model consuming features belongs to `tree` or `additive` and gains V2 support; a target-only model is a `baseline` and must reject V2.
6. **Ship tests.**

**Forgetting step 3 does not crash.** `model_family_for` classifies unknown types as `baseline` and logs a warning — forward-compatible by design. Your model will simply appear as a baseline in the dashboard, get the wrong badge, and be excluded from feature-importance routing. The drift-lock test exists precisely because this failure is quiet.

`KNOWN_MODEL_TYPES` is derived from the same map, so cross-slice validation updates itself.

## Adding a feature pack

1. Add the member to `FeatureGroup` in `app/shared/feature_frames/contract_v2.py`.
2. Add it to `_GROUP_ORDER` — the manifest emits columns in exactly this order.
3. Add its column manifest to `_GROUP_COLUMNS`.
4. Decide default membership. `DEFAULT_V2_GROUPS` holds six; sidecar packs reading tables a small seeded database may not populate stay **off**.
5. Add a safety class if it reads a column a production pipeline must supply — that becomes the `Requires supplied data` chip.
6. **Prove time-safety.** A pack reading a new table is exactly where leakage enters.

Remember the semantics: a disabled group's columns are **omitted entirely**, not NaN-filled. A NaN inside an *enabled* group means "source data unknown for this day", which the tree models handle natively.

## Adding a slice

Only when a genuinely new domain appears — not for a variation on an existing one.

```
app/features/<slice>/
├─ models.py     Mapped[] + mapped_column()
├─ schemas.py    Pydantic v2
├─ service.py    business logic
├─ routes.py     APIRouter with a prefix
└─ tests/
```

Then wire the router in `app/main.py`, ship an Alembic migration for any tables, and keep imports one-way.

If your new slice needs a type from an existing one, that type belongs in `app/shared/` — see the `ModelFamily` history in [Code architecture](code-architecture.md#what-the-rule-actually-prevents--a-real-example).

## Adding an endpoint

- Validate with Pydantic v2 at the boundary.
- Raise domain exceptions from `app/core/exceptions.py`; never a bare `HTTPException` with a raw string.
- Choose the error type deliberately: `validation` (the input is wrong) versus `unprocessable-entity` (the state forbids it). Clients branch on this — see [API reference](api-reference.md#the-distinction-that-matters-most).
- Ship a route test covering the 2xx path **and at least one error path**.

## Adding an agent tool

Read-only tools run immediately. **A tool that mutates state must be added to `agent_require_approval`** — otherwise the agent can perform that mutation with nobody in the loop.

That is why `save_scenario` joined `create_alias` and `archive_run` when the experiment agent gained scenario persistence: the capability and its gate landed together.

## Changing configuration

Add the field to `Settings` in `app/core/config.py`. It becomes settable by the upper-case environment variable automatically.

Then: document it in the [configuration reference](../configuration.md), add it to `.env.example` if deployments will commonly change it, and note whether it needs a restart. Almost everything does — `get_settings()` is cached. The AI-model settings are the exception, going through the `app_config` override mechanism.

## Schema changes

```bash
uv run alembic revision --autogenerate -m "description"
# review the generated migration — autogenerate is a draft, not an answer
uv run alembic upgrade head
```

Review before committing: autogenerate misses server defaults, index intent, and data migrations. Once merged, it is immutable.

## Tests

- Every new module, public function, endpoint, ORM model, and migration ships with a test.
- Every bug fix ships a **regression test that would have caught it**.
- Unit tests mock external services — OpenAI, Anthropic, Ollama.
- Integration tests are marked `@pytest.mark.integration` and run against **real** Compose Postgres.

```bash
uv run pytest -v -m "not integration"     # no DB needed
uv run pytest -v -m integration           # needs docker compose up
```

## Before you commit

```bash
uv run ruff check . && uv run ruff format --check .
uv run mypy app/ && uv run pyright app/
uv run pytest -v -m "not integration"
```

Frontend work adds `cd frontend && pnpm tsc --noEmit && pnpm lint && pnpm test --run`.

Details in [CI and quality gates](ci-and-quality-gates.md).

## Stop and ask before

- Cutting `dev` → `main`, or pushing any tag — release-please owns tagging.
- Bumping pydantic-ai, FastAPI, or SQLAlchemy major versions.
- Widening an agent's mutation surface.

## Next

- [CI and quality gates](ci-and-quality-gates.md) — what runs, and the branch and commit conventions.
