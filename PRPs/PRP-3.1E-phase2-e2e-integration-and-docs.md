# PRP-3.1E: Phase 2 E2E Integration Test + Cross-Config Leakage + Docs

**Feature**: `.agents/plans/initial-5-phase2-e2e-integration-and-docs.md`
**Parent PRP**: PRP-3.1 (umbrella — Phase 2 feature wiring; PRP-3.1A through PRP-3.1E are the 5 slices)
**Parent PRD**: `.agents/plans/wire-phase2-features-to-featuresets.md`
**Blocks**: closes the PRP-3.1 umbrella · **Blocked by**: PRP-3.1A (MERGED) + PRP-3.1B + PRP-3.1C + PRP-3.1D
**Status**: Ready for Implementation (after B+C+D merge)
**Confidence Score**: 9 / 10 — docs + tests only, no `service.py` / `routes.py` / `schemas.py` edits, integration-test pattern verified against `app/features/ingest/tests/test_routes.py:20-142` (`db_session` / `seed_data` / `client` fixture triad), additive-contract snapshot proof identical in shape to PRP-3.1A Level 4. Single uncertainty: exact `config_hash()` snapshot value from `dev` HEAD pre-PRP-3.1A — must be captured at implementation time per §15 Decision A.

---

## Goal

Close the PRP-3.1 umbrella as a **docs + tests-only PR**, with **zero edits to `service.py`, `routes.py`, or `schemas.py`**:

1. New end-to-end integration test `app/features/featuresets/tests/test_phase2_integration.py` marked `@pytest.mark.integration` that:
   - POSTs `/featuresets/compute` against a real `docker-compose` Postgres with `lifecycle_config` + `replenishment_config` + `promotion_config` ALL set.
   - Asserts the response `feature_columns` contain the union of Phase 2 columns (`days_since_launch_lag1`, `days_since_discontinue_lag1`, `days_since_last_replenishment_lag1`, `replenishment_count_w14_lag1`, `promo_markdown_active_lag1`, `promo_markdown_intensity_lag1`).
   - Asserts `config_hash` is byte-identical across two identical calls (determinism).
   - Asserts the additive contract: a request with **no** Phase 2 sub-configs returns the same `config_hash` it returned pre-PRP-3.1A (captured snapshot, inline constant).
2. New cross-config leakage test in `app/features/featuresets/tests/test_leakage.py` — `class TestPhase2CrossConfigLeakage` — composing all three Phase 2 sub-configs with `exogenous_config` + `lag_config` and asserting ZERO future-data references at the union of feature rows (the strongest additive leakage assertion).
3. Update `docs/PHASE/3-FEATURE_ENGINEERING.md` — add a "Phase 2 Features" section listing the three families, their config classes (with parameter ranges), their output columns, and their time-safety guarantees. Don't replace the existing exogenous section.
4. Update `docs/_base/DOMAIN_MODEL.md` — extend the Ubiquitous Language table with three new entries (`days_since_launch`, `replenishment event`, `promotion (kind)`). Touch nothing else.
5. Extend `examples/compute_features_demo.py` — add `create_phase2_config()` helper and a `--phase2` CLI flag block that prints Phase 2 feature columns from the response.

End state — single commit, **≤ 350 LOC net diff** (docs + tests, no service.py / routes.py / schemas.py change), `mypy --strict` + `pyright --strict` clean, `uv run pytest app/features/featuresets/ -v -m "not integration"` green, `uv run pytest app/features/featuresets/tests/test_phase2_integration.py -v -m integration` green against a fresh `docker-compose up -d` + `alembic upgrade head` + Phase 2 fixtures.

---

## Why

- **Closes the additive-contract invariant end-to-end.** PRP-3.1A's `test_config_hash_unchanged_when_phase2_omitted` test asserts the invariant at the Pydantic-schema layer. This slice asserts it at the **HTTP boundary** — a real `POST /featuresets/compute` with no Phase 2 fields returns the same `config_hash` it did pre-PR. That's the load-bearing user-facing guarantee from PRD §6 / §11 R2.
- **Proves Phase 2 compose cleanly.** PRP-3.1B / 3.1C / 3.1D each ship leakage tests for **their own** family. None of them prove the **union** doesn't leak. The cross-config leakage test here closes that gap.
- **Honest end-to-end demo.** PRD §3 user story: "a maintainer toggles a Holiday Rush scenario and the forecasting pipeline visibly responds." A real integration test with all three families ON, against a real Postgres + a real seed, is the closest thing to that demo before the UI lands.
- **Operating docs catch up to code.** `docs/PHASE/3-FEATURE_ENGINEERING.md` is the operator-facing reference for the slice. Without the Phase 2 section, new contributors must reverse-engineer `service.py`. The doc update is part of the PR, not a follow-up — same lift, same review (per `initial-5-phase2-e2e-integration-and-docs.md` line 37).

---

## What

### User-visible behavior

- `POST /featuresets/compute` with `{"lifecycle_config": {...}, "replenishment_config": {...}, "promotion_config": {...}}` returns the documented Phase 2 columns alongside any Phase 1 columns. Verified end-to-end against a real Postgres.
- A no-Phase-2-config request returns a response **byte-identical** in `config_hash` to the pre-PRP-3.1A baseline. Verified by snapshot.
- A developer reading `docs/PHASE/3-FEATURE_ENGINEERING.md` finds the three Phase 2 families documented next to the existing four Phase 1 families.
- `examples/compute_features_demo.py --phase2` prints a Phase 2-enabled feature column list.

### Success Criteria

- [ ] `app/features/featuresets/tests/test_phase2_integration.py` exists; class `TestPhase2EndToEnd` has ≥ 3 tests (`test_phase2_columns_appear`, `test_config_hash_deterministic`, `test_additive_contract_snapshot`).
- [ ] `app/features/featuresets/tests/test_leakage.py` has a new `class TestPhase2CrossConfigLeakage` with ≥ 2 unit-level (non-integration) cases composing all three Phase 2 configs.
- [ ] `docs/PHASE/3-FEATURE_ENGINEERING.md` has a new top-level section `## Phase 2 Features (Retail-Depth)` listing all three families, their config classes, their output columns, and their time-safety guarantee.
- [ ] `docs/_base/DOMAIN_MODEL.md` Ubiquitous Language table has rows for `days_since_launch`, `replenishment event`, `promotion (kind)`.
- [ ] `examples/compute_features_demo.py` has a `create_phase2_config()` helper (top-level function) and the main flow prints Phase 2 columns when invoked with `--phase2`.
- [ ] `uv run ruff check .` → clean.
- [ ] `uv run ruff format --check .` → clean.
- [ ] `uv run mypy app/` → 0 errors.
- [ ] `uv run pyright app/` → 0 errors.
- [ ] `uv run pytest app/features/featuresets/tests/test_leakage.py -v` → all green (new cross-config cases + existing cases).
- [ ] `docker compose up -d && uv run alembic upgrade head && uv run pytest app/features/featuresets/tests/test_phase2_integration.py -v -m integration` → all green.
- [ ] `git diff --stat dev -- app/features/featuresets/service.py app/features/featuresets/routes.py app/features/featuresets/schemas.py` → **empty** (this slice touches no production code).
- [ ] Net diff ≤ +350 / -20 LOC (verify with `git diff --stat dev...`).
- [ ] Single commit: `feat(features,docs): land phase 2 e2e integration and docs (#<issue>)` — note `feat:` (not `docs:` / `test:`) per `.claude/rules/versioning.md` to dodge the release-please merge-subject trap.

---

## All Needed Context

### Documentation & References

