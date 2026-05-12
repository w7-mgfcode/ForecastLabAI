# PRP-3.1C: Replenishment Compute Method for Time-Safe Featuresets

**Feature**: `.agents/plans/initial-3-replenishment-features.md`
**Parent PRP**: PRP-3.1 (umbrella — Phase 2 feature wiring; PRP-3.1A through PRP-3.1E are the 5 slices)
**Parent PRD**: `.agents/plans/wire-phase2-features-to-featuresets.md`
**Status**: Ready for Implementation (blocked by PRP-3.1A merge)
**Confidence Score**: 9 / 10 — pattern source (`_compute_exogenous_features`) identified to the exact line, DB shape verified against `ReplenishmentEvent` model, JOIN strategy locked in decisions log §2, fixture already authored by PRP-3.1A. Single residual risk: the data-loader helper signature (sync-vs-async) — resolved in §15 decision A with a deterministic fall-back.

---

## Goal

Land the replenishment compute slice as a **service-layer-only, additive PR**:

1. Add `FeatureEngineeringService._compute_replenishment_features(df, cutoff_date) -> tuple[pd.DataFrame, list[str]]` to `app/features/featuresets/service.py`, mirroring `_compute_exogenous_features` (`service.py:360`).
2. Add a sync helper `_replenishment_events_to_frame(events)` (in-method dispatch) so the compute method can accept either an injected DataFrame (unit/leakage tests) or events fetched via the async loader (integration / runtime).
3. Add `FeatureDataLoader.load_replenishment_events(db, store_ids, product_ids, cutoff_date)` for the integration / runtime path. SQL-side filter on `date <= cutoff_date` to enforce time-safety BEFORE pandas sees the rows (decisions log §2).
4. Wire exactly one new `if self.config.replenishment_config:` branch into `FeatureEngineeringService.compute_features()` directly after the existing `exogenous_config` branch (`service.py:131-134`).
5. Add one new leakage test class in `tests/test_leakage.py` covering: per-entity `shift(N)` invariance, `shift(1).rolling(W).count()` ordering (NEVER `rolling(W).count().shift(1)`), and cross-series isolation between `(store_id, product_id)` pairs.
6. Add one new unit-test class in `tests/test_service.py` covering: happy path, zero-events entity, single-event entity, multi-event entity, cutoff boundary alignment.
7. **NO schema changes. NO route changes. NO new Alembic migration.** Compute method + tests + loader helper only.

End state — single commit, ≤ 250 LOC net diff, `mypy --strict` + `pyright --strict` clean, `pytest app/features/featuresets/tests/test_leakage.py app/features/featuresets/tests/test_service.py -v -k replenishment` green, full module sweep `pytest app/features/featuresets/ -v` shows zero regression in PRP-3.1A schemas or any pre-existing case.

---

## Why