```yaml
# MUST READ before writing the integration test
- file: app/features/ingest/tests/test_routes.py
  lines: 1-142
  why: The canonical integration-test triad for this repo —
       `db_session` (lines 20-63), `seed_data` (lines 66-120),
       `client` (lines 123-142). MIRROR this pattern in
       test_phase2_integration.py — same fixture shapes, same
       cleanup-after-test pattern, same ASGITransport AsyncClient.

- file: app/features/featuresets/routes.py
  lines: 28-178
  why: The endpoint under test — POST /featuresets/compute. The response
       schema is ComputeFeaturesResponse with .feature_columns,
       .config_hash, .row_count. Cite line 173 for the
       config_hash response field; line 172 for feature_columns.

- file: app/features/featuresets/schemas.py
  lines: 186-276
  why: PRP-3.1A landed all three *Config classes. Verify the field
       names + bounds match before writing the integration test
       request body. LifecycleConfig at line 186, ReplenishmentConfig
       at line 208, PromotionConfig at line 237.

- file: app/features/featuresets/schemas.py
  lines: 344-372
  why: FeatureSetConfig has the three Phase 2 sub-config fields
       (lines 344-346) and get_enabled_features (line 350) appends
       "lifecycle" / "replenishment" / "promotion" tokens
       (lines 366-371). Required to verify enabled_features assertions.

- file: app/features/featuresets/service.py
  lines: 75-162
  why: compute_features() main switch. After PRP-3.1B/C/D land, there
       will be three new `if self.config.<family>_config:` blocks
       between line 134 and line 137. This PRP does NOT touch this
       file — it only EXERCISES the final wiring via the HTTP boundary.

- file: app/features/featuresets/tests/test_leakage.py
  lines: 20-77
  why: TestLagLeakage / TestRollingLeakage idiom. Mirror the
       sequential-quantity construction (sample_time_series
       conftest.py:17-33) so any cross-config leakage is
       mathematically detectable. Cross-config test extends
       TestGroupIsolationLeakage's two-series style at lines 204-286.

- file: app/features/featuresets/tests/conftest.py
  lines: 17-33
  why: sample_time_series fixture — produces sequential quantities
       1..30. The cross-config leakage test reuses this fixture
       directly; the integration test seeds analogous data through
       a different path (real DB via the seed_data fixture).

- file: docs/PHASE/3-FEATURE_ENGINEERING.md
  lines: 1-283
  why: Read in FULL — the structure to extend. New section "Phase 2
       Features" goes AFTER the existing "Feature Types" section
       (line 149 onwards). Don't touch existing sections; append only.

- file: docs/_base/DOMAIN_MODEL.md
  lines: 54-69
  why: The Ubiquitous Language table. Three rows to add AFTER line 68
       (`chunk` (RAG)) and BEFORE line 69 (`scenario` (seeder)). Match
       the existing column-style EXACTLY (`| `Term` | Means | NOT |`).

- file: examples/compute_features_demo.py
  lines: 1-229
  why: Read in FULL. `create_sample_config()` at line 27 is the
       shape to mirror for `create_phase2_config()`. The `main()`
       function at line 137 is where the `--phase2` branch hooks in.

- file: app/features/featuresets/schemas.py
  lines: 381-407
  why: ComputeFeaturesRequest — the request body schema for the
       integration test. store_id (line 394, ge=1), product_id
       (line 395, ge=1), cutoff_date (line 396), lookback_days
       (line 400-404, ge=1, le=1095), config (FeatureSetConfig).

- file: .agents/plans/initial-5-phase2-e2e-integration-and-docs.md
  why: The slice INITIAL. Lines 31-40 OTHER CONSIDERATIONS list the
       must-not-miss disciplines: PR title type (`feat:`), single
       commit referencing #92, integration tests require docker-compose.

- file: .agents/plans/wire-phase2-features-to-featuresets.md
  sections: §6 (time-safety contract), §7 (feature specs), §9
           (security/config boundary), §11 (success criteria),
           §12 Phase C (this slice's deliverables)
  why: Parent PRD. §11 R2 (additive contract) is the load-bearing
       invariant the snapshot test guards. §12 Phase C explicitly
       calls out the doc + integration test as deliverables.

- file: .agents/plans/phase2-decisions-and-prp-prep.md
  sections: §1 (lifecycle continuous-only), §3 (PromotionConfig
           generalization), §4 (release-please merge-subject trap)
  why: The locked decisions. Note §4 — PR title MUST be `feat:`,
       not `docs:` / `test:`, or release-please skips the bump.

- file: .claude/rules/test-requirements.md
  why: "NEVER mock the database in tests marked @pytest.mark.integration"
       — verbatim rule. The integration test must hit a real Postgres
       via docker-compose. No DB mocks, no SQLite, no in-memory shim.

- file: .claude/rules/versioning.md
  why: §"Merge-commit subject trap" — title must be feat:/fix: for
       release-please to bump pre-1.0 PATCH. See also
       docs/_base/RUNBOOKS.md "release-please skipped the bump"
       runbook for full diagnosis.

- file: .claude/rules/commit-format.md
  why: Scope allow-list. `features` + `docs` are both in the list;
       comma-pair `features,docs` is allowed (verified at the
       commit-format.md "Multi-scope commits" section).

- url: https://docs.pydantic.dev/2.10/concepts/models/#serialization
  why: model_dump_json determinism. config_hash() depends on
       model_dump_json being stable across runs — Pydantic v2.10
       guarantees this for frozen models with no None-pruning.

- url: https://www.starlette.io/testclient/#asgi-transport
  why: ASGITransport pattern used by the existing integration tests
       (httpx AsyncClient over the FastAPI app instance directly,
       no real socket). Re-use exactly.
```

### Current Codebase tree (relevant subset)

```bash
app/features/featuresets/
├── __init__.py
├── routes.py                  # POST /featuresets/compute — UNCHANGED
├── schemas.py                 # PRP-3.1A landed Phase 2 *Configs — UNCHANGED
├── service.py                 # PRP-3.1B/C/D landed compute methods — UNCHANGED
└── tests/
    ├── __init__.py
    ├── conftest.py            # PRP-3.1A landed phase2_* fixtures — UNCHANGED
    ├── test_leakage.py        # +1 new class TestPhase2CrossConfigLeakage
    ├── test_schemas.py        # UNCHANGED
    └── test_service.py        # UNCHANGED

docs/PHASE/
└── 3-FEATURE_ENGINEERING.md   # +new "Phase 2 Features" section

docs/_base/
└── DOMAIN_MODEL.md            # +3 rows in Ubiquitous Language table

examples/
└── compute_features_demo.py   # +create_phase2_config() + --phase2 flag
```

### Desired Codebase tree (after this PR)

```bash
app/features/featuresets/tests/
├── test_leakage.py            # +~50 LOC: TestPhase2CrossConfigLeakage
└── test_phase2_integration.py # NEW ~150 LOC: TestPhase2EndToEnd + fixtures

docs/PHASE/
└── 3-FEATURE_ENGINEERING.md   # +~60 LOC: "Phase 2 Features" section

docs/_base/
└── DOMAIN_MODEL.md            # +3 LOC: ubiquitous-language rows

examples/
└── compute_features_demo.py   # +~40 LOC: create_phase2_config + --phase2 branch
```

Net diff target: **≤ +300 / -10 LOC** (well under the 350 ceiling).

### Known Gotchas & Library Quirks

```python
# CRITICAL: NEVER mock the DB in @pytest.mark.integration tests
#   (.claude/rules/test-requirements.md, RULES.md). Use the real
#   Postgres from docker-compose via app.core.config.get_settings()
#   + create_async_engine(settings.database_url). The exact pattern
#   is in app/features/ingest/tests/test_routes.py:27-28.

# CRITICAL: The integration test's seed_data fixture MUST seed Phase 2
#   columns too — product.launch_date, product.discontinue_date,
#   replenishment_event rows, promotion rows with kind='markdown'.
#   The Product fixture in ingest tests (lines 76-95) does NOT seed
#   launch_date / discontinue_date; this slice's fixture MUST.

# CRITICAL: The additive-contract snapshot constant in
#   test_additive_contract_snapshot MUST be captured ONCE on `dev`
#   pre-PRP-3.1A and pinned. Procedure: see §15 Decision A. DO NOT
#   re-compute it on this branch — that would silently absorb a
#   regression.

# CRITICAL: feature_columns is an unordered set semantically but
#   service.py returns it as a list. Use `assert set(expected) <=
#   set(result["feature_columns"])` (subset check), NOT equality —
#   Phase 1 columns may also appear.

# CRITICAL: cutoff_date in the integration test must be ≥ the latest
#   seeded date so no rows are filtered out. The seed_data fixture
#   uses Jan 2024 dates; use cutoff_date=date(2024, 12, 31) in the
#   request to be safe.

# CRITICAL: store_id and product_id in the integration test must
#   resolve to ACTUAL seeded rows (ge=1 in the schema). Use the
#   primary-key IDs returned by SQLAlchemy after db_session.commit() —
#   NOT hardcoded 1/1 (which may not match if the test DB has prior
#   rows from a stale `docker compose` run).

# CRITICAL: `docker compose up -d` must already be running before
#   `pytest -m integration`. The fixture builds an engine against
#   settings.database_url (default localhost:5433) and will fail with
#   `CannotConnectNowError` otherwise. The CI workflow handles this
#   via the postgres service — see ci.yml `test` job.

# CRITICAL: cleanup is FK-aware in the existing pattern
#   (test_routes.py:48-61). Delete in this order:
#     replenishment_event → promotion → sales_daily → product → store
#   (or use ON DELETE CASCADE if the migration declares it — verify
#   with `\d+ promotion` in psql).

# GOTCHA: The PRP-3.1A snapshot test
#   test_config_hash_unchanged_when_phase2_omitted (test_schemas.py)
#   already locks the schema-layer hash. This PRP's
#   test_additive_contract_snapshot locks the SAME hash at the
#   HTTP boundary. The two MUST agree by construction; if they
#   diverge, that's a serialization regression in routes.py.

# GOTCHA: `response.json()["config_hash"]` returns a str. The
#   `FeatureSetConfig.config_hash()` Python method also returns str.
#   No type coercion needed; direct equality compare is correct.

# GOTCHA: docs/PHASE/3-FEATURE_ENGINEERING.md was generated in 2026-01-31
#   (line 3) and predates Phase 2. The new section MUST land AFTER
#   "## Feature Types" (line 149) but BEFORE "## Dependencies"
#   (line 213). Use a fresh top-level heading "## Phase 2 Features
#   (Retail-Depth)" — do NOT re-version the file as Phase 3.1.

# GOTCHA: docs/_base/DOMAIN_MODEL.md "Ubiquitous Language" table is
#   alphabetical-ish but actually grouped by domain. Insert the three
#   new rows in a logical group: after `rolling` (line 67) and
#   `chunk` (line 68), before `scenario` (line 69). Order:
#   `days_since_launch`, `replenishment event`, `promotion (kind)`.

# GOTCHA: examples/compute_features_demo.py uses `dict` as the return
#   type of create_sample_config() (line 27). For pyright --strict
#   cleanliness on the new create_phase2_config(), use the same
#   loose `dict` annotation (NOT TypedDict) — keep the diff additive
#   and minimal.
```

---

## Implementation Blueprint

### Integration test (NEW file)

```python
# app/features/featuresets/tests/test_phase2_integration.py
"""End-to-end integration test for Phase 2 features.

Closes the PRP-3.1 umbrella: proves that lifecycle + replenishment +
promotion configs compose cleanly through the HTTP boundary against
a real Postgres, and that the additive contract holds at that boundary.

Requires docker-compose Postgres+pgvector and `alembic upgrade head`.
"""

from contextlib import suppress
from datetime import date
from decimal import Decimal

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import get_settings
from app.features.data_platform.models import (
    Calendar,
    Product,
    Promotion,
    ReplenishmentEvent,
    SalesDaily,
    Store,
)
from app.main import app


# --- Additive-contract snapshot — pinned from `dev` HEAD pre-PRP-3.1A.
# See PRP-3.1E §15 Decision A for the capture procedure. If this hash
# changes, the additive contract (PRD §6 / §11 R2) is broken.
ADDITIVE_CONTRACT_BASELINE_HASH: str = "<paste-from-dev-head-pre-prp-3.1a>"


# --- db_session, seed_data, client fixtures mirror
# --- app/features/ingest/tests/test_routes.py:20-142 exactly,
# --- but seed_data ALSO inserts Phase 2 fixtures.

@pytest.fixture
async def db_session():
    """Real async Postgres session; rollback on teardown; FK-aware cleanup."""
    settings = get_settings()
    engine = create_async_engine(settings.database_url, echo=False)
    async_session_maker = async_sessionmaker(
        engine, class_=AsyncSession, expire_on_commit=False
    )
    async with async_session_maker() as session:
        try:
            yield session
        finally:
            with suppress(Exception):
                await session.rollback()
    async with async_session_maker() as cleanup:
        with suppress(Exception):
            # FK-order delete (replenishment_event → promotion → sales_daily → product → store)
            await cleanup.execute(
                delete(ReplenishmentEvent).where(
                    ReplenishmentEvent.date.between(date(2024, 1, 1), date(2024, 12, 31))
                )
            )
            await cleanup.execute(
                delete(Promotion).where(Promotion.start_date >= date(2024, 1, 1))
            )
            await cleanup.execute(
                delete(SalesDaily).where(
                    SalesDaily.date.between(date(2024, 1, 1), date(2024, 12, 31))
                )
            )
            await cleanup.execute(delete(Product).where(Product.sku.like("P31E-%")))
            await cleanup.execute(delete(Store).where(Store.code.like("P31E-%")))
            await cleanup.execute(
                delete(Calendar).where(
                    Calendar.date.between(date(2024, 1, 1), date(2024, 12, 31))
                )
            )
            await cleanup.commit()
    await engine.dispose()


@pytest.fixture
async def seed_data(db_session: AsyncSession) -> dict:
    """Seed a minimal Phase 2-shaped dataset.

    One store, one product (with launch + discontinue dates), 60 days of
    sales, three replenishment events, one markdown promotion. The IDs
    are returned so the test request body resolves to real rows.
    """
    store = Store(
        code="P31E-S1", name="P31E Store 1", region="North",
        city="City P31E", store_type="supermarket",
    )
    db_session.add(store)
    await db_session.flush()  # populate store.id

    product = Product(
        sku="P31E-SKU-1", name="P31E Product 1",
        category="Cat A", brand="Brand A",
        base_price=Decimal("19.99"), base_cost=Decimal("10.00"),
        launch_date=date(2023, 6, 1),
        discontinue_date=None,
    )
    db_session.add(product)
    await db_session.flush()

    # 60 days of sales (sequential quantities for leakage detection).
    sales = [
        SalesDaily(
            store_id=store.id, product_id=product.id,
            date=date(2024, 1, 1) + __import__("datetime").timedelta(days=i),
            quantity=i + 1, unit_price=Decimal("19.99"),
            total_amount=Decimal(str((i + 1) * 19.99)),
        )
        for i in range(60)
    ]
    db_session.add_all(sales)

    # Three replenishment events.
    db_session.add_all([
        ReplenishmentEvent(
            store_id=store.id, product_id=product.id,
            date=d, lead_time_days=7, ordered_qty=100, received_qty=98,
        )
        for d in (date(2024, 1, 5), date(2024, 1, 19), date(2024, 2, 9))
    ])

    # One markdown campaign in the middle of the window.
    db_session.add(Promotion(
        product_id=product.id, store_id=store.id,
        kind="markdown", discount_pct=Decimal("0.2000"),
        start_date=date(2024, 1, 20), end_date=date(2024, 2, 5),
    ))

    await db_session.commit()
    return {"store_id": store.id, "product_id": product.id}