- **Closes loop between seeded `replenishment_event` rows and consumer features.** The Phase 2 seeder (PR #92 / #93) emits `replenishment_event` rows but no downstream consumer reads them. After this slice, LightGBM trains on cadence-aware features — making the demo's narrative honest (PRD §1).
- **Unblocks PRP-3.1E (E2E + docs).** The end-to-end backtest preset in PRP-3.1E enables all three Phase 2 families simultaneously; replenishment is one of the three.
- **Parallel-safe with PRP-3.1B (lifecycle) and PRP-3.1D (promotion).** Once PRP-3.1A lands, this slice modifies only `service.py` (+ its test files) — no overlap with lifecycle's `service.py` branch other than the single `if` block in `compute_features()` (decisions log §3 documents the established merge-conflict-resolution convention: append in declaration order matching `enabled_features`).
- **Establishes the cross-table JOIN pattern inside a feature method.** This is the first compute method that pulls from a table OTHER than `sales_daily`. Locking the in-method async helper + sync DataFrame merge_asof pattern here makes PRP-3.1D's `promotion` JOIN trivial to follow.
- **Preserves the additive-contract invariant** (PRD §6 + PRD §11). Pre-PR `/featuresets/compute` callers (no `replenishment_config` in body) receive byte-identical responses; `config_hash()` and `feature_columns` order are unchanged.

---

## What

### User-visible behavior

- `POST /featuresets/compute` with `replenishment_config` set on the body emits new columns:
  ```jsonc
  {
    "feature_columns": [
      "...", // existing lag/rolling/calendar/exogenous columns unchanged
      "days_since_last_replenishment_lag1",
      "replenishment_count_w14_lag1"
    ]
  }
  ```
- Column names follow the deterministic naming `days_since_last_replenishment_lag{N}` and `replenishment_count_w{W}_lag{N}` where `N = config.lag_days` and `W = config.count_window_days` (PRD §7.2).
- Time-safety enforced at three layers: SQL `WHERE date <= cutoff_date`, pandas `groupby([store_id, product_id])`, and `shift(lag_days)` (for days-since) / `shift(1).rolling(window=W, min_periods=1).count()` (for rolling count). NEVER `rolling().shift()`.
- For `(store_id, product_id)` pairs with **zero replenishment events** in the cutoff window:
  - `replenishment_count_w{W}_lag{N}` is `0` (NOT NaN — count-with-no-events is a meaningful 0).
  - `days_since_last_replenishment_lag{N}` is NaN (sentinel for "no prior event observed"). Downstream callers may impute via `ImputationConfig`.
- Callers omitting `replenishment_config` see byte-identical responses (additive-contract invariant).

### Success Criteria

- [ ] `_compute_replenishment_features` exists on `FeatureEngineeringService` and is invoked from `compute_features()` exactly when `self.config.replenishment_config is not None`.
- [ ] When `include_days_since_last=True`, emits column `days_since_last_replenishment_lag{lag_days}` of dtype `float64` (NaN-sentinel for no-prior-event).
- [ ] When `include_count_window=True`, emits column `replenishment_count_w{count_window_days}_lag{lag_days}` of dtype `int64` (`0` for zero-event entities — never NaN).
- [ ] When BOTH flags True, both columns appear in `feature_columns` in stable order (days-since-first, then count).
- [ ] Leakage class `TestReplenishmentLeakage` in `test_leakage.py` asserts (a) per-entity `shift(N)` invariance, (b) `shift(1).rolling(W).count()` order, (c) cross-series isolation. Each assertion includes a `LEAKAGE DETECTED` failure message.
- [ ] Unit class `TestReplenishmentFeatures` in `test_service.py` covers: happy path, zero-events entity, single-event entity, multi-event entity, cutoff-boundary alignment (an event ON `cutoff_date` is included; an event AFTER is not).
- [ ] `uv run pytest app/features/featuresets/tests/test_leakage.py app/features/featuresets/tests/test_service.py -v -k replenishment` → all green.
- [ ] `uv run pytest app/features/featuresets/ -v` → no regression vs pre-PR.
- [ ] `uv run ruff check app/features/featuresets/` and `uv run ruff format --check app/features/featuresets/` → clean.
- [ ] `uv run mypy app/features/featuresets/service.py` → 0 errors.
- [ ] `uv run pyright app/features/featuresets/service.py` → 0 errors.
- [ ] Additive-contract proof: `FeatureSetConfig(name="x").config_hash()` is byte-identical pre/post PR (this slice doesn't touch `schemas.py`; the guard already lives in PRP-3.1A).
- [ ] Diff stat: ≤ +250 / -2 LOC (verify with `git diff --stat dev...`).

---

## All Needed Context

### Documentation & References

```yaml
# MUST READ before writing the compute method
- file: app/features/featuresets/service.py
  lines: 360-404
  why: _compute_exogenous_features is the canonical pattern. Same signature
       (df) -> tuple[pd.DataFrame, list[str]], same docstring shape, same
       RuntimeError guard, same groupby(entity_cols, observed=True).shift(...)
       idiom. Mirror this method line-for-line; the only structural difference
       is the upstream JOIN (replenishment_event is a separate table).

- file: app/features/featuresets/service.py
  lines: 75-162
  why: compute_features() — the orchestrator. New replenishment branch lands
       AFTER the exogenous branch at line 131-134 and BEFORE the stats block
       at line 137. The branch unpacks (result, cols) the same way every
       other branch does.

- file: app/features/featuresets/service.py
  lines: 195-235
  why: _compute_rolling_features — the shift(1).rolling(...) pattern with
       groupby.transform that respects entity isolation. Replenishment count
       MUST use this exact idiom: shift(1).rolling(window=W, min_periods=1).count()
       NEVER rolling(W).count().shift(1).

- file: app/features/featuresets/service.py
  lines: 407-471
  why: FeatureDataLoader.load_sales_data + load_calendar_data — the async
       SQLAlchemy pattern with select(...).where(...).order_by(...) and the
       dict-comprehension materialization into a pd.DataFrame. The new
       load_replenishment_events helper mirrors this shape.

- file: app/features/data_platform/models.py
  lines: 471-514
  why: ReplenishmentEvent — VERIFIED column names. CRITICAL: the DB column is
       `date` (line 493), NOT `event_date`. The PRP-3.1A fixture
       (phase2_replenishment_events_df) uses `event_date` for clarity in
       fixtures — the compute method MUST rename / accept either, see §15 A.

- file: app/features/featuresets/tests/conftest.py
  lines: 1-60
  why: sample_time_series + multi_series_time_series are the seed fixtures.
       The Phase 2 fixture (phase2_replenishment_events_df) lands here via
       PRP-3.1A — this PRP DEPENDS on PRP-3.1A being merged first.

- file: app/features/featuresets/tests/test_leakage.py
  lines: 204-286
  why: TestGroupIsolationLeakage is the canonical cross-series isolation
       test. TestReplenishmentLeakage MUST add a parallel test_cross_series_*
       case using a 2-store × 2-product replenishment-events DataFrame.

- file: app/features/featuresets/tests/test_leakage.py
  lines: 79-145
  why: TestRollingLeakage demonstrates the math-detectable leakage assertion
       style. Use sequential dates so the shift(1).rolling(W) ordering is
       observable: at row i with events on every date, count_w7 = min(i, 7).

- file: app/features/featuresets/tests/test_service.py
  lines: 18-82
  why: TestLagFeatures + TestRollingFeatures are the unit-test class shape.
       TestReplenishmentFeatures uses the same idiom: build a small df,
       construct config, instantiate service, call compute_features, assert
       expected column values.

- file: app/features/featuresets/schemas.py
  lines: ~250 (post-PRP-3.1A merge — exact line depends on insertion point)
  why: ReplenishmentConfig — referenced as self.config.replenishment_config.
       Field names: include_days_since_last, include_count_window, lag_days
       (default 1, ge=1, le=30), count_window_days (default 14, ge=7, le=60).
       DO NOT redefine; just read.

- file: alembic/versions/a8b9c0d1e234_add_retail_depth_columns_and_replenishment_event_table.py
  why: Confirms replenishment_event table exists. NO new migration is needed.

- url: https://pandas.pydata.org/docs/reference/api/pandas.merge_asof.html
  why: merge_asof for backward-looking JOIN of events onto sales rows.
       CRITICAL: pass direction="backward" + allow_exact_matches=True so an
       event ON the same date as a sales row counts as "today's last event".

- url: https://pandas.pydata.org/docs/reference/api/pandas.core.groupby.DataFrameGroupBy.shift.html
  why: groupby.shift behavior with NaN propagation — confirms shift(N) on a
       group with < N prior values returns NaN (the desired sentinel).

- url: https://pandas.pydata.org/docs/reference/api/pandas.core.window.rolling.Rolling.count.html
  why: rolling().count() returns counts of non-NaN values. Combined with
       shift(1), gives the exact "past W-day event count, excluding today".

- docfile: .agents/plans/initial-3-replenishment-features.md
  why: Slice spec. Particularly OTHER CONSIDERATIONS §4 (sparse-event
       entities — emit 0 for count, NaN-then-imputation for days-since),
       and §5 (count_window_days bounded 7..60 from PRP-3.1A).

- docfile: .agents/plans/phase2-decisions-and-prp-prep.md
  sections: §2 (Replenishment JOIN strategy — in-method async helper),
           §0 (column names verified)
  why: Locks the data-load approach and the "no new migration" assumption.

- docfile: .agents/plans/wire-phase2-features-to-featuresets.md
  sections: §6 (time-safety contract — mandatory), §7.2 (replenishment spec),
           §11 (success criteria)
  why: Parent PRD — read §6 before any pandas line is written.

- file: .claude/rules/product-vision.md
  why: Principle #5 — time-safety is non-negotiable. The leakage test IS
       the spec; never weaken it to make a feature pass.

- file: .claude/rules/test-requirements.md
  why: Integration tests against real Postgres; no DB mocks. Unit tests mock
       external IO. This slice's unit tests use the injected-DataFrame path;
       integration tests use the async loader path.
```

### Current Codebase tree (relevant subset)

```bash
app/features/featuresets/
├── __init__.py
├── routes.py             # unchanged in this PRP
├── schemas.py            # unchanged here — PRP-3.1A adds ReplenishmentConfig
├── service.py            # +1 _compute method, +1 loader method, +1 branch
└── tests/
    ├── __init__.py
    ├── conftest.py       # unchanged here — PRP-3.1A adds fixture
    ├── test_leakage.py   # +1 test class (TestReplenishmentLeakage)
    ├── test_schemas.py   # unchanged here
    └── test_service.py   # +1 test class (TestReplenishmentFeatures)

app/features/data_platform/
└── models.py             # READ ONLY — ReplenishmentEvent column shape
```

### Desired Codebase tree (after this PR)

```bash
app/features/featuresets/
├── service.py            # +~110 LOC: _compute_replenishment_features
│                         #          + load_replenishment_events helper
│                         #          + 1 branch in compute_features()
└── tests/
    ├── test_leakage.py   # +~70 LOC: TestReplenishmentLeakage (4 cases)
    └── test_service.py   # +~70 LOC: TestReplenishmentFeatures (5 cases)
```

Net diff target: **≤ 250 LOC** (compute + loader + branch + tests).

### Known Gotchas & Library Quirks

```python
# CRITICAL: The DB column on ReplenishmentEvent is `date` (models.py:493),
#   NOT `event_date`. The PRP-3.1A fixture uses `event_date` for clarity.
#   The compute method MUST normalize: accept the fixture's `event_date`
#   column when injected, accept `date` when loaded via SQL. Use a single
#   internal name (`event_date`) throughout the compute method and have the
#   loader rename on materialization. See §15 decision A.

# CRITICAL: `replenishment_event` is a SEPARATE TABLE from `sales_daily`.
#   The compute method receives a sales-shape DataFrame (one row per
#   (store_id, product_id, date)) and must JOIN events onto it by
#   (store_id, product_id) with date alignment. Use pd.merge_asof with
#   direction="backward" so each sales row gets the most-recent
#   event_date <= sales_date.

# CRITICAL: shift(N) for days-since:
#   1. Compute days_since_last_event PER (store_id, product_id) using
#      merge_asof to align "last event_date <= sales_date".
#   2. Take (sales_date - last_event_date).dt.days.
#   3. Apply groupby(entity_cols).shift(lag_days) to time-shift the column.
#   The lag is applied AFTER the days-since calculation — shifting the
#   result column, NOT the events.

# CRITICAL: shift(1).rolling(W).count() — NEVER rolling(W).count().shift(1).
#   The order matters because rolling().shift() looks at the rolling-result
#   timeline, leaving today's value AS one of the contributing rows. The
#   leakage test must mathematically distinguish the two patterns.

# CRITICAL: sparse-event entities. A (store_id, product_id) pair with zero
#   events in the cutoff window:
#     * replenishment_count_w{W}_lag{N} = 0 (count of nothing is 0, not NaN)
#     * days_since_last_replenishment_lag{N} = NaN (no prior event seen)
#   The count column dtype must be int64 — fill NaN with 0 BEFORE casting.
#   The days-since column dtype must be float64 (numpy can't have int NaN).

# CRITICAL: merge_asof requires SORTED keys. Sort the events DataFrame by
#   event_date BEFORE the merge — otherwise pandas raises ValueError.
#   merge_asof also requires both sides to have the same datetime dtype;
#   convert with pd.to_datetime BEFORE the merge.

# CRITICAL: groupby + merge_asof interaction. For multi-entity DataFrames,
#   pass `by=["store_id", "product_id"]` to merge_asof so the backward
#   search is per-entity. Without `by=`, a store=1 sales row could be
#   matched to a store=2 event — CROSS-SERIES LEAKAGE.

# CRITICAL: `T | None`, not `Optional[T]` (project style; PRP-3.1A §15).
#   `tuple[...]` for hashable; sequences (`list[int]` for non-frozen, not
#   tuple, for in-method local variables).

# CRITICAL: `mypy --strict` flags untyped lambdas inside .transform().
#   Use named inner functions with explicit signatures, mirroring
#   _compute_rolling_features (service.py:222-228).

# CRITICAL: pandas `groupby(..., observed=True)` is the project idiom
#   (every existing _compute_* uses it). Use it consistently to suppress
#   the upcoming pandas 3.x FutureWarning and to match existing tests.

# GOTCHA: pd.merge_asof with `tolerance=None` (the default) admits matches
#   arbitrarily far back. This is the DESIRED behavior — "last event ever"
#   is meaningful. DO NOT pass tolerance.

# GOTCHA: pandas `Series.dt.days` returns nullable Int64 in some versions
#   when the source has NaT. Force float64 explicitly to avoid downstream
#   mypy/pyright surprises:
#     days_col = (sales_dt - event_dt).dt.days.astype("float64")

# GOTCHA: The injected-DataFrame test path passes events directly. The
#   integration path uses the loader. Both must converge on the same
#   _compute_replenishment_features signature. Implementation: the method
#   accepts an OPTIONAL events_df parameter; if None, raise — unit tests
#   pass it explicitly, integration tests fetch it upstream and pass it in.
#   See §15 decision A for the alternative (in-method async DB call) and
#   why we rejected it.

# GOTCHA: TYPE_CHECKING block currently has `pass` (service.py:27). If you
#   need new TYPE_CHECKING-only imports (e.g., for AsyncSession in the
#   loader signature — but that's already imported at line 20), do NOT add
#   them inside TYPE_CHECKING; keep the existing pattern.

# GOTCHA: SQLAlchemy 2.0 async — load_replenishment_events MUST use the
#   imperative-style `from app.features.data_platform.models import
#   ReplenishmentEvent` and `select(ReplenishmentEvent.store_id, ...)`. Do
#   NOT use the legacy `query()` API.
```

---

## Implementation Blueprint

### Compute method (in `service.py`)

```python
# app/features/featuresets/service.py — additions only.
# Insert AFTER _compute_exogenous_features (after line 404) and BEFORE
# the FeatureDataLoader class declaration (line 407).

def _compute_replenishment_features(
    self,
    df: pd.DataFrame,
    events_df: pd.DataFrame | None = None,
) -> tuple[pd.DataFrame, list[str]]:
    """Compute replenishment-event features.

    CRITICAL: All replenishment features are lagged to prevent leakage.
    The events DataFrame must be pre-filtered to event_date <= cutoff_date
    by the caller (the loader does this SQL-side; tests do it explicitly).

    Produced columns (when matching flags are set):
        * days_since_last_replenishment_lag{N}: float64 — gap (days) from
          the current sales-row date to the most-recent prior event for
          the SAME (store_id, product_id). NaN when no prior event exists.
        * replenishment_count_w{W}_lag{N}: int64 — number of events in
          the trailing W-day window, excluding the current day (via
          shift(1)). 0 for entity-windows with no events.

    Args:
        df: Sales-shape DataFrame sorted by entity_cols + date_col.
        events_df: ReplenishmentEvent rows with columns
            [store_id, product_id, event_date]. May include extra columns
            (lead_time_days, ordered_qty, received_qty) — they are ignored.
            REQUIRED for this method; pass None and the method raises.

    Returns:
        Tuple of (df with new columns appended, list of new column names).

    Raises:
        RuntimeError: If replenishment_config is None, or events_df is None.
    """
    config = self.config.replenishment_config
    if config is None:
        raise RuntimeError(
            "_compute_replenishment_features called without replenishment_config"
        )
    if events_df is None:
        raise RuntimeError(
            "_compute_replenishment_features requires events_df "
            "(load via FeatureDataLoader.load_replenishment_events or "
            "inject in tests)"
        )

    result = df.copy()
    columns: list[str] = []

    # Normalize event_date dtype + sort (merge_asof requires sorted keys).
    events = events_df.loc[
        :, ["store_id", "product_id", "event_date"]
    ].copy()
    events["event_date"] = pd.to_datetime(events["event_date"])
    events = events.sort_values(["event_date", "store_id", "product_id"])

    # Align sales date dtype for merge_asof.
    sales_dt_col = "_sales_dt_internal"
    result[sales_dt_col] = pd.to_datetime(result[self.date_col])

    # --- Feature 1: days_since_last_replenishment_lag{N} -------------------
    if config.include_days_since_last:
        # Per-entity backward asof: each sales row gets the most-recent
        # event_date for the SAME (store_id, product_id). `by=` enforces
        # per-entity matching (NO CROSS-SERIES LEAKAGE).
        sorted_result = result.sort_values(sales_dt_col)
        with_last = pd.merge_asof(
            sorted_result,
            events.rename(columns={"event_date": "_last_event_dt"}),
            left_on=sales_dt_col,
            right_on="_last_event_dt",
            by=["store_id", "product_id"],
            direction="backward",
            allow_exact_matches=True,
        )
        # Reorder back to original (entity, date) order so the .shift() below
        # operates on the canonical orientation.
        with_last = with_last.sort_values([*self.entity_cols, self.date_col])
        # Days-since-last: (sales_date - last_event_date).dt.days, float64
        # so NaN survives (numpy int can't represent missing).
        days_since = (
            with_last[sales_dt_col] - with_last["_last_event_dt"]
        ).dt.days.astype("float64")
        # Apply config.lag_days SHIFT per entity (NEVER on the events).
        col_name = f"days_since_last_replenishment_lag{config.lag_days}"
        result[col_name] = (
            days_since.groupby(
                [with_last[c] for c in self.entity_cols],
                observed=True,
            )
            .shift(config.lag_days)
            .reset_index(drop=True)
        )
        columns.append(col_name)

    # --- Feature 2: replenishment_count_w{W}_lag{N} -----------------------
    if config.include_count_window:
        # Build a per-(entity, sales-date) event-indicator timeline by
        # aggregating events to daily counts then reindexing onto sales.
        # NOTE: a single sales row may map to multiple events on the same
        # date (rare; e.g., two POs received same day). Treat each event
        # as a unit count.
        event_counts = (
            events.assign(_one=1)
            .groupby(["store_id", "product_id", "event_date"], observed=True)["_one"]
            .sum()
            .reset_index()
            .rename(columns={"_one": "_event_count", "event_date": sales_dt_col})
        )
        # Left-merge counts onto sales by (store, product, date).
        merged = result.merge(
            event_counts,
            on=["store_id", "product_id", sales_dt_col],
            how="left",
        )
        merged["_event_count"] = merged["_event_count"].fillna(0).astype("int64")

        # shift(1).rolling(W).sum() per entity — NEVER .rolling().shift().
        window = config.count_window_days

        def _shift_rolling_count(
            x: "pd.Series[int]",
            w: int = window,
        ) -> "pd.Series[float]":
            return x.shift(1).rolling(window=w, min_periods=1).sum()

        rolling_counts = merged.groupby(
            self.entity_cols, observed=True
        )["_event_count"].transform(_shift_rolling_count)

        # Apply config.lag_days shift on TOP of the shift(1).rolling — so
        # the effective lag is lag_days (default 1). lag_days=1 means the
        # window covers (today-W .. today-1), excluding today.
        # If lag_days > 1, the window shifts further into the past.
        if config.lag_days > 1:
            rolling_counts = rolling_counts.groupby(
                [merged[c] for c in self.entity_cols],
                observed=True,
            ).shift(config.lag_days - 1)

        col_name = (
            f"replenishment_count_w{window}_lag{config.lag_days}"
        )
        # Fill remaining NaN (first rows of each group) with 0 and cast.
        result[col_name] = (
            rolling_counts.fillna(0).astype("int64").reset_index(drop=True)
        )
        columns.append(col_name)

    # Drop the internal sales-dt column.
    result = result.drop(columns=[sales_dt_col])

    return result, columns
```

### Branch wired into `compute_features()`

```python
# app/features/featuresets/service.py — modify in place inside compute_features.
# Insert AFTER the existing exogenous branch (after line 134) and BEFORE
# the stats-computation block (line 137).

        # 5. Exogenous features
        if self.config.exogenous_config:
            result, cols = self._compute_exogenous_features(result)
            feature_columns.extend(cols)

        # 6. Replenishment features (Phase 2 — PRP-3.1C)
        if self.config.replenishment_config:
            # events_df is passed in via compute_features kwargs (added below)
            # or fetched upstream by compute_features_for_series.
            events_df = getattr(self, "_replenishment_events_df", None)
            result, cols = self._compute_replenishment_features(
                result, events_df=events_df
            )
            feature_columns.extend(cols)
```

> NOTE: The events DataFrame is sidecar-attached to the service instance by the caller (`FeatureDataLoader` or test). See §15 decision A for why this beats threading a parameter through `compute_features()`.

### Async loader helper (in `service.py`)

```python
# Add to FeatureDataLoader class (after load_calendar_data, before
# the module-level compute_features_for_series function).

async def load_replenishment_events(
    self,
    db: AsyncSession,
    store_ids: list[int],
    product_ids: list[int],
    cutoff_date: date_type,
) -> pd.DataFrame:
    """Load replenishment events for the given entities up to cutoff_date.

    CRITICAL: SQL-side filter `date <= cutoff_date` enforces time-safety
    BEFORE any pandas code sees the rows. Per decisions log §2.

    Args:
        db: Async database session.
        store_ids: Store IDs to include.
        product_ids: Product IDs to include.
        cutoff_date: Maximum event date (inclusive).

    Returns:
        DataFrame with columns [store_id, product_id, event_date,
        lead_time_days, ordered_qty, received_qty]. The DB column `date`
        is renamed to `event_date` for clarity at the compute boundary.
    """
    from app.features.data_platform.models import ReplenishmentEvent

    stmt = (
        select(
            ReplenishmentEvent.store_id,
            ReplenishmentEvent.product_id,
            ReplenishmentEvent.date,
            ReplenishmentEvent.lead_time_days,
            ReplenishmentEvent.ordered_qty,
            ReplenishmentEvent.received_qty,
        )
        .where(
            ReplenishmentEvent.store_id.in_(store_ids),
            ReplenishmentEvent.product_id.in_(product_ids),
            ReplenishmentEvent.date <= cutoff_date,
        )
        .order_by(
            ReplenishmentEvent.store_id,
            ReplenishmentEvent.product_id,
            ReplenishmentEvent.date,
        )
    )

    result = await db.execute(stmt)
    rows = result.all()

    if not rows:
        return pd.DataFrame(
            columns=[
                "store_id",
                "product_id",
                "event_date",
                "lead_time_days",
                "ordered_qty",
                "received_qty",
            ]
        )

    return pd.DataFrame(
        [
            {
                "store_id": row.store_id,
                "product_id": row.product_id,
                "event_date": row.date,  # rename at the boundary
                "lead_time_days": row.lead_time_days,
                "ordered_qty": row.ordered_qty,
                "received_qty": row.received_qty,
            }
            for row in rows
        ]
    )
```

### Wire-in via `compute_features_for_series`

```python
# Extend the module-level compute_features_for_series function (service.py:535)
# to fetch events when replenishment_config is set, and attach to the service
# instance for the duration of the call.

# After loading sales_data and calendar_data, BEFORE constructing the service:

    events_df: pd.DataFrame | None = None
    if config.replenishment_config:
        events_df = await loader.load_replenishment_events(
            db=db,
            store_ids=[store_id],
            product_ids=[product_id],
            cutoff_date=cutoff_date,
        )

    service = FeatureEngineeringService(config)
    if events_df is not None:
        service._replenishment_events_df = events_df  # sidecar attach
    return service.compute_features(df, cutoff_date=cutoff_date)
```

### List of tasks (in execution order)

```yaml
Task 1 — Add load_replenishment_events helper:
MODIFY app/features/featuresets/service.py:
  - FIND pattern: "async def load_calendar_data(" inside class FeatureDataLoader
  - INJECT new method AFTER load_calendar_data (after its closing return,
    around line 532), BEFORE the module-level `async def compute_features_for_series`.
  - MIRROR the signature/structure of load_sales_data:
      * async def
      * sqlalchemy select() with .where() + .order_by()
      * fast-path empty DataFrame with named columns
      * dict-comprehension materialization
  - SQL-side filter MUST include `date <= cutoff_date` to enforce time-safety
    before any pandas code sees the rows (decisions log §2).
  - Rename `date` to `event_date` on materialization for compute-boundary
    clarity.

Task 2 — Add _compute_replenishment_features method:
MODIFY app/features/featuresets/service.py:
  - FIND pattern: "def _compute_exogenous_features(" — its closing `return result, columns`.
  - INJECT new method AFTER _compute_exogenous_features (after line 404),
    BEFORE `class FeatureDataLoader` (line 407).
  - SIGNATURE: `def _compute_replenishment_features(self, df, events_df=None) -> tuple[pd.DataFrame, list[str]]`
  - GUARD: raise RuntimeError if config is None OR events_df is None.
  - PRESERVE the docstring shape from _compute_exogenous_features.
  - DTYPE contracts (test-enforced):
      * days_since_last_replenishment_lag{N} → float64 (NaN for no-prior)
      * replenishment_count_w{W}_lag{N} → int64 (0 for no-events)
  - merge_asof MUST pass `by=["store_id", "product_id"]` to prevent
    cross-series leakage.

Task 3 — Wire branch into compute_features():
MODIFY app/features/featuresets/service.py:
  - FIND pattern: in compute_features, the lines:
        if self.config.exogenous_config:
            result, cols = self._compute_exogenous_features(result)
            feature_columns.extend(cols)
  - INSERT replenishment branch AFTER it, BEFORE the `# Compute stats` comment.
  - Pull events_df from `getattr(self, "_replenishment_events_df", None)`.
  - PRESERVE existing exogenous-branch byte-identically.

Task 4 — Wire compute_features_for_series:
MODIFY app/features/featuresets/service.py:
  - FIND pattern: "service = FeatureEngineeringService(config)" near the end
    of compute_features_for_series.
  - INSERT events-load + sidecar-attach BEFORE that line, so:
      events_df = None
      if config.replenishment_config:
          events_df = await loader.load_replenishment_events(...)
      service = FeatureEngineeringService(config)
      if events_df is not None:
          service._replenishment_events_df = events_df
  - PRESERVE final `return service.compute_features(df, cutoff_date=cutoff_date)`.

Task 5 — Add TestReplenishmentLeakage to test_leakage.py:
MODIFY app/features/featuresets/tests/test_leakage.py:
  - APPEND a new class TestReplenishmentLeakage AFTER TestEdgeCaseLeakage.
  - 4 required test methods (mirror TestRollingLeakage / TestGroupIsolationLeakage):
      * test_days_since_uses_only_past_events
      * test_count_window_uses_shift_then_rolling
        (mathematically distinguishes shift(1).rolling(W) from rolling(W).shift(1))
      * test_cross_series_isolation (2 stores × 2 products, events only in one)
      * test_event_on_cutoff_date_included_via_le_filter
  - Each leakage assertion MUST include a "LEAKAGE DETECTED" failure message.
  - Build per-test sales DataFrames + events DataFrames in-test (do not
    rely on `phase2_replenishment_events_df` for math-detectable cases —
    use sequential dates so the expected values are derivable).

Task 6 — Add TestReplenishmentFeatures to test_service.py:
MODIFY app/features/featuresets/tests/test_service.py:
  - APPEND a new class TestReplenishmentFeatures AFTER the last existing class.
  - 5 required test methods:
      * test_happy_path_three_events     — expected days-since + count
      * test_zero_events_entity          — count=0, days-since=NaN
      * test_single_event_entity         — count=0/1 boundary
      * test_cutoff_excludes_post_events — event AFTER cutoff invisible
      * test_dtypes_are_int64_and_float64 — column dtype contracts

Task 7 — Validation gates (run locally + CI):
RUN:
  uv run ruff check app/features/featuresets/
  uv run ruff format --check app/features/featuresets/
  uv run mypy app/features/featuresets/service.py
  uv run pyright app/features/featuresets/service.py
  uv run pytest app/features/featuresets/tests/test_leakage.py \
                app/features/featuresets/tests/test_service.py \
                -v -k replenishment
  uv run pytest app/features/featuresets/ -v   # full module regression
```

### Per-task pseudocode (non-obvious parts)

```python
# Task 5 — TestReplenishmentLeakage.test_count_window_uses_shift_then_rolling
# CRITICAL: this is the test that distinguishes the CORRECT
# shift(1).rolling(W).sum() from the INCORRECT rolling(W).sum().shift(1).
# Construct events such that the two patterns produce different counts.

def test_count_window_uses_shift_then_rolling(self) -> None:
    """CRITICAL: shift(1).rolling(W).count() MUST be the order.

    Events on dates 1, 3, 5 (W=3). Sales rows on every date 1..7.
    Correct (shift(1).rolling(3).sum()):
        date=1: shift gives NaN, rolling sum of [NaN] → 0
        date=2: shift gives 1 (event on d1), rolling sum [1] → 1
        date=3: shift gives 0 (no event on d2), rolling sum [1,0] → 1
        date=4: shift gives 1 (event on d3), rolling sum [1,0,1] → 2
        date=5: shift gives 0, rolling sum [0,1,0] → 1
        date=6: shift gives 1 (event on d5), rolling sum [1,0,1] → 2
        date=7: shift gives 0, rolling sum [0,1,0] → 1
    Incorrect (rolling(3).sum().shift(1)) would emit different values
    at date=3 (would be 1+0+1 shifted → still 2 at date=4 but
    DIFFERENT at date=3 because rolling at d3 INCLUDES today's event).
    The assertion at date=3 catches the difference.
    """
    from app.features.featuresets.schemas import (
        FeatureSetConfig, ReplenishmentConfig,
    )
    from app.features.featuresets.service import FeatureEngineeringService

    sales = pd.DataFrame({
        "date": pd.date_range("2024-01-01", periods=7, freq="D"),
        "store_id": [1]*7,
        "product_id": [1]*7,
        "quantity": list(range(1, 8)),
    })
    events = pd.DataFrame({
        "store_id": [1, 1, 1],
        "product_id": [1, 1, 1],
        "event_date": [date(2024,1,1), date(2024,1,3), date(2024,1,5)],
    })
    config = FeatureSetConfig(
        name="test",
        replenishment_config=ReplenishmentConfig(
            include_days_since_last=False,
            include_count_window=True,
            count_window_days=3,
            lag_days=1,
        ),
    )
    service = FeatureEngineeringService(config)
    service._replenishment_events_df = events
    result = service.compute_features(sales)
    col = "replenishment_count_w3_lag1"
    counts = result.df[col].tolist()
    expected = [0, 1, 1, 2, 1, 2, 1]
    assert counts == expected, (
        f"LEAKAGE DETECTED: count column = {counts}, expected {expected}. "
        "shift(1).rolling(W).sum() order may be reversed to "
        "rolling(W).sum().shift(1)."
    )

# Task 5 — test_cross_series_isolation
# CRITICAL: events only on store=1; store=2 must NEVER see counts > 0.
def test_cross_series_isolation(self) -> None:
    sales = pd.DataFrame({
        "date": list(pd.date_range("2024-01-01", periods=5, freq="D")) * 2,
        "store_id": [1]*5 + [2]*5,
        "product_id": [1]*10,
        "quantity": list(range(10)),
    })
    events = pd.DataFrame({
        "store_id": [1, 1],
        "product_id": [1, 1],
        "event_date": [date(2024,1,2), date(2024,1,4)],
    })
    # ... configure, run, assert store=2's count column is all 0 and
    # days_since is all NaN.

# Task 6 — TestReplenishmentFeatures.test_zero_events_entity
def test_zero_events_entity(self) -> None:
    sales = pd.DataFrame({
        "date": pd.date_range("2024-01-01", periods=5, freq="D"),
        "store_id": [1]*5, "product_id": [1]*5,
        "quantity": [1,2,3,4,5],
    })
    events = pd.DataFrame(columns=[
        "store_id", "product_id", "event_date",
    ])  # ZERO events
    # ... run; assert count column is all 0 and dtype int64;
    # assert days-since is all NaN and dtype float64.

# Task 6 — test_cutoff_excludes_post_events
def test_cutoff_excludes_post_events(self) -> None:
    """Event AFTER cutoff must not influence pre-cutoff feature rows."""
    # Sales 2024-01-01..2024-01-05; cutoff=2024-01-04.
    # Events: 2024-01-02 (pre), 2024-01-05 (post-cutoff — should NOT appear).
    # After compute_features(df, cutoff_date=date(2024,1,4)):
    #   - df is filtered to ≤ cutoff (5 → 4 rows).
    #   - At date=2024-01-04, days_since should reflect event on 1-02 only.
    #   - The 2024-01-05 event must be invisible — that's the loader's
    #     responsibility in runtime, but in tests we manually filter
    #     events_df by event_date <= cutoff_date before passing.
    # Mirrors TestCutoffLeakage.test_features_computed_only_from_pre_cutoff_data.
```

### Integration Points

```yaml
DATABASE:
  - NO migration required. replenishment_event table exists since
    alembic/versions/a8b9c0d1e234_add_retail_depth_columns_and_replenishment_event_table.py
  - SQL-side filter in load_replenishment_events enforces time-safety
    BEFORE pandas (decisions log §2).

CONFIG:
  - NO new env vars. ReplenishmentConfig fields are request-body knobs
    (already declared by PRP-3.1A).

ROUTES:
  - NO changes. POST /featuresets/compute already accepts FeatureSetConfig
    with the new optional replenishment_config field (PRP-3.1A wire-in).

DOCS:
  - NO docs touched in this slice. PRP-3.1E updates
    docs/PHASE/3-FEATURE_ENGINEERING.md and docs/_base/DOMAIN_MODEL.md
    once all three compute methods land.

ALEMBIC:
  - NO new revision.

DOWNSTREAM PRPs:
  - PRP-3.1E (E2E + docs) — depends on this slice + PRP-3.1B + PRP-3.1D.
    The end-to-end backtest enables all three Phase 2 families simultaneously.
```

---

## Validation Loop

### Level 1: Syntax & Style

```bash
# Run from repo root. Fix errors before proceeding to Level 2.
uv run ruff check app/features/featuresets/ --fix
uv run ruff format --check app/features/featuresets/

# Expected: clean. If `ruff format --check` complains, run:
#   uv run ruff format app/features/featuresets/
```

### Level 2: Type Checks (BOTH must be clean — merge gate)

```bash
uv run mypy app/features/featuresets/service.py
uv run pyright app/features/featuresets/service.py

# Expected: 0 errors on each. Common failure modes for this slice:
#   - mypy "incompatible types in assignment" on dtype-cast chains: ensure
#     `.astype("int64")` and `.astype("float64")` are the final ops.
#   - pyright "reportUnknownMemberType" on pd.merge_asof: this is a known
#     pandas-stubs gap. If it fires, narrow the call with an explicit cast
#     or annotate the result as `pd.DataFrame`. DO NOT silence with
#     `# type: ignore` without the specific rule code.
#   - mypy "untyped lambda" inside .transform(): replace with a named
#     inner function (`_shift_rolling_count` in the blueprint above).
```

### Level 3: Unit Tests (new compute method + existing module regressions)

```bash
# Replenishment-focused subset:
uv run pytest app/features/featuresets/tests/test_leakage.py \
              app/features/featuresets/tests/test_service.py \
              -v -k replenishment

# Full module sweep — must show 0 regressions in pre-existing tests:
uv run pytest app/features/featuresets/ -v

# If failing: read the error, find root cause. NEVER weaken the leakage
# test to make a feature pass — the test is the spec.
```

### Level 4: Additive-contract proof

```bash
# This slice does NOT touch schemas.py — config_hash() invariant is
# already guarded by PRP-3.1A's snapshot test. Verify the existing guard
# still passes:
uv run pytest app/features/featuresets/tests/test_schemas.py \
              -v -k config_hash_unchanged_when_phase2_omitted

# Expected: PASS. If it fails, you accidentally touched FeatureSetConfig
# defaults or field ordering. Revert that change.
```

### Level 5: Integration (real Postgres)

```bash
# Start the stack:
docker compose up -d
uv run alembic upgrade head

# Seed a small Phase 2 dataset:
uv run python scripts/seed_random.py --full-new --seed 42 --confirm

# Start the API:
uv run uvicorn app.main:app --reload --port 8123 &
APP_PID=$!

# Call /featuresets/compute with replenishment_config set:
curl -s -X POST http://localhost:8123/featuresets/compute \
  -H "Content-Type: application/json" \
  -d '{
    "store_id":1,"product_id":1,"cutoff_date":"2024-06-30",
    "lookback_days":180,
    "config":{
      "name":"replenishment-smoke",
      "replenishment_config":{
        "include_days_since_last":true,
        "include_count_window":true,
        "lag_days":1,
        "count_window_days":14
      }
    }
  }' \
  | jq '.feature_columns'
# Expected: includes "days_since_last_replenishment_lag1" and
#           "replenishment_count_w14_lag1".

# Call WITHOUT replenishment_config — additive-contract sanity:
curl -s -X POST http://localhost:8123/featuresets/compute \
  -H "Content-Type: application/json" \
  -d '{
    "store_id":1,"product_id":1,"cutoff_date":"2024-06-30",
    "lookback_days":180,
    "config":{"name":"baseline"}
  }' \
  | jq '.feature_columns'