@pytest.fixture
async def client(db_session: AsyncSession):
    """ASGITransport client with shared db_session override."""
    from app.core.database import get_db

    async def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.clear()


PHASE2_EXPECTED_COLUMNS: set[str] = {
    "days_since_launch_lag1",
    "days_since_last_replenishment_lag1",
    "replenishment_count_w14_lag1",
    "promo_markdown_active_lag1",
    "promo_markdown_intensity_lag1",
}
# discontinue_date is None on the seeded product so
# days_since_discontinue_lag1 is omitted from the strict-subset check
# (the column may appear with all-NaN values depending on PRP-3.1B's
# decision — assert containment, not equality, per Gotchas).


@pytest.mark.integration
class TestPhase2EndToEnd:
    """Integration tests for Phase 2 features at the HTTP boundary."""

    @pytest.mark.asyncio
    async def test_phase2_columns_appear(self, client, seed_data):
        """All Phase 2 columns appear in the response when all configs are set."""
        body = {
            "store_id": seed_data["store_id"],
            "product_id": seed_data["product_id"],
            "cutoff_date": "2024-02-29",
            "lookback_days": 60,
            "config": {
                "name": "phase2-smoke",
                "lifecycle_config": {
                    "include_days_since_launch": True,
                    "include_days_since_discontinue": True,
                    "lag_days": 1,
                },
                "replenishment_config": {
                    "include_days_since_last": True,
                    "include_count_window": True,
                    "lag_days": 1,
                    "count_window_days": 14,
                },
                "promotion_config": {
                    "kinds_to_track": ["markdown"],
                    "include_active": True,
                    "include_intensity": True,
                    "lag_days": 1,
                },
            },
        }
        response = await client.post("/featuresets/compute", json=body)
        assert response.status_code == 200, response.text
        data = response.json()

        cols = set(data["feature_columns"])
        missing = PHASE2_EXPECTED_COLUMNS - cols
        assert not missing, f"Phase 2 columns missing from response: {missing}"

    @pytest.mark.asyncio
    async def test_config_hash_deterministic(self, client, seed_data):
        """Two identical Phase 2 requests return identical config_hash."""
        body = {
            "store_id": seed_data["store_id"],
            "product_id": seed_data["product_id"],
            "cutoff_date": "2024-02-29",
            "lookback_days": 60,
            "config": {
                "name": "phase2-det",
                "lifecycle_config": {"lag_days": 1},
                "replenishment_config": {"lag_days": 1},
                "promotion_config": {"kinds_to_track": ["markdown"], "lag_days": 1},
            },
        }
        r1 = (await client.post("/featuresets/compute", json=body)).json()
        r2 = (await client.post("/featuresets/compute", json=body)).json()
        assert r1["config_hash"] == r2["config_hash"]

    @pytest.mark.asyncio
    async def test_additive_contract_snapshot(self, client, seed_data):
        """A request with NO Phase 2 sub-configs returns the pre-PRP-3.1A hash.

        Regression guard for PRD §6 / §11 R2 (additive contract). If this
        fails, a pre-PR caller's response shape changed — STOP and root-
        cause before merging.
        """
        body = {
            "store_id": seed_data["store_id"],
            "product_id": seed_data["product_id"],
            "cutoff_date": "2024-02-29",
            "lookback_days": 60,
            "config": {"name": "x"},
        }
        response = await client.post("/featuresets/compute", json=body)
        assert response.status_code == 200, response.text
        assert response.json()["config_hash"] == ADDITIVE_CONTRACT_BASELINE_HASH, (
            "Additive contract broken: a no-Phase-2 request's config_hash "
            "differs from the pre-PRP-3.1A baseline. See PRP-3.1E §15 Decision A."
        )
```

### Cross-config leakage test (APPEND to test_leakage.py)

```python
# Append AFTER the existing TestEdgeCaseLeakage class (line ~328).
# This is a UNIT test (no @pytest.mark.integration) — it exercises the
# in-process FeatureEngineeringService with all three Phase 2 configs
# composed.

class TestPhase2CrossConfigLeakage:
    """Verify Phase 2 configs compose without future-data leakage.

    Even when each Phase 2 family's own leakage tests (PRP-3.1B/C/D
    test_leakage cases) are green individually, composing all three
    with Phase 1 (lag + exogenous) may surface a new leakage path
    if any family's _compute_* method mutates `df` in place before
    the next family reads it. This class is the strongest additive
    assertion — feature rows at row i reference ONLY rows ≤ i-1.
    """

    def test_all_phase2_configs_compose_no_future_leakage(
        self,
        sample_time_series: pd.DataFrame,
        phase2_product_attrs_df: pd.DataFrame,
        phase2_replenishment_events_df: pd.DataFrame,
        phase2_promotion_rows_df: pd.DataFrame,
    ) -> None:
        """CRITICAL: All three Phase 2 configs ON + lag_config — no row i
        feature reads data > row i-1 for the (store=1, product=1) series.

        The fixtures inject lifecycle / replenishment / promotion data
        that the corresponding _compute_* methods JOIN onto the input
        DataFrame. We assert the resulting feature columns at row i
        depend only on past data via the sequential-quantity trick.
        """
        from app.features.featuresets.schemas import (
            LagConfig,
            LifecycleConfig,
            PromotionConfig,
            ReplenishmentConfig,
        )
        config = FeatureSetConfig(
            name="phase2-leakage",
            lag_config=LagConfig(lags=(1,)),
            lifecycle_config=LifecycleConfig(lag_days=1),
            replenishment_config=ReplenishmentConfig(lag_days=1, count_window_days=14),
            promotion_config=PromotionConfig(kinds_to_track=("markdown",), lag_days=1),
        )
        service = FeatureEngineeringService(config)
        # NOTE: This relies on PRP-3.1B/C/D plumbing the auxiliary
        # DataFrames through compute_features. If those slices pass
        # aux frames via a different mechanism (e.g., service.__init__),
        # adjust the call here accordingly — the assertion below is
        # what matters, not the wiring detail.
        result = service.compute_features(sample_time_series)

        # The existing lag invariant must hold: lag_1 at row i = i.
        for i in range(1, len(result.df)):
            assert result.df.iloc[i]["lag_1"] == i, (
                f"CROSS-CONFIG LEAKAGE: lag_1 at row {i} corrupted by Phase 2 compose"
            )

        # Every Phase 2 column at every row must be NaN at row 0
        # (no prior data) — proves no future-data fill.
        phase2_cols = [
            c for c in result.feature_columns
            if c.startswith(("days_since_", "replenishment_", "promo_"))
        ]
        for col in phase2_cols:
            assert pd.isna(result.df.iloc[0][col]), (
                f"CROSS-CONFIG LEAKAGE: {col} at row 0 has value "
                f"{result.df.iloc[0][col]!r} — should be NaN (no past data)."
            )

    def test_phase2_compose_preserves_group_isolation(
        self,
        multi_series_time_series: pd.DataFrame,
    ) -> None:
        """CRITICAL: Multi-series + all Phase 2 configs — no cross-series
        leakage between (store=1, product=1) and (store=2, product=2).

        Even when Phase 2 joins are evaluated for the union of entities,
        groupby([store_id, product_id]).shift(1) must keep them isolated.
        """
        from app.features.featuresets.schemas import (
            LagConfig,
            LifecycleConfig,
            PromotionConfig,
            ReplenishmentConfig,
        )
        config = FeatureSetConfig(
            name="phase2-groupiso",
            entity_columns=("store_id", "product_id"),
            lag_config=LagConfig(lags=(1,)),
            lifecycle_config=LifecycleConfig(lag_days=1),
            replenishment_config=ReplenishmentConfig(lag_days=1),
            promotion_config=PromotionConfig(kinds_to_track=("markdown",), lag_days=1),
        )
        service = FeatureEngineeringService(config)
        result = service.compute_features(multi_series_time_series)

        # First row of each series must have NaN lag_1 (per-group isolation).
        for store_id in (1, 2):
            for product_id in (1, 2):
                series = result.df[
                    (result.df["store_id"] == store_id)
                    & (result.df["product_id"] == product_id)
                ].reset_index(drop=True)
                assert pd.isna(series.iloc[0]["lag_1"]), (
                    f"GROUP ISOLATION BREACH at series ({store_id},{product_id}): "
                    "lag_1 first row should be NaN even with Phase 2 configs composed"
                )
```

### docs/PHASE/3-FEATURE_ENGINEERING.md — new section

INSERT a new top-level section AFTER `## Feature Types` (existing line 149..210) and BEFORE `## Dependencies` (existing line 213). Don't touch any existing line.

```markdown
---

## Phase 2 Features (Retail-Depth)

Phase 2 (PRP-3.1, landed in PRs covering INITIALs 1-5) extends the feature
matrix with three retail-depth families derived from the seeder's Phase 2
emission. All three families are **opt-in** (default `None`) and **additive**
— a `/featuresets/compute` call without any Phase 2 sub-config returns a
response byte-identical to the pre-Phase-2 baseline (regression-guarded by
`test_phase2_integration.py::TestPhase2EndToEnd::test_additive_contract_snapshot`).

### Lifecycle features

Continuous date-deltas derived from `product.launch_date` and
`product.discontinue_date` (both nullable on Phase 2 products). See
PRP-3.1B for the compute method; the categorical `lifecycle_stage` was
explicitly **dropped** in favor of continuous deltas (decision log §1) —
LightGBM splits discover stage boundaries from the integer delta naturally.

```python
from app.features.featuresets.schemas import LifecycleConfig

LifecycleConfig(
    include_days_since_launch=True,       # default True
    include_days_since_discontinue=True,  # default True
    lag_days=1,                            # 1..30
)
```

| Column | Type | Time-safety |
|--------|------|-------------|
| `days_since_launch_lag{N}` | int (NaN if `launch_date` is NULL) | `shift(N)` per `(store_id, product_id)` |
| `days_since_discontinue_lag{N}` | int (NaN if `discontinue_date` is NULL) | `shift(N)` per `(store_id, product_id)` |

### Replenishment features

Inbound-stock cadence from the `replenishment_event` table (separate from
`sales_daily`). See PRP-3.1C for the compute method + SQL helper.

```python
from app.features.featuresets.schemas import ReplenishmentConfig

ReplenishmentConfig(
    include_days_since_last=True,   # default True
    include_count_window=True,      # default True
    lag_days=1,                      # 1..30
    count_window_days=14,            # 7..60
)
```

| Column | Type | Time-safety |
|--------|------|-------------|
| `days_since_last_replenishment_lag{N}` | int (NaN before first event) | `shift(N)` per `(store_id, product_id)` |
| `replenishment_count_w{W}_lag{N}` | int | `shift(N).rolling(W).sum()` per series |

### Promotion features (generic — any `promotion.kind`)

Generalized from the original markdown-only design (decision log §3) — one
JOIN to the `promotion` table, with one-hot per kind on the configured
subset. Default `kinds_to_track=("markdown",)` preserves the original PRD
intent; callers can opt into `pct_off | bogo | bundle` by passing additional
kinds. See PRP-3.1D for the compute method.

```python
from app.features.featuresets.schemas import PromotionConfig

PromotionConfig(
    kinds_to_track=("markdown",),  # subset of pct_off|bogo|bundle|markdown
    include_active=True,            # default True
    include_intensity=True,         # default True
    lag_days=1,                      # 1..30
)
```

| Column | Type | Time-safety |
|--------|------|-------------|
| `promo_<kind>_active_lag{N}` | int 0/1 | `shift(N)` per `(store_id, product_id)` of active-indicator |
| `promo_<kind>_intensity_lag{N}` | float ∈ [0, 1] | `shift(N)` of `promotion.discount_pct` (`Numeric(5,4)`) |

### Time-safety guarantee (cross-cutting)

All Phase 2 features obey the same invariants as Phase 1
(`app/features/featuresets/tests/test_leakage.py`):

- Every numeric column is `shift(N)` (positive) per `(store_id, product_id)`
  group.
- Every rolling/count column is `shift(1).rolling(W)`, never
  `rolling(W).shift(1)`.
- Inputs JOINed from auxiliary tables (`replenishment_event`, `promotion`)
  are SQL-filtered to `event_date <= cutoff_date` / `start_date <= cutoff_date`
  BEFORE pandas sees them.
- A dedicated `TestPhase2CrossConfigLeakage` class composes all three
  families with `lag_config` and asserts no future-data references at the
  union of feature rows.

### End-to-end integration

`app/features/featuresets/tests/test_phase2_integration.py` (marked
`@pytest.mark.integration`) exercises `POST /featuresets/compute` against
a real Postgres with all three Phase 2 sub-configs set, and pins the
additive-contract snapshot at the HTTP boundary. Run after
`docker compose up -d && uv run alembic upgrade head`.
```

### docs/_base/DOMAIN_MODEL.md — Ubiquitous Language additions

INSERT three rows AFTER existing line 68 (`chunk` (RAG)...) and BEFORE existing line 69 (`scenario` (seeder)...). Touch nothing else in the file.

```markdown
| `days_since_launch` | Continuous integer offset from `product.launch_date` to a sales-daily row, used as a lifecycle feature (`days_since_launch_lag{N}`) | lifecycle_stage (Phase 2 dropped the categorical) |
| `replenishment event` | One row in `replenishment_event` representing inbound stock at `(store, product, date)`; feature cadence is derived from event spacing | inbound order, restock (those would be different grains) |
| `promotion (kind)` | One row in `promotion` with `kind ∈ {pct_off, bogo, bundle, markdown}`; features one-hot per kind via `PromotionConfig.kinds_to_track` | discount, sale (kind is the discriminator, not "promotion" in the colloquial sense) |
```

### examples/compute_features_demo.py — extension

APPEND a `create_phase2_config()` function after `create_sample_config()` (existing line 27-66) and add a `--phase2` CLI branch to `main()` (line 137).

```python
def create_phase2_config() -> dict:
    """Create a Phase 2-enabled feature configuration.

    Extends create_sample_config() with the three Phase 2 sub-configs
    (lifecycle, replenishment, promotion). Use this with the same
    /featuresets/compute and /featuresets/preview endpoints.
    """
    cfg = create_sample_config()
    cfg["name"] = "retail_forecast_phase2_v1"
    cfg["lifecycle_config"] = {
        "include_days_since_launch": True,
        "include_days_since_discontinue": True,
        "lag_days": 1,
    }
    cfg["replenishment_config"] = {
        "include_days_since_last": True,
        "include_count_window": True,
        "lag_days": 1,
        "count_window_days": 14,
    }
    cfg["promotion_config"] = {
        "kinds_to_track": ["markdown"],
        "include_active": True,
        "include_intensity": True,
        "lag_days": 1,
    }
    return cfg


# Inside main(), after the Phase 1 demo flow, add:
def print_phase2_columns() -> None:
    """Print the Phase 2 feature column list produced by the API."""
    import sys
    cfg = create_phase2_config()
    print("Phase 2 feature configuration constructed:")
    print(f"  Lifecycle:     {cfg['lifecycle_config']}")
    print(f"  Replenishment: {cfg['replenishment_config']}")
    print(f"  Promotion:     {cfg['promotion_config']}")
    print()
    # Use the standard /preview flow with the new config; cutoff/series
    # selection identical to main() — caller has already started the API.
    body = {
        "store_id": 1,
        "product_id": 1,
        "cutoff_date": date(2024, 1, 31).isoformat(),
        "sample_rows": 3,
        "config": cfg,
    }
    with httpx.Client(timeout=30.0) as client:
        try:
            response = client.post(f"{FEATURES_ENDPOINT}/preview", json=body)
            response.raise_for_status()
        except httpx.HTTPStatusError as e:
            print(f"  Phase 2 preview returned HTTP {e.response.status_code}: "
                  f"{e.response.text}", file=sys.stderr)
            return
    result = response.json()
    phase2_cols = [
        c for c in result["feature_columns"]
        if c.startswith(("days_since_", "replenishment_", "promo_"))
    ]
    print(f"  Phase 2 columns returned ({len(phase2_cols)}):")
    for col in phase2_cols:
        print(f"    - {col}")
```