# Expected: no replenishment_* columns. Identical to pre-PR shape.

# Out-of-bounds rejection (count_window_days=4 violates ge=7):
curl -s -X POST http://localhost:8123/featuresets/compute \
  -H "Content-Type: application/json" \
  -d '{
    "store_id":1,"product_id":1,"cutoff_date":"2024-06-30",
    "config":{
      "name":"bad",
      "replenishment_config":{"count_window_days":4}
    }
  }' \
  | jq '.title'
# Expected: "validation_error" (RFC 7807 problem+json).

kill $APP_PID
```

---

## Final Validation Checklist

- [ ] All tests pass: `uv run pytest app/features/featuresets/ -v`
- [ ] Replenishment subset green: `uv run pytest app/features/featuresets/tests/test_leakage.py app/features/featuresets/tests/test_service.py -v -k replenishment`
- [ ] No linting errors: `uv run ruff check app/features/featuresets/`
- [ ] No formatting drift: `uv run ruff format --check app/features/featuresets/`
- [ ] No mypy errors: `uv run mypy app/features/featuresets/service.py`
- [ ] No pyright errors: `uv run pyright app/features/featuresets/service.py`
- [ ] Additive-contract proof: PRP-3.1A's `test_config_hash_unchanged_when_phase2_omitted` still passes
- [ ] HTTP smoke OK: invalid `count_window_days=4` rejected with RFC 7807 (Level 5)
- [ ] Diff stat: ≤ +250 / -2 LOC (verify with `git diff --stat dev...`)
- [ ] Single commit, message: `feat(features): implement replenishment compute method (#<issue>)` (replace `<issue>` with the open GitHub issue from `.agents/plans/phase2-decisions-and-prp-prep.md` §7 outstanding-action)
- [ ] No `schemas.py` changes, no `routes.py` changes (verify with `git diff dev... -- app/features/featuresets/schemas.py app/features/featuresets/routes.py` → empty)
- [ ] No new Alembic migration created (verify with `ls alembic/versions/ | wc -l` → unchanged)
- [ ] Leakage tests assert per-entity `shift(N)` invariance AND `shift(1).rolling(W)` ordering AND cross-series isolation

---

## Anti-Patterns to Avoid

- ❌ **Do NOT use `rolling(W).sum().shift(1)`.** It looks similar but leaks today's event into the window. The leakage test in Task 5 mathematically distinguishes the two.
- ❌ **Do NOT call `pd.merge_asof` without `by=["store_id", "product_id"]`.** Without `by=`, a store=1 sales row can match a store=2 event — silent cross-series leakage.
- ❌ **Do NOT issue the events SQL without a `date <= cutoff_date` predicate.** Time-safety MUST be enforced SQL-side before pandas sees the rows (decisions log §2).
- ❌ **Do NOT fill `days_since_last_replenishment_lag{N}` with a sentinel integer (e.g., 9999) inside the compute method.** Leave NaN for downstream `ImputationConfig` to handle. The fill-with-int would silently corrupt LightGBM splits.
- ❌ **Do NOT fill `replenishment_count_w{W}_lag{N}` with NaN.** Count-of-nothing is 0 — fill 0 and cast to int64.
- ❌ **Do NOT touch `schemas.py`.** `ReplenishmentConfig` lives in PRP-3.1A. Touching it here breaks the additive-contract snapshot guard.
- ❌ **Do NOT touch `routes.py`.** The request body is `FeatureSetConfig`; the new optional field is already accepted (PRP-3.1A wire-in).
- ❌ **Do NOT change the order of existing `_compute_*` branches in `compute_features()`.** Append the new branch AFTER exogenous — never reorder.
- ❌ **Do NOT thread `events_df` as a positional parameter through `compute_features()`.** Use the sidecar-attach pattern (`service._replenishment_events_df = events_df`) — see §15 decision A. Threading the param widens the public API of an existing method, which crosses the additive-contract line.
- ❌ **Do NOT inline an `await db.execute()` inside `_compute_replenishment_features`.** The compute method stays synchronous (mirrors `_compute_exogenous_features`). The async fetch is in `FeatureDataLoader.load_replenishment_events`.
- ❌ **Do NOT use untyped lambdas inside `.transform()`.** `mypy --strict` rejects them. Use a named inner function with explicit signature.
- ❌ **Do NOT use `Optional[T]`.** Project style is `T | None` (PEP 604).
- ❌ **Do NOT add an AI co-author trailer** to the commit (forbidden by `.claude/rules/commit-format.md`).

---

## §15 — PRP-Authoring Decisions

These are decisions made during PRP authoring that the INITIAL didn't lock — recorded here so a future session can audit the reasoning.

### Decision A — `events_df` is sidecar-attached on the service instance, not threaded through `compute_features()`

**INITIAL said:** "Decide: join inside `_compute_replenishment_features`, or expect the caller to join upstream? Recommended: join inside the method, BUT only fetch `event_date <= cutoff_date` to preserve time-safety."
**My call:** Two-layer split — `FeatureDataLoader.load_replenishment_events` does the SQL fetch (async, time-safe), and `_compute_replenishment_features` does the in-memory JOIN (sync, mirrors every other `_compute_*`). The events DataFrame is passed via `service._replenishment_events_df` (sidecar attribute), NOT as a parameter on `compute_features()`.
**Why:**
1. `compute_features()` is `def`, not `async def`. Adding a parameter that's only sometimes used by one of six branches widens the existing public API — crosses the additive-contract line.
2. `_compute_exogenous_features` reads from columns already on `df` (inline). Replenishment is the first cross-table family, and the same pattern will repeat for PRP-3.1D (promotion). Locking the sidecar pattern here makes PRP-3.1D trivial.
3. Tests inject the DataFrame explicitly via `service._replenishment_events_df = ...` — no async overhead in unit tests, no DB mock needed.
4. The runtime path (`compute_features_for_series`) handles the async fetch and the sidecar attach in one place.
**Alternative considered:** Make `_compute_replenishment_features` an `async def` that takes a `db: AsyncSession`. Rejected because it would force `compute_features()` to become async, which cascades into every existing caller — a breaking change.
**Risk if reversed:** A future refactor that drops the sidecar attribute MUST re-thread `events_df` everywhere. Single point of attention; documented here.

### Decision B — Column dtypes are locked: float64 for days-since, int64 for count

**INITIAL said (OTHER CONSIDERATIONS §4):** "feature must emit `0` (not NaN) for `replenishment_count_w{W}_lag{N}` and a sentinel (e.g., a max-cap value or NaN-with-imputation flag) for `days_since_last_replenishment_lag{N}`. Match the existing exogenous method's NaN policy."
**My call:**
- `days_since_last_replenishment_lag{N}` → `float64` with NaN sentinel. No max-cap integer. Downstream `ImputationConfig` (or LightGBM's native NaN handling) is the right boundary for imputation.
- `replenishment_count_w{W}_lag{N}` → `int64` with `0` for no-events. Counts of nothing are 0, not unknown.
**Why:** Matches the existing exogenous policy (`stockout_lag_1` returns NaN when no prior data). Forces dtype discipline (the test asserts dtypes explicitly). Imputation policy is a separate concern.
**Risk if reversed:** A "max-cap integer" sentinel (e.g., 9999) would corrupt LightGBM's tree splits; a NaN count would force every downstream consumer to handle two missing-data semantics. Locking the dtype contract here prevents both.

### Decision C — `lag_days` semantics: lag_days=1 means "exclude today" via `shift(1).rolling(W)`, lag_days>1 adds an extra `shift(lag_days-1)` on top

**INITIAL said:** "`shift(N).rolling(W).sum()` of event indicator."
**My call:** Default `lag_days=1` maps to `shift(1).rolling(W).sum()` (the canonical "exclude today" pattern). For `lag_days>1`, apply an additional `shift(lag_days-1)` on the rolling result, so the window covers `(today-W-(lag_days-1)..today-lag_days)`.
**Why:** The PRD §7.2 table says "`shift(N).rolling(W).sum()`" but the parent PRD §6 time-safety contract says "`shift(1).rolling(W)` — NEVER `rolling().shift(1)`". The two reconcile when `lag_days=1`. For `lag_days>1`, the layered approach preserves the shift(1).rolling(W) safety boundary AND honors the user's requested lag.
**Alternative considered:** `shift(lag_days).rolling(W).sum()` directly. Rejected because it conflates two semantics (the "no-today" shift and the "user lag") into a single shift, making the leakage test harder to reason about. Layering is auditable.
**Risk if reversed:** A lag_days=1 caller still sees `shift(1).rolling(W)` (correct). A lag_days=7 caller sees `shift(1).rolling(W).shift(6)` (still correct, slightly less efficient than `shift(7).rolling(W)`). The performance hit is negligible at expected data volumes.

### Decision D — `load_replenishment_events` accepts `list[int]` for entity IDs (matches future multi-entity callers); single-entity callers wrap in `[id]`

**INITIAL did not specify.** The companion `load_sales_data` (service.py:413) takes scalar `store_id: int, product_id: int`.
**My call:** `load_replenishment_events(store_ids: list[int], product_ids: list[int], cutoff_date)`.
**Why:** The async loader is shared infrastructure. PRP-3.1E will train across many series; loading events one-at-a-time would N+1-query the DB. `IN (:ids)` is the standard SQLAlchemy idiom. Single-series callers pass `[store_id]` / `[product_id]` — trivial wrapping.
**Risk if reversed:** Minor — could add a scalar overload later if needed.

### Decision E — The internal helper column `_sales_dt_internal` is created and dropped within `_compute_replenishment_features`; never persists in the output

**INITIAL did not specify.** Existing `_compute_*` methods don't add helper columns to the output.
**My call:** Create `_sales_dt_internal` for the merge_asof, drop it before return.
**Why:** Pattern fidelity. The output DataFrame must contain only the original columns plus the new feature columns — adding internal helpers would silently change the response shape (which `feature_columns` doesn't include, but `response.rows[0].features` keys would).
**Risk if reversed:** Trivial cleanup bug; the test that asserts `feature_columns` length would catch it.

---

## §16 — Open Questions for the Implementing Agent

None. All decisions are resolved above. If a surprise emerges during implementation:

- **If `pyright --strict` rejects `pd.merge_asof(..., by=...)` signatures** — fall back to a manual per-entity groupby + per-group merge_asof loop. The test contract (per-entity isolation, dtype, leakage ordering) is unchanged; only the implementation idiom shifts. Cite the pyright error in the PR description.
- **If diff exceeds 250 LOC** — STOP and ask before adding scope. Most likely the `load_replenishment_events` helper grew (e.g., joining lead_time_days for a separate feature) — defer that to a follow-up.
- **If `compute_features_for_series` integration test reveals a sidecar-attribute race** (concurrent requests sharing a service instance) — fall back to threading `events_df` as a parameter on a NEW async overload `compute_features_async`. Document in §15 as Decision F. Single-request paths are not affected.

If anything else surfaces, STOP and ask — don't quietly weaken the leakage spec or the time-safety SQL filter.

---

## Confidence Score: 9 / 10

**Why 9, not 10:**
- ✅ Pattern source identified to the exact line (`_compute_exogenous_features` at `service.py:360`).
- ✅ DB shape verified (`ReplenishmentEvent` at `models.py:471-514`); column rename `date → event_date` documented and bidirectional.
- ✅ JOIN strategy locked by decisions log §2 (in-method via async helper).
- ✅ Cross-series isolation enforced via `merge_asof(..., by=[entity_cols])` AND `groupby(entity_cols, observed=True).shift()` — belt-and-braces.
- ✅ Sparse-event dtype contracts (`int64` count with 0-fill, `float64` days-since with NaN) explicitly tested.
- ✅ Validation gates are deterministic and executable as-written.
- ✅ Additive-contract preserved by NOT touching `schemas.py` / `routes.py`.
- ⚠️ The one residual risk: `pd.merge_asof` + pandas-stubs interaction under `pyright --strict`. Mitigation documented in §16 (per-entity loop fall-back). Out of an abundance of caution, the implementer should run `pyright` on the FIRST draft and adjust before extending the test suite.

Goal achieved: an implementing agent with no prior session context can read this PRP, edit 3 files (service.py, test_leakage.py, test_service.py), run 7 commands, and ship a green PR.