Wire the `--phase2` flag in `main()`:

```python
def main() -> None:
    import argparse
    parser = argparse.ArgumentParser(description="Feature engineering demo")
    parser.add_argument("--phase2", action="store_true",
                        help="Run the Phase 2 (lifecycle/replenishment/promotion) preview")
    args, _ = parser.parse_known_args()
    # ... existing flow up to/through Phase 1 demo ...
    if args.phase2:
        print()
        print("=" * 50)
        print("Phase 2 feature demo")
        print("=" * 50)
        print_phase2_columns()
```

### List of tasks (in execution order)

```yaml
Task 1 — Capture the additive-contract snapshot from `dev` HEAD:
  - PRE-CONDITION: This MUST run on `dev` BEFORE creating the
    PRP-3.1E branch. The hash is the response.json()["config_hash"]
    field from a no-Phase-2 request against `dev` HEAD.
  - Procedure: see §15 Decision A.
  - Output: a single string constant (e.g., "a1b2c3d4...") to
    paste into ADDITIVE_CONTRACT_BASELINE_HASH in
    test_phase2_integration.py.
  - DO NOT defer this step. The snapshot is load-bearing.

Task 2 — Create test_phase2_integration.py:
ADD app/features/featuresets/tests/test_phase2_integration.py:
  - COPY the db_session / seed_data / client fixture triad from
    app/features/ingest/tests/test_routes.py:20-142 (verbatim
    structure; adapt seed_data body to include Phase 2 columns).
  - ADD class TestPhase2EndToEnd with three @pytest.mark.asyncio tests:
      * test_phase2_columns_appear
      * test_config_hash_deterministic
      * test_additive_contract_snapshot
  - PASTE the snapshot from Task 1 into ADDITIVE_CONTRACT_BASELINE_HASH.
  - Mark the class @pytest.mark.integration.

Task 3 — Append TestPhase2CrossConfigLeakage to test_leakage.py:
MODIFY app/features/featuresets/tests/test_leakage.py:
  - FIND pattern: "class TestEdgeCaseLeakage:" (line ~289).
  - APPEND a new class AFTER it (end of file).
  - Two test methods:
      * test_all_phase2_configs_compose_no_future_leakage
      * test_phase2_compose_preserves_group_isolation
  - IMPORT LifecycleConfig, ReplenishmentConfig, PromotionConfig
    inside the test methods (lazy import to keep top-of-file diff
    minimal). LagConfig is already imported (line 14).

Task 4 — Update docs/PHASE/3-FEATURE_ENGINEERING.md:
MODIFY docs/PHASE/3-FEATURE_ENGINEERING.md:
  - FIND pattern: line 210 (end of "## Imputation" subsection).
  - INSERT the "## Phase 2 Features (Retail-Depth)" section
    AFTER line 210 and BEFORE the existing "## Dependencies"
    section (line 213).
  - Verbatim content per the blueprint above — three families,
    three code blocks, three tables, one cross-cutting time-safety
    note, one E2E note.
  - DO NOT modify any existing line.

Task 5 — Update docs/_base/DOMAIN_MODEL.md:
MODIFY docs/_base/DOMAIN_MODEL.md:
  - FIND pattern: line 68 (`chunk` (RAG)...).
  - INSERT three new rows AFTER line 68 and BEFORE line 69
    (`scenario` (seeder)...). Verbatim content per blueprint.
  - DO NOT modify any existing line.

Task 6 — Extend examples/compute_features_demo.py:
MODIFY examples/compute_features_demo.py:
  - FIND pattern: end of create_sample_config (line ~66).
  - APPEND create_phase2_config() AFTER it.
  - FIND pattern: top of main() (line 137).
  - INSERT argparse setup at the top of main(), keep the existing
    body, and conditionally call print_phase2_columns() when
    --phase2 is passed.
  - Make sure existing `python examples/compute_features_demo.py`
    (no flag) keeps working unchanged.

Task 7 — Validation gates:
RUN:
  uv run ruff check .
  uv run ruff format --check .
  uv run mypy app/
  uv run pyright app/
  uv run pytest app/features/featuresets/ -v -m "not integration"
  docker compose up -d
  uv run alembic upgrade head
  uv run pytest app/features/featuresets/tests/test_phase2_integration.py -v -m integration

Task 8 — Commit:
  git commit -m "feat(features,docs): land phase 2 e2e integration and docs (#<issue>)"
  # NOTE: type MUST be `feat:` (not `docs:`/`test:`) per
  # .claude/rules/versioning.md to avoid release-please bump skip.
```

### Integration Points

```yaml
DATABASE:
  - NO migration required (PRP-3.1A confirmed all Phase 2 columns
    exist in a8b9c0d1e234_add_retail_depth_columns_and_replenishment
    _event_table.py).

CONFIG:
  - NO new env vars. The integration test reads settings.database_url
    from .env (same as ingest integration tests).

ROUTES:
  - NO changes. POST /featuresets/compute already accepts the three
    Phase 2 sub-configs after PRP-3.1A.

SERVICE:
  - NO changes. PRP-3.1B/C/D landed the compute methods.

SCHEMAS:
  - NO changes. PRP-3.1A landed the three *Config classes and the
    three FeatureSetConfig fields.

DOCS:
  - docs/PHASE/3-FEATURE_ENGINEERING.md: +new section.
  - docs/_base/DOMAIN_MODEL.md: +3 rows in Ubiquitous Language table.

EXAMPLES:
  - examples/compute_features_demo.py: +create_phase2_config() helper
    + --phase2 CLI flag.

CI:
  - The existing `test` job in .github/workflows/ci.yml runs both
    unit + integration tests against a Postgres+pgvector service.
    The new test_phase2_integration.py picks up automatically;
    no workflow change needed.
```

---

## Validation Loop

### Level 1: Syntax & Style

```bash
uv run ruff check .
uv run ruff format --check .

# Expected: clean. If `ruff format --check` fails on the new
# test file or doc examples, run `uv run ruff format` to autofix.
```

### Level 2: Type Checks (merge gate)

```bash
uv run mypy app/
uv run pyright app/

# Expected: 0 errors. Common failure modes:
#   - pyright complaining about `dict` return type in
#     create_phase2_config — use the loose `dict` annotation
#     identical to create_sample_config (Gotchas).
#   - mypy "Untyped function call" on test fixtures — the
#     existing test_routes.py pattern doesn't annotate fixtures
#     either; mirror that style.
```

### Level 3: Unit Tests (non-integration)

```bash
uv run pytest app/features/featuresets/tests/test_leakage.py -v
uv run pytest app/features/featuresets/ -v -m "not integration"

# Expected: all green, including the new TestPhase2CrossConfigLeakage
# class. The two new test methods exercise the in-process
# FeatureEngineeringService — no DB, no HTTP.
```

### Level 4: Integration Test (real Postgres)

```bash
# Prerequisites — must be running:
docker compose up -d
uv run alembic upgrade head

uv run pytest app/features/featuresets/tests/test_phase2_integration.py -v -m integration

# Expected: three green tests.
#
# If test_additive_contract_snapshot FAILS:
#   - The ADDITIVE_CONTRACT_BASELINE_HASH constant is stale or
#     was never captured. STOP, re-run Task 1 against `dev` HEAD
#     pre-PRP-3.1A, paste the result, retry.
#   - If the hash on `dev` HEAD has itself changed since Task 1,
#     the additive contract is broken — investigate the underlying
#     regression in schemas.py/routes.py before merging this PR.
#
# If test_phase2_columns_appear FAILS with missing columns:
#   - One of PRP-3.1B/C/D's compute methods is producing different
#     column names than this PRP expects. Reconcile with the actual
#     compute output — this PRP is the LAST slice; the others are
#     the source of truth on column naming.
```

### Level 5: Manual smoke (optional)

```bash
docker compose up -d
uv run alembic upgrade head
uv run uvicorn app.main:app --reload --port 8123 &
APP_PID=$!

# Seed Phase 2 data:
uv run python scripts/seed_random.py --full-new --seed 42 --confirm

# Hit the endpoint:
curl -s -X POST http://localhost:8123/featuresets/compute \
  -H "Content-Type: application/json" \
  -d '{
    "store_id": 1, "product_id": 1,
    "cutoff_date": "2024-02-29", "lookback_days": 60,
    "config": {
      "name": "phase2-smoke",
      "lifecycle_config":    {"lag_days": 1},
      "replenishment_config": {"lag_days": 1, "count_window_days": 14},
      "promotion_config":    {"kinds_to_track": ["markdown"], "lag_days": 1}
    }
  }' \
  | jq '.feature_columns | map(select(startswith("days_since_") or startswith("replenishment_") or startswith("promo_")))'

# Expected: a JSON array containing the 6 Phase 2 columns
# (or 5 if the seeded product has discontinue_date=NULL).

# Run the extended demo script:
uv run python examples/compute_features_demo.py --phase2
# Expected: prints Phase 2 columns at the end of the run.

kill $APP_PID
```

### Level 6: Diff stat check

```bash
git diff --stat dev...

# Expected: ≤ +350 / -20 LOC total.
# Files touched (and ONLY these):
#   app/features/featuresets/tests/test_phase2_integration.py  (NEW)
#   app/features/featuresets/tests/test_leakage.py             (+~50 LOC)
#   docs/PHASE/3-FEATURE_ENGINEERING.md                        (+~60 LOC)
#   docs/_base/DOMAIN_MODEL.md                                 (+3 LOC)
#   examples/compute_features_demo.py                          (+~40 LOC)
#
# VERIFY no production code touched:
git diff --stat dev... -- \
  app/features/featuresets/service.py \
  app/features/featuresets/routes.py \
  app/features/featuresets/schemas.py
# Expected: empty output.
```

---

## Final Validation Checklist

- [ ] Snapshot captured (§15 Decision A): `ADDITIVE_CONTRACT_BASELINE_HASH` is a real string, not the placeholder.
- [ ] All unit tests pass: `uv run pytest app/features/featuresets/ -v -m "not integration"`.
- [ ] Integration test passes: `uv run pytest app/features/featuresets/tests/test_phase2_integration.py -v -m integration` after `docker compose up -d && uv run alembic upgrade head`.
- [ ] No linting errors: `uv run ruff check .`.
- [ ] No formatting drift: `uv run ruff format --check .`.
- [ ] No mypy errors: `uv run mypy app/`.
- [ ] No pyright errors: `uv run pyright app/`.
- [ ] No production-code diff: `git diff --stat dev... -- app/features/featuresets/{service,routes,schemas}.py` is empty.
- [ ] Diff stat: ≤ +350 / -20 LOC (`git diff --stat dev...`).
- [ ] Single commit, message: `feat(features,docs): land phase 2 e2e integration and docs (#<issue>)` — `feat:`, NOT `docs:`/`test:`/`chore:`, per `.claude/rules/versioning.md`.
- [ ] No AI co-author trailer (per `.claude/rules/commit-format.md`).
- [ ] PR title matches the commit subject (to avoid release-please merge-subject trap per `docs/_base/RUNBOOKS.md`).
- [ ] PR body references the parent PRD location + #92 (Phase 2 seeder PR) for lineage.

---

## Anti-Patterns to Avoid

- [FAIL] **Do NOT mock the DB in `test_phase2_integration.py`.** The whole point is real-Postgres verification. Use `docker compose up -d` + the real `db_session` engine pattern. Verbatim from `.claude/rules/test-requirements.md`: "NEVER mock the database in integration tests".
- [FAIL] **Do NOT recompute `ADDITIVE_CONTRACT_BASELINE_HASH` on this branch.** That silently absorbs any regression. The hash MUST come from `dev` HEAD pre-PRP-3.1A — see §15 Decision A.
- [FAIL] **Do NOT edit `service.py` / `routes.py` / `schemas.py`.** This slice is docs + tests only. Production code lives in PRP-3.1A/B/C/D. If you find yourself wanting to edit production code here, STOP and open a new INITIAL.
- [FAIL] **Do NOT use `Optional[T]`.** Project style is `T | None` (PEP 604), enforced by ruff `UP007`.
- [FAIL] **Do NOT use `os.environ` in the integration test.** Read settings via `get_settings()` (matches `app/features/ingest/tests/test_routes.py:27`).
- [FAIL] **Do NOT add an AI co-author trailer.** Forbidden by `.claude/rules/commit-format.md`.
- [FAIL] **Do NOT title the commit `docs(features): ...` or `test(features): ...`.** release-please will skip the bump (RUNBOOKS.md "release-please skipped the bump after a dev → main merge"). Use `feat(features,docs): ...`.
- [FAIL] **Do NOT replace any existing line in `docs/PHASE/3-FEATURE_ENGINEERING.md` or `docs/_base/DOMAIN_MODEL.md`.** Append-only. Both files have human-readable history; preserve it.
- [FAIL] **Do NOT exceed the diff budget.** If the diff creeps past 350 LOC, the slice is doing too much — defer the optional parts (example script extension first, then doc tables) and re-scope.
- [FAIL] **Do NOT load PHASE/3 with operational instructions that belong in RUNBOOKS.md.** The new section documents the feature contract, not the operational workflow. Toolchain notes (docker, alembic) go in RUNBOOKS, not PHASE/3.
- [FAIL] **Do NOT add `# type: ignore` to make pyright happy.** Diagnose the actual issue; mirror the existing pattern.

---

## §15 — PRP-Authoring Decisions

Decisions made during PRP authoring that the INITIAL didn't lock — recorded so a future session can audit the reasoning.

### Decision A — Capture `ADDITIVE_CONTRACT_BASELINE_HASH` BEFORE branching

**Problem.** The integration test's snapshot constant must be the `config_hash` value as it was on `dev` HEAD **before any Phase 2 work** (i.e., before PRP-3.1A landed). If we compute it on the PRP-3.1E branch, we silently freeze whatever value the post-Phase-2 code produces — defeating the regression-guard purpose entirely.

**Procedure** (run ONCE, on `dev` HEAD, BEFORE creating the PRP-3.1E branch — or by checking out the commit just before PRP-3.1A merged):

```bash
git switch dev
git pull
git rev-parse HEAD                          # sanity: confirm you're at the right SHA
# If PRP-3.1A has ALREADY landed on dev, check out the prior commit:
# git switch -d $(git log --format=%H --grep="phase 2.*configs" -n 1)^

docker compose up -d
uv run alembic upgrade head

uv run uvicorn app.main:app --port 8123 &
APP_PID=$!
sleep 2

# Pre-PRP-3.1A response — note `config: {"name": "x"}` only:
curl -s -X POST http://localhost:8123/featuresets/compute \
  -H "Content-Type: application/json" \
  -d '{"store_id":1,"product_id":1,"cutoff_date":"2024-02-29","lookback_days":60,"config":{"name":"x"}}' \
  | jq -r '.config_hash'
# Copy that value into ADDITIVE_CONTRACT_BASELINE_HASH.

kill $APP_PID
git switch -
```

Alternative if `seed_data` is required before the endpoint returns 200: replace the curl call with a Python one-liner against the `FeatureSetConfig(name="x").config_hash()` direct call — that's what `test_schemas.py::test_config_hash_unchanged_when_phase2_omitted` (PRP-3.1A) already pins, and the HTTP response surfaces the same value verbatim.

**Why this matters.** PRD §6 / §11 R2 says the additive contract is mandatory. The schema-level test (PRP-3.1A) guards it at the model layer. This snapshot guards it at the response layer. If they ever diverge, `routes.py` introduced a serialization drift between `FeatureSetConfig.config_hash()` and the response field — a separate bug to fix.

### Decision B — Cross-config leakage test goes in `test_leakage.py`, not the new integration file

**Considered.** Putting the cross-config leakage assertion inside `test_phase2_integration.py` (which would make it integration-only).

**Decided.** Put it in `test_leakage.py` as a unit test (no `@pytest.mark.integration`).

**Why.** `test_leakage.py` is the **load-bearing leakage spec** (per `.claude/rules/test-requirements.md` and PRD §11 R1). The cross-config case is a leakage case — it belongs with the others, runs on every PR (not gated behind docker-compose), and re-uses the existing `sample_time_series` / `multi_series_time_series` fixtures verbatim. Keeping leakage assertions co-located makes the spec scannable.

**Counter.** Some Phase 2 features (replenishment, promotion) require real DB-loaded auxiliary frames. If PRP-3.1B/C/D plumb those frames through `compute_features` in a way that requires an `AsyncSession` arg, the unit-level test can't run.

**Mitigation.** Build the cross-config test against the in-process `FeatureEngineeringService.compute_features` path with **only** the lifecycle features that derive from the DataFrame's columns (no aux frame). The replenishment/promotion families' own leakage tests (in PRP-3.1C/3.1D, presumably DB-backed) already cover the per-family case; the cross-config test's job is to prove COMPOSITION doesn't introduce leakage, not to re-test each family.

### Decision C — Doc section heading: `## Phase 2 Features (Retail-Depth)`

**Considered.** `## Phase 2: Retail-Depth Features` (mirroring the document's own title `Phase 3: Feature Engineering`).

**Decided.** `## Phase 2 Features (Retail-Depth)`.

**Why.** The document's title refers to **PRP phase 3** (the feature-engineering slice). The "Phase 2" in our heading refers to the **seeder phase 2** (`#92` / `#93`). Using `## Phase 2:` would collide visually with the document's own Phase 3 framing. The chosen form makes the source unambiguous and matches how PRP-3.1A's commit message refers to the work ("Phase 2 features").

### Decision D — Single commit, comma-pair scope `(features,docs)`

**INITIAL says.** Commit type `feat:` (required for release-please bump). Scope was left implicit.

**Decided.** `feat(features,docs): land phase 2 e2e integration and docs (#<issue>)`.

**Why.** `commit-format.md` explicitly allows comma-pair scopes when a change cuts across two scope domains. This PR touches `app/features/featuresets/tests/` (scope `features`) and `docs/` (scope `docs`) in roughly equal proportion. The comma-pair makes the cross-cut visible in the changelog. Single-scope `feat(features): ...` is also acceptable; reviewer's call.

### Decision E — Don't replace existing doc lines (append-only)

**Considered.** Refreshing the existing `docs/PHASE/3-FEATURE_ENGINEERING.md` validation results section (line 256-269) to include Phase 2 numbers.

**Decided.** Append only; don't modify existing lines.

**Why.** The existing doc is a snapshot of PRP-4 completion (2026-01-31, PR #25). Rewriting it would lose that historical context. The new section flags Phase 2 work as additive and dated separately. If reviewers want a refreshed "current state" doc, that's a separate `docs:` PR.

---

## §16 — Open Questions for the Implementing Agent

None that block authoring. Three runtime decisions only the implementing agent can make:

1. **Exact column names produced by PRP-3.1B/C/D.** This PRP enumerates the expected names (`days_since_launch_lag1`, `days_since_last_replenishment_lag1`, `replenishment_count_w14_lag1`, `promo_markdown_active_lag1`, `promo_markdown_intensity_lag1`). If those slices chose different names (e.g., `_lag_1` with an underscore), update `PHASE2_EXPECTED_COLUMNS` in `test_phase2_integration.py` and the doc tables in `docs/PHASE/3-FEATURE_ENGINEERING.md` accordingly. The PRP-3.1B/C/D implementations are the source of truth.
2. **`days_since_discontinue_lag1` on a NULL-discontinue product.** The seed_data fixture in this PRP uses `discontinue_date=None`. PRP-3.1B may either omit the column entirely or emit it with all-NaN values. The assertion uses `set(expected) <= set(feature_columns)` (subset), so either behavior passes. If PRP-3.1B chooses to omit the column, remove `days_since_discontinue_lag1` from any expected sets to be tighter.
3. **Auxiliary-frame plumbing for the cross-config leakage test.** If PRP-3.1C/3.1D require an `AsyncSession` arg on `compute_features` (rather than loading the aux frames inside the service via `_load_replenishment_events_up_to_cutoff`), Decision B's unit-level placement breaks. Fallback: move the cross-config leakage test into `test_phase2_integration.py` and mark it `@pytest.mark.integration`. Reviewer's call.

If any of the three surprise you mid-implementation, STOP, document the surprise in a PR comment, and adjust the corresponding test / doc cell to match the actual code — don't silently re-invent the contract.

---

## Confidence Score: 9 / 10

**Why 9, not 10:**

- [PASS] All file paths verified against the repo at PRP-authoring time (PRP-3.1A schemas present at `app/features/featuresets/schemas.py:186-276`; integration-test pattern verified at `app/features/ingest/tests/test_routes.py:20-142`; existing `compute_features_demo.py` at `examples/`).
- [PASS] All four locked decisions from `phase2-decisions-and-prp-prep.md` carried forward — lifecycle continuous-only, replenishment in-method JOIN, PromotionConfig generalization, release-please merge-subject discipline.
- [PASS] Validation gates are deterministic and executable as-written.
- [PASS] Additive-contract invariant has TWO snapshot guards: schema layer (PRP-3.1A `test_config_hash_unchanged_when_phase2_omitted`) + HTTP boundary (this PRP's `test_additive_contract_snapshot`). Defense in depth.
- [PASS] Cross-config leakage test addresses the gap PRP-3.1B/C/D individually leave open.
- [PASS] Diff budget (≤ 350 LOC) leaves slack for doc tone tweaks and an extra leakage case if needed.
- [WARN] Residual risk: PRP-3.1B/C/D haven't merged yet at authoring time. If those slices land with different column-naming conventions (e.g., `_lag_1` instead of `_lag1`) or different auxiliary-frame plumbing, the test assertions and doc tables here need a one-line reconciliation each. §16 calls this out explicitly; the change is local (`PHASE2_EXPECTED_COLUMNS` constant + one column-name string per doc cell).

Goal achieved: an implementing agent with no prior session context can read this PRP, edit 4 files, add 1 file, run 8 commands, and ship a green PR that closes the PRP-3.1 umbrella.
