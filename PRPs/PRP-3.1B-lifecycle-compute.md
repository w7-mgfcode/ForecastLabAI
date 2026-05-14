# PRP-3.1B: Lifecycle Feature Compute Method

**Feature**: `.agents/plans/initial-2-lifecycle-features.md`
**Parent PRP**: PRP-3.1 (umbrella — Phase 2 feature wiring; PRP-3.1A through PRP-3.1E are the 5 slices)
**Parent PRD**: `.agents/plans/wire-phase2-features-to-featuresets.md`
**Depends on**: PRP-3.1A (must merge first — provides `LifecycleConfig`, `phase2_product_attrs_df`, `enabled_features` token)
**Unblocks**: PRP-3.1E (E2E + docs); does not block PRP-3.1C/D (they run in parallel against the same `LifecycleConfig`-free surface)
**Status**: Ready for Implementation (after PRP-3.1A merges)
**Confidence Score**: 9 / 10 — pattern source verified line-for-line (`_compute_exogenous_features` at `service.py:360-404`), DB columns verified (`product.launch_date` / `product.discontinue_date` both `Mapped[date | None]` at `models.py:101-102`), leakage spec invariants reused from `test_leakage.py`. One residual uncertainty: in-method DB JOIN vs. caller-supplied attrs DataFrame — resolved in §15 Decision A with a defensible default.

---

## Goal

Implement the time-safe compute method that turns Phase 2 product-lifecycle dates into model-ready continuous features:

1. New method `FeatureEngineeringService._compute_lifecycle_features(df) -> tuple[pd.DataFrame, list[str]]` in `app/features/featuresets/service.py`.
2. Method reads `product.launch_date` and `product.discontinue_date` per-row (joined onto `df` from a caller-supplied product-attrs DataFrame or loaded inside the method — see §15 Decision A).
3. Produces continuous integer columns (NO categorical stage):
   - `days_since_launch_lag{N}` when `config.include_days_since_launch` is True.
   - `days_since_discontinue_lag{N}` when `config.include_days_since_discontinue` is True.
   - Both lagged by `config.lag_days` (default 1) via `df.groupby(entity_cols)[col].shift(lag_days)` to prevent leakage. NULL when the product is not-yet-launched or has no `launch_date` / `discontinue_date` set.
4. One new branch `if self.config.lifecycle_config:` in `FeatureEngineeringService.compute_features()` — mirrors the existing `if self.config.exogenous_config:` block (`service.py:132-134`) exactly.
5. New leakage case(s) in `tests/test_leakage.py` proving — via sequential-date fixtures — that `days_since_launch_lag1` at row `i` reflects only data ≤ row `i-1`.
6. New unit test(s) in `tests/test_service.py` (happy path + edge cases: NULL `launch_date`, `discontinue_date` before cutoff, single-row entity).
7. **NO schema changes** — `LifecycleConfig`, `FeatureSetConfig.lifecycle_config`, and `get_enabled_features()` → `"lifecycle"` token already landed in PRP-3.1A.
8. **NO routes/migrations changes** — additive contract preserved.

End state — single commit, ≤ 200 LOC net diff, `mypy --strict` + `pyright --strict` clean, full featuresets suite green (`uv run pytest app/features/featuresets/ -v`), leakage proof recorded as a new test case in `test_leakage.py`.

---

## Why

- **Closes the loop between seeded realism and the model.** Phase 2 added `product.launch_date` / `product.discontinue_date` to every product (#92 / #93), but no downstream consumer reads them. Today, toggling a "new product launch" scenario in the seeder UI produces zero observable change in LightGBM forecasts.
- **PRD Mission, Principle 1 — time-safety is non-negotiable.** This slice's existence is to prove the lifecycle compute method respects the leakage spec at `app/features/featuresets/tests/test_leakage.py`. The leakage test ships in the SAME PR as the compute method (test-first per INITIAL §OTHER_CONSIDERATIONS).
- **Pilot-validates the Phase 2 compute pattern.** This is the FIRST compute slice after PRP-3.1A's schemas. If a gotcha emerges (NULL handling for `discontinue_date`, missing product attrs, sparse launch dates), it surfaces HERE — before PRP-3.1C (replenishment) and PRP-3.1D (promotion) replicate the pattern. Resolving it once keeps the next two slices small.
- **Continuous-only encoding is locked.** Decision 1 in `.agents/plans/phase2-decisions-and-prp-prep.md §1` rejected the categorical `lifecycle_stage_*` one-hot family entirely. LightGBM splits on the continuous `days_since_launch` will discover stage boundaries naturally; no registry-column-name irreversibility; no seeder-threshold coupling.
- **Unblocks PRP-3.1E.** The end-to-end backtest in PRP-3.1E needs at least ONE Phase 2 family producing real columns to prove the LightGBM pipeline accepts the extended matrix. Lifecycle is the simplest of the three and the natural pilot.

---

## What

### User-visible behavior

- `POST /featuresets/compute` with `config.lifecycle_config` set returns a `feature_matrix` whose `feature_columns` now include:
  - `days_since_launch_lag{N}` (int, nullable) — when `include_days_since_launch=True`
  - `days_since_discontinue_lag{N}` (int, nullable) — when `include_days_since_discontinue=True`
- `enabled_features` continues to include `"lifecycle"` (already wired in PRP-3.1A).
- Requests without `lifecycle_config` (the entire pre-Phase-2 caller surface) return byte-identical responses to pre-PR behavior — `feature_columns` and `config_hash` unchanged.
- Validation errors on `lifecycle_config` (e.g., `lag_days=0`) continue to surface as RFC 7807 `application/problem+json` 422 via `app/core/problem_details.py` (handled by the existing FastAPI / Pydantic v2 handler — no new error shape).

### Success Criteria

- [ ] `FeatureEngineeringService._compute_lifecycle_features` exists at `app/features/featuresets/service.py`, signature `(self, df: pd.DataFrame) -> tuple[pd.DataFrame, list[str]]`, mirroring `_compute_exogenous_features` at line 360.
- [ ] One new `if self.config.lifecycle_config:` branch in `compute_features()`, placed AFTER the exogenous branch (line 134), BEFORE the stats block at line 136.
- [ ] When `include_days_since_launch=True`: column `days_since_launch_lag{lag_days}` is in `feature_columns` and contains `int | NaN`. Pandas type is nullable Int64 OR float64-with-NaN (both acceptable — assertions check `pd.isna()` not dtype).
- [ ] When `include_days_since_discontinue=True`: column `days_since_discontinue_lag{lag_days}` is in `feature_columns` and contains `int | NaN`. NaN when `discontinue_date IS NULL`; negative integer when `date < discontinue_date` (signed — per INITIAL §FEATURE bullet 3); zero or positive when `date >= discontinue_date`.
- [ ] NULL `launch_date` produces NaN for all `days_since_launch_lag*` rows for that product (no crash, no silent zero).
- [ ] First `lag_days` rows of every `(store_id, product_id)` series have NaN for the lagged column (no leakage from neighbor series — group isolation invariant).
- [ ] Leakage test `test_lifecycle_no_future_leakage` in `tests/test_leakage.py` is green and asserts that, given a known `launch_date`, the value at row `i` of `days_since_launch_lag1` equals `(date[i-1] - launch_date).days` exactly (mathematical detector — any leakage produces a wrong integer).
- [ ] Group-isolation leakage test asserts that two products with different `launch_date` values produce independently-correct `days_since_launch_lag1` columns (no cross-series contamination).
- [ ] Unit test `test_compute_lifecycle_features_happy_path` in `tests/test_service.py` covers the canonical `phase2_product_attrs_df` fixture (P1 launched 2023-06-01, discontinued 2025-12-31; P2 launched 2024-03-15, NULL discontinue).
- [ ] Unit test `test_compute_lifecycle_features_null_launch_date` covers a product whose `launch_date IS NULL` — expects all-NaN column for that product, no exception.
- [ ] Unit test `test_compute_lifecycle_features_discontinue_before_cutoff` covers `discontinue_date < cutoff_date` — expects positive integer days for rows after the discontinue date.
- [ ] `uv run pytest app/features/featuresets/ -v` → all green (no regression in any pre-existing PRP-3.1A test).
- [ ] `uv run pytest app/features/featuresets/tests/test_leakage.py app/features/featuresets/tests/test_service.py -v -k lifecycle` → all green.
- [ ] `uv run ruff check app/features/featuresets/` → clean.
- [ ] `uv run mypy app/features/featuresets/service.py` → 0 errors.
- [ ] `uv run pyright app/features/featuresets/service.py` → 0 errors.
- [ ] Net diff target: ≤ 200 LOC additions; 0 modifications outside the targeted insertion points; 0 deletions of existing code.
- [ ] Commit: `feat(features): implement lifecycle compute method (#<issue>)` — single commit, no AI co-author trailer.

---

## All Needed Context

### Documentation & References

```yaml
# MUST READ before writing the compute method
- file: app/features/featuresets/service.py
  lines: 360-404
  why: _compute_exogenous_features is the canonical line-for-line template.
       Same signature, same `if config is None: raise RuntimeError(...)` guard,
       same `result = df.copy()` + `columns: list[str] = []` shape, same
       `df.groupby(self.entity_cols, observed=True)[col].shift(lag)` idiom.
       The lifecycle method MUST mirror this — do not invent a new shape.

- file: app/features/featuresets/service.py
  lines: 132-134
  why: The exogenous branch wiring in compute_features. The lifecycle branch
       is a 3-line clone inserted immediately AFTER this block, BEFORE the
       stats block at line 136. Order matters because `enabled_features`
       (already shipped by PRP-3.1A) emits "lifecycle" AFTER "exogenous".

- file: app/features/featuresets/service.py
  lines: 100-110
  why: compute_features sorts by [*entity_cols, date_col] and filters to
       cutoff_date BEFORE any feature computation. Our method runs AFTER
       that filter — we may assume `df` is already sorted and cutoff-respecting.

- file: app/features/featuresets/service.py
  lines: 164-193
  why: _compute_lag_features shows the EXACT shift-by-lag idiom we copy.
       `df.groupby(self.entity_cols, observed=True)[col].shift(lag)`.
       Use `observed=True` for categorical safety (matches the codebase).

- file: app/features/featuresets/schemas.py
  lines: TBD (after PRP-3.1A merges) — LifecycleConfig with three fields:
         include_days_since_launch (bool), include_days_since_discontinue
         (bool), lag_days (int, Field(ge=1, le=30, default=1))
  why: Schema is already locked. This PRP MUST NOT widen it. Use exactly
       the three field names.

- file: app/features/featuresets/tests/test_leakage.py
  lines: 20-76
  why: TestLagLeakage is the exact rejection pattern: sequential values
       so leakage is mathematically detectable. Mirror this with sequential
       DATES (date+1 per row → days-since-launch is exactly the row index).
       The new test class `TestLifecycleLeakage` lives in this file.

- file: app/features/featuresets/tests/test_leakage.py
  lines: 204-247
  why: TestGroupIsolationLeakage shows how to assert cross-series safety.
       The lifecycle test MUST replicate this for two products with
       different launch_dates — proves shift(lag) respects groupby boundaries.

- file: app/features/featuresets/tests/conftest.py
  lines: TBD (after PRP-3.1A merges) — phase2_product_attrs_df fixture with
         columns: product_id, launch_date, discontinue_date.
         P1: launch_date=date(2023,6,1), discontinue_date=date(2025,12,31)
         P2: launch_date=date(2024,3,15), discontinue_date=pd.NaT
  why: This is the canonical input. The leakage/unit tests merge it onto
       sample_time_series (or build a derivative). Do not invent a new fixture.

- file: app/features/featuresets/tests/conftest.py
  lines: 17-33
  why: sample_time_series is the multi-day fixture (30 days from 2024-01-01
       for store=1, product=1). Joined with phase2_product_attrs_df it
       becomes the canonical lifecycle test input.

- file: app/features/data_platform/models.py
  lines: 89-126
  why: Product table — `launch_date: Mapped[datetime.date | None]` (line 101),
       `discontinue_date: Mapped[datetime.date | None]` (line 102). Both
       nullable. CheckConstraint at 122-125 guarantees
       discontinue_date >= launch_date when both set. lifecycle_stage exists
       (line 100) but we DO NOT use it per Decision 1.

- file: app/features/featuresets/service.py
  lines: 407-471
  why: FeatureDataLoader is the existing async DB-load pattern. If §15
       Decision A is reversed and you choose in-method JOIN, mirror this
       loader's `select(...).where(...).order_by(...)` style with
       AsyncSession.execute.

- url: https://pandas.pydata.org/docs/reference/api/pandas.DataFrame.merge.html
  why: Left-merge semantics for joining phase2_product_attrs_df onto df.
       on="product_id", how="left" — NULL launch_date stays NaN, no row
       duplication, no row drop.

- url: https://pandas.pydata.org/docs/reference/api/pandas.Series.dt.days.html
  why: (date - launch_date).dt.days produces integer-or-NaN. Use this
       BEFORE the shift, so NaN propagates correctly through the shift.

- url: https://pandas.pydata.org/docs/user_guide/integer_na.html
  why: pandas nullable Int64 vs float64+NaN. Either is acceptable for the
       output column; assertions use pd.isna(), not dtype equality.

- docfile: .agents/plans/phase2-decisions-and-prp-prep.md
  sections: §0 (DB-shape verified — no migration), §1 (continuous-only,
            NO categorical stage)
  why: Locks the "NO lifecycle_stage_*" decision. Reject any reviewer
       request to add the categorical here — it is a separate future PRP.

- docfile: .agents/plans/wire-phase2-features-to-featuresets.md
  sections: §6 (time-safety contract skeleton), §7.1 (lifecycle spec —
            post-decision shape), §11 (success criteria), §14 R1 (leakage)
  why: Parent PRD. §6's skeleton IS the shape of _compute_lifecycle_features.
       §7.1 lists the exact column-name convention `days_since_launch_lag{N}`.

- docfile: .agents/plans/initial-2-lifecycle-features.md
  why: The immediate input to this PRP. Read §FEATURE for column shapes,
       §EXAMPLES for line-number citations, §OTHER_CONSIDERATIONS for the
       test-first principle (leakage test ships in same PR as compute).

- file: .claude/rules/product-vision.md
  why: Principle 5 — time-safety in features is non-negotiable. Principle 4 —
       strict typing. Both are merge gates.

- file: .claude/rules/test-requirements.md
  why: test_leakage.py IS the spec; never weaken to make a feature pass.
       Backend new public method MUST have at least one happy-path test +
       leakage regression test for any time-safety-affecting code.

- file: .claude/rules/security-patterns.md
  why: Allow-lists over deny-lists (already enforced by Pydantic — no new
       work here). No raw SQL — if you choose in-method DB load (§15
       Decision A inverse), use SQLAlchemy 2.0 async select() only.
```

### Current Codebase tree (relevant subset, AFTER PRP-3.1A merges)

```bash
app/features/featuresets/
├── __init__.py
├── routes.py             # unchanged in this PRP
├── schemas.py            # PRP-3.1A landed LifecycleConfig + lifecycle_config field + "lifecycle" token
├── service.py            # +1 _compute_lifecycle_features method, +1 if-branch in compute_features
└── tests/
    ├── __init__.py
    ├── conftest.py       # PRP-3.1A landed phase2_product_attrs_df fixture
    ├── test_leakage.py   # +1 TestLifecycleLeakage class (load-bearing spec extension)
    ├── test_schemas.py   # unchanged in this PRP
    └── test_service.py   # +1 TestLifecycleFeatures class (compute method tests)

app/features/data_platform/
└── models.py             # READ ONLY — sources Product.launch_date / discontinue_date
```

### Desired Codebase tree (after this PR)

```bash
app/features/featuresets/
├── service.py            # +~70 LOC: 1 new method + 3-line branch in compute_features
└── tests/
    ├── test_leakage.py   # +~60 LOC: 1 new test class with ≥2 cases (per-series + group-isolation)
    └── test_service.py   # +~70 LOC: 1 new test class with ≥3 cases (happy path + NULL + discontinue-before-cutoff)
```

Net diff target: **≤ 200 LOC** (additions only; zero modifications to pre-existing logic).

### Known Gotchas & Library Quirks

```python
# CRITICAL: PRP-3.1A landed LifecycleConfig as a frozen Pydantic v2 model.
#   Use `self.config.lifecycle_config.include_days_since_launch`, etc. — never
#   mutate the config object. mypy --strict + pyright --strict catch mutation.

# CRITICAL: The compute_features() driver (service.py:75-162) sorts the df by
#   [*entity_cols, date_col] at line 103 and filters by cutoff at lines 106-108
#   BEFORE branching into _compute_* methods. Our method MUST assume df is
#   already sorted and cutoff-filtered. Do NOT sort or re-filter — that's a
#   regression vs. the existing pattern.

# CRITICAL: `df.groupby(self.entity_cols, observed=True)[col].shift(lag_days)`
#   is the canonical pattern. observed=True matters when entity columns are
#   pandas Categorical (defensive — current fixtures are int, but the codebase
#   uses observed=True consistently — see service.py:186, 230, 329, 338, 347).

# CRITICAL: phase2_product_attrs_df contains pd.NaT (for missing dates) and
#   date objects. After a left-merge onto df, the column dtype may be
#   object-typed (mixed date+NaT). Convert with pd.to_datetime(...) BEFORE
#   subtracting to get a datetime64[ns] series that supports `.dt.days`.

# CRITICAL: Day-deltas with NaT propagate correctly:
#     (pd.to_datetime(df["date"]) - pd.to_datetime(df["launch_date"])).dt.days
#   produces float64 with NaN where launch_date is NaT — NO exception, NO
#   silent zero. Tests must assert pd.isna() on those rows.

# CRITICAL: The shift comes AFTER the date-delta, not before. The delta is a
#   pure function of (date, launch_date) at row i — no past-data dependency.
#   The leakage prevention comes from the shift(lag_days), which guarantees
#   the column value at row i reflects the delta computed AT ROW i-lag_days.
#   This is subtly different from lag features over `quantity`, where the
#   value itself is the past observation. Document this in the docstring.

# CRITICAL: discontinue_date is signed per INITIAL §FEATURE bullet 3.
#   For a product launched 2024-01-01 and discontinued 2024-06-01:
#     row date=2024-03-01 → days_since_discontinue = -92 (still pre-retire)
#     row date=2024-08-01 → days_since_discontinue = +61 (post-retire)
#   Do NOT clip to >= 0. LightGBM learns the sign.

# CRITICAL: Column-name format string: f"days_since_launch_lag{lag_days}" —
#   matches the PRD §7.1 convention. NOT `days_since_launch_lag_1` (no
#   underscore between lag and digit). Mirror the exogenous `price_lag_{lag}`
#   pattern at service.py:381 if in doubt — note exogenous uses underscore;
#   re-read the PRD §7.1 to confirm. PRD §7.1 row 1 shows `days_since_intro_lag{N}`
#   (no underscore). Resolved: use `days_since_launch_lag{N}` — no underscore.

# GOTCHA: pandas merge on (store_id, product_id, date) is tempting but
#   phase2_product_attrs_df is keyed on product_id only (lifecycle dates are
#   per-product, not per-store-product). Merge ONLY on product_id. Tests
#   that mix multiple stores per product MUST observe the same lifecycle
#   delta for both stores at the same date.

# GOTCHA: The product-attrs join doubles the column footprint of df. If a
#   caller has already merged launch_date / discontinue_date in (e.g., via
#   the loader extension in §15 Decision A), the merge would collide. Pattern:
#   check `"launch_date" in df.columns`; if absent, raise a clear error
#   "product attrs not joined — see PRP-3.1B §15 Decision A". This makes the
#   caller-contract explicit instead of failing with a cryptic KeyError.

# GOTCHA: mypy --strict on `pd.Series.dt.days` returns `pd.Series[float]`,
#   not `pd.Series[int]`, even when the input is non-null. Type the local as
#   `pd.Series[float]` or `Any` — do NOT annotate as `pd.Series[int]`.

# GOTCHA: pyright --strict on `result[col_name] = df.groupby(...).shift(lag)`
#   reports `reportUnknownMemberType` if the chain returns `Any`. Mitigate
#   with `# type: ignore[no-any-return]` only if mypy is happy. Otherwise
#   intermediate-assign to a typed local first (mirrors the codebase — see
#   service.py:382 which assigns directly without ignore).

# GOTCHA: `_compute_exogenous_features` (service.py:379-385) conditionally
#   skips work if the source column is absent (`if config.include_price and
#   "unit_price" in df.columns:`). Replicate this defensive pattern for
#   launch_date / discontinue_date — if the product-attrs join didn't happen
#   upstream, emit NO columns and (optionally) log a single info-level event.
#   Do NOT raise — the caller may have set lifecycle_config without joining
#   attrs (e.g., the existing /featuresets/compute endpoint, which loads
#   sales_daily but no product attrs). Logging the skip surfaces the gap
#   without breaking pre-existing tests.

# GOTCHA: The existing /featuresets/compute endpoint (routes.py) does NOT
#   join product attrs. After this PRP merges, a caller setting
#   lifecycle_config will get the family token in `enabled_features` but
#   ZERO lifecycle columns in `feature_columns`. The end-to-end wiring
#   (loader-extension to merge product attrs into the response DataFrame)
#   is OUT OF SCOPE for this PRP — it belongs in PRP-3.1E. The compute
#   method MUST be defensive about the missing columns and log a
#   single "lifecycle_config set but product attrs not joined" line.

# GOTCHA: AI co-author trailer is forbidden per .claude/rules/commit-format.md.
#   Do NOT add `Co-Authored-By: Claude ...` or `🤖 Generated with [Claude Code]`
#   to the commit message. The hook .claude/hooks/check-commit-format.sh
#   rejects them.
```

---

## Implementation Blueprint

### The compute method

```python
# app/features/featuresets/service.py — additions only
# Insert AFTER `_compute_exogenous_features` (which ends at line 404),
# BEFORE `class FeatureDataLoader` (starts at line 407).

    def _compute_lifecycle_features(
        self, df: pd.DataFrame
    ) -> tuple[pd.DataFrame, list[str]]:
        """Compute product-lifecycle features from launch/discontinue dates.

        CRITICAL: This method assumes ``df`` has already been sorted by
        [*entity_cols, date_col] and cutoff-filtered upstream in
        :meth:`compute_features`. It does NOT re-sort or re-filter.

        The compute is two-step:
          1. Per-row date deltas: ``date - launch_date`` (int days, NaN-safe)
          2. Lagged by ``config.lag_days`` per ``(store_id, product_id)`` to
             ensure the value at row ``i`` reflects only data at row ``i - lag_days``.

        Source columns (must be joined upstream — typically by an extended
        FeatureDataLoader; see PRP-3.1E):
          * ``launch_date`` — ``datetime.date | NaT`` per product
          * ``discontinue_date`` — ``datetime.date | NaT`` per product

        Defensive behavior: if the source columns are absent (the legacy
        ``/featuresets/compute`` endpoint does not join product attrs), emit
        zero columns and a single info-level log line. This preserves the
        additive-contract invariant: callers who set ``lifecycle_config`` but
        don't join attrs see ``"lifecycle"`` in ``enabled_features`` but no
        new columns in ``feature_columns``. The end-to-end wiring lands in
        PRP-3.1E.

        Args:
            df: Input dataframe (already sorted + cutoff-filtered).

        Returns:
            Tuple of ``(dataframe with lifecycle features, list of new column names)``.
        """
        config = self.config.lifecycle_config
        if config is None:
            raise RuntimeError(
                "_compute_lifecycle_features called without lifecycle_config"
            )

        result = df.copy()
        columns: list[str] = []
        lag = config.lag_days

        # Defensive: skip silently if product attrs were not joined.
        if "launch_date" not in df.columns and "discontinue_date" not in df.columns:
            logger.info(
                "featureops.lifecycle_skipped_no_product_attrs",
                reason="launch_date / discontinue_date columns absent from input df",
                hint="loader must join product.launch_date / discontinue_date "
                "before calling compute_features (see PRP-3.1E)",
            )
            return result, columns

        date_series = pd.to_datetime(result[self.date_col])

        if config.include_days_since_launch and "launch_date" in df.columns:
            launch = pd.to_datetime(result["launch_date"])
            # Pre-shift delta: int days where both dates set, NaN otherwise.
            delta_launch = (date_series - launch).dt.days
            # Lag per (store_id, product_id) so row i reflects row i-lag's delta.
            col_name = f"days_since_launch_lag{lag}"
            result[col_name] = (
                delta_launch.groupby(
                    [result[c] for c in self.entity_cols], observed=True
                ).shift(lag)
            )
            columns.append(col_name)

        if (
            config.include_days_since_discontinue
            and "discontinue_date" in df.columns
        ):
            discontinue = pd.to_datetime(result["discontinue_date"])
            # Signed delta: negative pre-retire, positive post-retire, NaN if NULL.
            delta_discontinue = (date_series - discontinue).dt.days
            col_name = f"days_since_discontinue_lag{lag}"
            result[col_name] = (
                delta_discontinue.groupby(
                    [result[c] for c in self.entity_cols], observed=True
                ).shift(lag)
            )
            columns.append(col_name)

        return result, columns
```

### `compute_features` wiring

```python
# app/features/featuresets/service.py — single 3-line insertion AFTER line 134,
# BEFORE the stats block at line 136. Exact pattern mirror of the exogenous block.

        # 5. Exogenous features
        if self.config.exogenous_config:
            result, cols = self._compute_exogenous_features(result)
            feature_columns.extend(cols)

        # 6. Lifecycle features (PRP-3.1B — Phase 2)
        if self.config.lifecycle_config:
            result, cols = self._compute_lifecycle_features(result)
            feature_columns.extend(cols)

        # Compute stats
        # ... (unchanged below this line)
```

### Leakage test (test-first per INITIAL)

```python
# app/features/featuresets/tests/test_leakage.py — APPEND new class
# AFTER TestEdgeCaseLeakage (the last class, ending at line 329).

class TestLifecycleLeakage:
    """CRITICAL: Lifecycle features must never use future data."""

    def test_days_since_launch_lag1_no_future_leakage(
        self, sample_time_series: pd.DataFrame
    ) -> None:
        """With a known launch_date and sequential dates, the lagged column
        at row i must equal (date[i-1] - launch_date).days exactly.

        sample_time_series has 30 sequential days starting 2024-01-01 for
        (store=1, product=1). With launch_date=2023-12-25, the per-row
        days-since-launch is 7,8,9,...,36; after shift(1), the lagged column
        at row i is the value at row i-1: NaN at row 0, 7 at row 1, 8 at row 2,
        ...  Any other integer is leakage.
        """
        from datetime import date as date_t
        from app.features.featuresets.schemas import (
            FeatureSetConfig,
            LifecycleConfig,
        )
        from app.features.featuresets.service import FeatureEngineeringService

        df = sample_time_series.copy()
        df["launch_date"] = date_t(2023, 12, 25)
        df["discontinue_date"] = pd.NaT

        config = FeatureSetConfig(
            name="test_lifecycle_leakage",
            lifecycle_config=LifecycleConfig(
                include_days_since_launch=True,
                include_days_since_discontinue=False,
                lag_days=1,
            ),
        )
        service = FeatureEngineeringService(config)
        result = service.compute_features(df)

        col = "days_since_launch_lag1"
        assert col in result.feature_columns, (
            f"missing column {col} — wiring regression"
        )

        # Row 0: NaN (no prior row to lag from)
        assert pd.isna(result.df.iloc[0][col]), (
            f"row 0 must be NaN (no history), got {result.df.iloc[0][col]}"
        )

        # Rows 1..29: exactly (i - 1) + 7 days since launch
        # (date[0] is 2024-01-01 → 7 days since 2023-12-25)
        for i in range(1, len(result.df)):
            expected = (i - 1) + 7
            actual = result.df.iloc[i][col]
            assert actual == expected, (
                f"LEAKAGE DETECTED at row {i}: {col}={actual} != expected={expected}. "
                "Lifecycle feature must reflect data at row i - lag_days only."
            )

    def test_lifecycle_group_isolation_no_cross_product_leakage(
        self, multi_series_time_series: pd.DataFrame
    ) -> None:
        """Two products with different launch_dates must produce independently
        correct columns — no cross-series contamination via groupby boundary."""
        from datetime import date as date_t
        from app.features.featuresets.schemas import (
            FeatureSetConfig,
            LifecycleConfig,
        )
        from app.features.featuresets.service import FeatureEngineeringService

        df = multi_series_time_series.copy()
        # Product 1 launched 2023-12-01 (32 days before 2024-01-01)
        # Product 2 launched 2023-12-25 (7 days before 2024-01-01)
        launch_map = {1: date_t(2023, 12, 1), 2: date_t(2023, 12, 25)}
        df["launch_date"] = df["product_id"].map(launch_map)
        df["discontinue_date"] = pd.NaT

        config = FeatureSetConfig(
            name="test_lifecycle_isolation",
            entity_columns=("store_id", "product_id"),
            lifecycle_config=LifecycleConfig(
                include_days_since_launch=True,
                include_days_since_discontinue=False,
                lag_days=1,
            ),
        )
        service = FeatureEngineeringService(config)
        result = service.compute_features(df)

        for store_id in (1, 2):
            for product_id, base_lag in ((1, 32), (2, 7)):
                series = result.df[
                    (result.df["store_id"] == store_id)
                    & (result.df["product_id"] == product_id)
                ].reset_index(drop=True)
                # Row 0: NaN
                assert pd.isna(series.iloc[0]["days_since_launch_lag1"]), (
                    f"({store_id},{product_id}) row 0 must be NaN"
                )
                # Row 1: base_lag (date[0] - launch_date).days
                actual = series.iloc[1]["days_since_launch_lag1"]
                assert actual == base_lag, (
                    f"CROSS-PRODUCT LEAKAGE: ({store_id},{product_id}) row 1: "
                    f"days_since_launch_lag1={actual}, expected={base_lag}. "
                    "Lifecycle lag is mixing across products."
                )
```

### Unit tests for the compute method

```python
# app/features/featuresets/tests/test_service.py — APPEND new class
# AFTER TestComputeFeatures (the last class, ending around line 319).

class TestLifecycleFeatures:
    """Tests for _compute_lifecycle_features (PRP-3.1B)."""

    def test_compute_lifecycle_happy_path(
        self, sample_time_series: pd.DataFrame
    ) -> None:
        """Happy path: launch_date and discontinue_date both set; produces
        both lagged columns with expected integer values."""
        from datetime import date as date_t
        from app.features.featuresets.schemas import (
            FeatureSetConfig,
            LifecycleConfig,
        )
        from app.features.featuresets.service import FeatureEngineeringService

        df = sample_time_series.copy()
        df["launch_date"] = date_t(2024, 1, 1)   # delta starts at 0
        df["discontinue_date"] = date_t(2024, 1, 15)  # signed crossover

        config = FeatureSetConfig(
            name="lc_happy",
            lifecycle_config=LifecycleConfig(
                include_days_since_launch=True,
                include_days_since_discontinue=True,
                lag_days=1,
            ),
        )
        service = FeatureEngineeringService(config)
        result = service.compute_features(df)

        assert "days_since_launch_lag1" in result.feature_columns
        assert "days_since_discontinue_lag1" in result.feature_columns

        # Row 1 (date=2024-01-02): lag1 reflects row 0 (date=2024-01-01)
        # days_since_launch at row 0 = 0; days_since_discontinue at row 0 = -14
        assert result.df.iloc[1]["days_since_launch_lag1"] == 0
        assert result.df.iloc[1]["days_since_discontinue_lag1"] == -14

        # Row 16 (date=2024-01-17): lag1 reflects row 15 (date=2024-01-16)
        # days_since_launch at row 15 = 15; days_since_discontinue at row 15 = +1
        assert result.df.iloc[16]["days_since_launch_lag1"] == 15
        assert result.df.iloc[16]["days_since_discontinue_lag1"] == 1

    def test_compute_lifecycle_null_launch_date(
        self, sample_time_series: pd.DataFrame
    ) -> None:
        """NULL launch_date → all-NaN lifecycle column, no exception."""
        from app.features.featuresets.schemas import (
            FeatureSetConfig,
            LifecycleConfig,
        )
        from app.features.featuresets.service import FeatureEngineeringService

        df = sample_time_series.copy()
        df["launch_date"] = pd.NaT
        df["discontinue_date"] = pd.NaT

        config = FeatureSetConfig(
            name="lc_null",
            lifecycle_config=LifecycleConfig(
                include_days_since_launch=True,
                include_days_since_discontinue=False,
                lag_days=1,
            ),
        )
        service = FeatureEngineeringService(config)
        result = service.compute_features(df)

        col = "days_since_launch_lag1"
        assert col in result.feature_columns
        assert result.df[col].isna().all(), (
            "NULL launch_date must produce all-NaN column"
        )

    def test_compute_lifecycle_discontinue_before_cutoff(
        self, sample_time_series: pd.DataFrame
    ) -> None:
        """discontinue_date before all rows → positive integer for every row."""
        from datetime import date as date_t
        from app.features.featuresets.schemas import (
            FeatureSetConfig,
            LifecycleConfig,
        )
        from app.features.featuresets.service import FeatureEngineeringService

        df = sample_time_series.copy()
        df["launch_date"] = date_t(2023, 1, 1)
        df["discontinue_date"] = date_t(2023, 12, 25)  # 7 days before row 0

        config = FeatureSetConfig(
            name="lc_post_discontinue",
            lifecycle_config=LifecycleConfig(
                include_days_since_launch=False,
                include_days_since_discontinue=True,
                lag_days=1,
            ),
        )
        service = FeatureEngineeringService(config)
        result = service.compute_features(df)

        # Row 1: lag1 reflects row 0 → date=2024-01-01 - discontinue=2023-12-25 = +7
        assert result.df.iloc[1]["days_since_discontinue_lag1"] == 7
        # Row 8: lag1 reflects row 7 → 2024-01-08 - 2023-12-25 = +14
        assert result.df.iloc[8]["days_since_discontinue_lag1"] == 14
        # All non-NaN values must be >= 0 (discontinue is in the past)
        non_na = result.df["days_since_discontinue_lag1"].dropna()
        assert (non_na >= 0).all(), (
            "with discontinue in the past, all lagged values must be >= 0"
        )

    def test_compute_lifecycle_skipped_when_attrs_absent(
        self, sample_time_series: pd.DataFrame
    ) -> None:
        """Defensive: missing product-attrs columns → zero new columns, no crash.

        This is the contract for the legacy /featuresets/compute path; PRP-3.1E
        adds the loader extension that joins product attrs.
        """
        from app.features.featuresets.schemas import (
            FeatureSetConfig,
            LifecycleConfig,
        )
        from app.features.featuresets.service import FeatureEngineeringService

        # sample_time_series has NO launch_date / discontinue_date columns.
        config = FeatureSetConfig(
            name="lc_no_attrs",
            lifecycle_config=LifecycleConfig(),
        )
        service = FeatureEngineeringService(config)
        result = service.compute_features(sample_time_series)

        assert "days_since_launch_lag1" not in result.feature_columns
        assert "days_since_discontinue_lag1" not in result.feature_columns
        # The family token still appears via get_enabled_features (set in PRP-3.1A).
        assert "lifecycle" in config.get_enabled_features()

    def test_compute_lifecycle_uses_phase2_fixture(
        self,
        sample_time_series: pd.DataFrame,
        phase2_product_attrs_df: pd.DataFrame,
    ) -> None:
        """End-to-end merge with the PRP-3.1A fixture: P1 launched 2023-06-01."""
        from app.features.featuresets.schemas import (
            FeatureSetConfig,
            LifecycleConfig,
        )
        from app.features.featuresets.service import FeatureEngineeringService

        df = sample_time_series.merge(
            phase2_product_attrs_df, on="product_id", how="left"
        )
        config = FeatureSetConfig(
            name="lc_phase2_fixture",
            lifecycle_config=LifecycleConfig(lag_days=1),
        )
        service = FeatureEngineeringService(config)
        result = service.compute_features(df)

        # P1 launched 2023-06-01; 2024-01-01 is 214 days after
        # → row 1 (date=2024-01-02, lag1 reflects row 0) = 214
        from datetime import date as date_t
        expected = (date_t(2024, 1, 1) - date_t(2023, 6, 1)).days
        assert result.df.iloc[1]["days_since_launch_lag1"] == expected
```

### List of tasks (in execution order)

```yaml
Task 1 — Write the leakage test FIRST (per INITIAL §OTHER_CONSIDERATIONS):
MODIFY app/features/featuresets/tests/test_leakage.py:
  - FIND pattern: "class TestEdgeCaseLeakage:" (the last class — around line 289)
  - APPEND new class TestLifecycleLeakage AFTER its closing block.
  - Include ≥2 cases:
      * test_days_since_launch_lag1_no_future_leakage (sequential-date detector)
      * test_lifecycle_group_isolation_no_cross_product_leakage (per-product
        launch dates; multi_series_time_series fixture from existing conftest)
  - MIRROR rejection-message format from TestLagLeakage at line 42-45 — "LEAKAGE
    DETECTED at row {i}: ... Lifecycle feature must reflect ..."
  - The test MUST FAIL at this point (the compute method does not yet exist) —
    this is the test-first discipline. Capture the failure (red).

Task 2 — Implement _compute_lifecycle_features:
MODIFY app/features/featuresets/service.py:
  - FIND pattern: end of `_compute_exogenous_features` (line 404, the
    `return result, columns` of that method).
  - INSERT new method AFTER that return, BEFORE `class FeatureDataLoader`
    at line 407.
  - Body per the Implementation Blueprint above:
      * `config is None` guard (raise RuntimeError — mirrors line 372)
      * `result = df.copy()` + `columns: list[str] = []`
      * Defensive skip when product-attrs columns absent (log + return)
      * Per-row date deltas via pd.to_datetime + .dt.days
      * Per-(store_id, product_id) shift(lag_days) via groupby
      * Column-name format: f"days_since_launch_lag{lag}" — NO underscore
        between "lag" and the digit (matches PRD §7.1)

Task 3 — Wire the branch into compute_features:
MODIFY app/features/featuresets/service.py:
  - FIND pattern: the exogenous branch at lines 132-134:
        if self.config.exogenous_config:
            result, cols = self._compute_exogenous_features(result)
            feature_columns.extend(cols)
  - INSERT a clone immediately AFTER line 134, BEFORE the `# Compute stats`
    comment at line 136:
        # 6. Lifecycle features (PRP-3.1B — Phase 2)
        if self.config.lifecycle_config:
            result, cols = self._compute_lifecycle_features(result)
            feature_columns.extend(cols)
  - PRESERVE every byte of pre-existing code above line 134 and below line 136.

Task 4 — Confirm the leakage test now passes (test-first turns green):
RUN:
  uv run pytest app/features/featuresets/tests/test_leakage.py::TestLifecycleLeakage -v
  # Expected: 2 passed.

Task 5 — Add unit tests for the compute method:
MODIFY app/features/featuresets/tests/test_service.py:
  - FIND pattern: the LAST class `TestComputeFeatures` (around line 277).
  - APPEND new class TestLifecycleFeatures AFTER its closing block.
  - Include ≥4 cases:
      * test_compute_lifecycle_happy_path (both columns; both flags True)
      * test_compute_lifecycle_null_launch_date (all-NaN; no crash)
      * test_compute_lifecycle_discontinue_before_cutoff (signed positive)
      * test_compute_lifecycle_skipped_when_attrs_absent (defensive skip)
      * test_compute_lifecycle_uses_phase2_fixture (canonical PRP-3.1A fixture)
  - MIRROR style from TestLagFeatures (line 18-82) — no class-level setup,
    fixtures injected via signature.

Task 6 — Validation gates (run in order, fix any failures BEFORE proceeding):
RUN:
  uv run ruff check app/features/featuresets/ --fix
  uv run ruff format --check app/features/featuresets/
  uv run mypy app/features/featuresets/service.py
  uv run pyright app/features/featuresets/service.py
  uv run pytest app/features/featuresets/tests/test_leakage.py -v
  uv run pytest app/features/featuresets/tests/test_service.py -v
  uv run pytest app/features/featuresets/ -v   # full module regression
```

### Per-task pseudocode (only where non-obvious)

```python
# Task 2 — the groupby-on-derived-Series idiom is the only non-trivial line.
# pandas accepts a LIST of grouper Series; we pass result[c] for each entity
# col so the groupby key is sourced from `result` (post-merge attrs included).
# Equivalent to: result.groupby(self.entity_cols)[col].shift(lag) — but
# expressed over the derived Series `delta_launch` (which is not a column
# in `result`). The list-of-Series form is what's documented at
# https://pandas.pydata.org/docs/reference/api/pandas.Series.groupby.html

delta_launch = (date_series - launch).dt.days
lagged = delta_launch.groupby(
    [result[c] for c in self.entity_cols], observed=True
).shift(lag)
result[col_name] = lagged

# WHY this works: groupby keys come from `result` (same length as df), the
# series being shifted is `delta_launch` (same length as df). pandas pairs
# them by positional index. observed=True is defensive for Categorical.

# Alternative shape that ALSO works (and is closer to the exogenous pattern):
#   result["_tmp_launch_delta"] = (date_series - launch).dt.days
#   result[col_name] = result.groupby(
#       self.entity_cols, observed=True
#   )["_tmp_launch_delta"].shift(lag)
#   result.drop(columns=["_tmp_launch_delta"], inplace=True)
# Pick whichever the implementer finds more readable; both satisfy the
# leakage test. Prefer the no-temp-column form (less mutation).
```

### Integration Points

```yaml
DATABASE:
  - NO migration required. Verified — all Phase 2 columns exist in
    a8b9c0d1e234_add_retail_depth_columns_and_replenishment_event_table.py
    and `product.launch_date` / `product.discontinue_date` are nullable
    Date columns (models.py:101-102).

CONFIG:
  - NO new env vars. No knobs in app/core/config.py. All lifecycle
    parameters live on LifecycleConfig (PRP-3.1A).

ROUTES:
  - NO changes to app/features/featuresets/routes.py. The request body
    is unchanged from PRP-3.1A; this PRP only changes service behavior.

DOCS:
  - NO docs touched in this slice. PRP-3.1E updates
    docs/PHASE/3-FEATURE_ENGINEERING.md and DOMAIN_MODEL.md after all
    three compute methods (3.1B/C/D) land.

ALEMBIC:
  - NO new revision.

LOADER EXTENSION (deferred to PRP-3.1E):
  - The existing FeatureDataLoader (service.py:407-471) loads sales_daily
    but NOT product attrs. PRP-3.1E extends it to JOIN
    product.launch_date / product.discontinue_date when
    config.lifecycle_config is set. THIS PRP relies on the defensive-skip
    branch when attrs are absent — that's the contract until PRP-3.1E.

DOWNSTREAM PRPs:
  - PRP-3.1C (replenishment compute) — independent of this slice; no
    merge-conflict surface.
  - PRP-3.1D (promotion compute) — independent; no merge-conflict surface.
  - PRP-3.1E (E2E + docs) — depends on this PRP. Extends FeatureDataLoader
    to join product attrs and updates docs/PHASE/3 + DOMAIN_MODEL.md.
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

# Expected: 0 errors on each. Common failure modes:
#   - mypy "Incompatible types in assignment" on the groupby-shift chain:
#       fall back to the intermediate-typed-local form (see Per-task pseudocode).
#   - pyright "reportUnknownMemberType" on (date_series - launch).dt.days:
#       cast intermediate to `pd.Series[Any]` if pyright can't narrow.
#   - pyright "reportUnusedVariable" on the discarded `_tmp_launch_delta`:
#       use the no-temp-column form instead.
```

### Level 3: Unit Tests (new compute + existing regressions)

```bash
# Tests for the new compute method only (must be green):
uv run pytest app/features/featuresets/tests/test_service.py::TestLifecycleFeatures -v

# Leakage spec (must be green):
uv run pytest app/features/featuresets/tests/test_leakage.py::TestLifecycleLeakage -v

# Full module sweep — 0 regressions in pre-existing tests:
uv run pytest app/features/featuresets/ -v

# Convenient combined filter (mirrors the INITIAL §commit-message validation):
uv run pytest app/features/featuresets/tests/test_leakage.py \
              app/features/featuresets/tests/test_service.py -v -k lifecycle
# Expected: all lifecycle-named tests green; nothing else touched.
```

### Level 4: Leakage proof (manual eyeballing of the test output)

```bash
# Print the deltas to confirm the lag arithmetic with a known-good fixture:
uv run python -c "
import pandas as pd
from datetime import date
from app.features.featuresets.schemas import FeatureSetConfig, LifecycleConfig
from app.features.featuresets.service import FeatureEngineeringService

dates = pd.date_range('2024-01-01', periods=30, freq='D')
df = pd.DataFrame({
    'date': dates,
    'store_id': [1]*30,
    'product_id': [1]*30,
    'quantity': list(range(1, 31)),
    'unit_price': [10.0]*30,
    'total_amount': [q*10.0 for q in range(1, 31)],
    'launch_date': [date(2023, 12, 25)]*30,
    'discontinue_date': [pd.NaT]*30,
})

config = FeatureSetConfig(
    name='leakage_eyeball',
    lifecycle_config=LifecycleConfig(lag_days=1, include_days_since_discontinue=False),
)
result = FeatureEngineeringService(config).compute_features(df)
print(result.df[['date','days_since_launch_lag1']].head(10))
"
# Expected:
#         date  days_since_launch_lag1
# 0 2024-01-01                     NaN
# 1 2024-01-02                     7.0
# 2 2024-01-03                     8.0
# 3 2024-01-04                     9.0
# ...
# Any other shape == leakage; STOP and diagnose.
```

### Level 5: HTTP smoke (FastAPI boundary — additive contract)

```bash
# Start the API:
docker compose up -d
uv run alembic upgrade head
uv run uvicorn app.main:app --reload --port 8123 &
APP_PID=$!
sleep 2

# Pre-PR caller (no lifecycle_config) — must be byte-identical to dev:
curl -s -X POST http://localhost:8123/featuresets/compute \
  -H "Content-Type: application/json" \
  -d '{
    "store_id":1,"product_id":1,
    "cutoff_date":"2024-01-31",
    "config":{"name":"smoke-pre"}
  }' | jq '.config_hash, .feature_columns'
# Expected: hash + columns identical to `dev` HEAD (same request).

# New caller (lifecycle_config set, attrs not joined — defensive skip):
curl -s -X POST http://localhost:8123/featuresets/compute \
  -H "Content-Type: application/json" \
  -d '{
    "store_id":1,"product_id":1,
    "cutoff_date":"2024-01-31",
    "config":{
      "name":"smoke-lc",
      "lifecycle_config":{"include_days_since_launch":true,"lag_days":1}
    }
  }' | jq '.feature_columns | length'
# Expected: same length as the pre-PR call — defensive skip emits zero
# lifecycle columns until PRP-3.1E wires the loader extension.
# Backend logs (uvicorn stdout) MUST contain:
#   featureops.lifecycle_skipped_no_product_attrs

# Invalid bound (Pydantic rejection from PRP-3.1A — must still return 422):
curl -s -X POST http://localhost:8123/featuresets/compute \
  -H "Content-Type: application/json" \
  -d '{
    "store_id":1,"product_id":1,"cutoff_date":"2024-01-31",
    "config":{"name":"bad","lifecycle_config":{"lag_days":0}}
  }' | jq '.title'
# Expected: "validation_error" (RFC 7807 problem+json)

kill $APP_PID
```

---

## Final Validation Checklist

- [ ] Leakage test class `TestLifecycleLeakage` exists in `tests/test_leakage.py` and ALL cases pass
- [ ] Unit test class `TestLifecycleFeatures` exists in `tests/test_service.py` and ALL ≥4 cases pass
- [ ] `uv run pytest app/features/featuresets/ -v` — 0 regressions in pre-existing tests (PRP-3.1A surface unchanged)
- [ ] `uv run ruff check app/features/featuresets/` — clean
- [ ] `uv run ruff format --check app/features/featuresets/` — clean
- [ ] `uv run mypy app/features/featuresets/service.py` — 0 errors
- [ ] `uv run pyright app/features/featuresets/service.py` — 0 errors
- [ ] No schema changes — `git diff dev... -- app/features/featuresets/schemas.py` → empty (PRP-3.1A is the only writer)
- [ ] No routes changes — `git diff dev... -- app/features/featuresets/routes.py` → empty
- [ ] No new migrations — `git diff dev... -- alembic/versions/` → empty
- [ ] Diff stat: ≤ +200 / -0 LOC (additions only) — verify with `git diff --stat dev...`
- [ ] Defensive-skip log line `featureops.lifecycle_skipped_no_product_attrs` emitted when product attrs are absent (HTTP smoke Level 5)
- [ ] Single commit, message: `feat(features): implement lifecycle compute method (#<issue>)`
- [ ] Commit references an open GitHub issue (resolve via `gh issue list --search "lifecycle"` or open one before committing)
- [ ] No AI co-author trailer in the commit message (`commit-format.md`)
- [ ] No PRP-3.1A re-writes — `git diff dev... -- app/features/featuresets/tests/conftest.py` → empty (fixtures land in PRP-3.1A; this PRP only consumes them)

---

## Anti-Patterns to Avoid

- ❌ **Do NOT add a categorical `lifecycle_stage_*` family.** Locked out by Decision 1 in `.agents/plans/phase2-decisions-and-prp-prep.md §1`. If a reviewer requests it, point them at the decisions log — it's a future PRP, not this one.
- ❌ **Do NOT modify `LifecycleConfig`.** Schema is locked by PRP-3.1A. Adding a new field here splits the contract across two PRs and breaks the parallel-execution premise.
- ❌ **Do NOT skip the leakage test.** It's the spec (per `.claude/rules/test-requirements.md` and PRD Principle 1). Write it FIRST, watch it fail, then implement the method.
- ❌ **Do NOT use `rolling()` then `shift(1)`.** That's leakage by construction. The lifecycle method doesn't use `rolling` at all — but if a future iteration adds one (e.g., "days since launch, rolling-mean over the last 7 cohorts"), it MUST be `shift(lag).rolling(...)` per the canonical pattern at `service.py:228`.
- ❌ **Do NOT raise on missing product-attrs columns.** Log and skip. The legacy `/featuresets/compute` path will hit this case until PRP-3.1E lands; raising here would break pre-existing callers who set `lifecycle_config` blindly.
- ❌ **Do NOT clip `days_since_discontinue` to >= 0.** The signed delta is the feature per INITIAL §FEATURE bullet 3 — LightGBM learns the sign.
- ❌ **Do NOT add an in-method async DB JOIN unless §15 Decision A is reversed.** That couples this PRP to the loader contract and breaks the "compute method is sync, pandas-only" pattern. The DB load extension belongs in PRP-3.1E.
- ❌ **Do NOT use `Optional[T]`.** Repo style is `T | None` (PEP 604) — same convention as `_compute_exogenous_features` at line 360.
- ❌ **Do NOT use `list[...]` for the column-name aggregator.** It is already `list[str]` per the existing pattern; that's correct. The hashable-tuple rule applies to model fields, NOT to return-value lists.
- ❌ **Do NOT edit `_compute_exogenous_features`** or any other existing `_compute_*` method. This PRP is purely additive.
- ❌ **Do NOT update docs/PHASE/3-FEATURE_ENGINEERING.md or DOMAIN_MODEL.md.** That's PRP-3.1E's surface; updating here causes merge-conflict churn between B/C/D and E.
- ❌ **Do NOT add an AI co-author trailer** (`Co-Authored-By: Claude <...>`, `🤖 Generated with [Claude Code]`) — forbidden by `.claude/rules/commit-format.md`. The `.claude/hooks/check-commit-format.sh` hook rejects them.
- ❌ **Do NOT push --force on `dev` or `main`.** Forbidden by `.claude/rules/security-patterns.md`.

---

## §15 — PRP-Authoring Decisions

These are decisions made during PRP authoring that the INITIAL didn't fully lock — recorded so a future session can audit the reasoning.

### Decision A — `_compute_lifecycle_features` assumes product attrs are pre-joined; in-method DB load is deferred to PRP-3.1E

**INITIAL said (line 38):** "The compute method must JOIN `product` on `product_id` to populate them into the per-row DataFrame before computing date deltas."
**My call:** The compute method does NOT issue a DB JOIN. It expects `launch_date` / `discontinue_date` to be columns on the input `df` (joined upstream by the caller — typically an extended `FeatureDataLoader`). When the columns are absent, it logs and emits zero columns (defensive skip).
**Why:**
1. `_compute_*` methods in `service.py` are synchronous and pandas-only — none of them touch the DB. `_compute_exogenous_features` (the canonical template) reads `unit_price` / `is_stockout` from `df.columns` defensively (line 379, 397) and emits no columns when absent. Forcing a DB JOIN inside `_compute_lifecycle_features` would break that invariant and force the method to be `async`, propagating async-ness up through `compute_features` and its callers.
2. The existing `FeatureDataLoader.load_sales_data` (line 413-471) is the ONLY DB-load path. Extending it to JOIN `Product` is small and natural, but landing it in this PRP doubles the diff and crosses into the PRP-3.1E surface (which already owns the E2E wiring + loader extension).
3. The defensive-skip path keeps `/featuresets/compute` byte-additive: a caller setting `lifecycle_config` without joining attrs gets the `"lifecycle"` token in `enabled_features` (already wired in PRP-3.1A) but zero lifecycle columns — no error, no regression.
**Trade-off:** PRP-3.1B alone produces no lifecycle columns over HTTP. PRP-3.1E will add the loader extension and the E2E smoke that proves columns flow to the response. This is acceptable because: (a) the leakage test + unit tests prove the COMPUTE behavior; (b) PRP-3.1C (replenishment) and PRP-3.1D (promotion) face the same "loader needs extending" problem and benefit from a single loader-extension PR in 3.1E rather than three duplicated extensions.
**If reversed:** Convert `_compute_lifecycle_features` to `async def`, accept an `AsyncSession` parameter, query `Product` filtered by `product_id IN (...)`, merge in-method. This duplicates work that 3.1C/D need anyway and forces the compute method shape to drift from the exogenous template. Not recommended.

### Decision B — Column-name format is `days_since_launch_lag{N}` (no underscore before digit)

**INITIAL said (line 13):** "`days_since_launch_lag{N}`"
**Exogenous pattern at `service.py:381`:** `f"price_lag_{lag}"` (WITH underscore).
**My call:** Use the INITIAL/PRD form — no underscore: `days_since_launch_lag1`, `days_since_launch_lag7`.
**Why:** The INITIAL is explicit and the PRD §7.1 row 1 uses the same convention (`days_since_intro_lag{N}` in the pre-decision PRD, renamed to `_launch` post-decision but preserving the no-underscore form). The exogenous-family lag column-names predate this convention; mixing styles is harmless but the new family is allowed to set its own convention as long as it's consistent.
**Risk:** A registry consumer that hardcodes `days_since_launch_lag_1` (with underscore) would miss this column. None exists today.

### Decision C — Defensive log key is `featureops.lifecycle_skipped_no_product_attrs`

**INITIAL said:** N/A — silent on logging.
**My call:** Log a single `info` line with that event key when the defensive skip fires.
**Why:** Matches the existing logging idiom (`featureops.compute_started`, `featureops.imputation_leakage_risk` — see `service.py:92, 332, 341`). Surfaces the "config set but no attrs joined" gap to operators without raising — which would break callers.
**If reversed:** Drop the log line. The leakage and unit tests still pass; only operational visibility regresses.

### Decision D — Unit tests live in `test_service.py`; leakage tests live in `test_leakage.py` (not bundled)

**INITIAL said (line 17-18):** Leakage case in `tests/test_leakage.py`; computation unit test in `tests/test_service.py`.
**My call:** Honor the split exactly as the INITIAL specifies — leakage cases go in `test_leakage.py`, computation cases go in `test_service.py`. Decision recorded here only to confirm I read the directive and did not silently merge the two files.
**Why:** `test_leakage.py` is the load-bearing spec (per `.claude/rules/test-requirements.md` and PRD Principle 1). Keeping leakage cases isolated makes audit easier — `audit-rules-drift` and any future "show me the leakage spec" tooling looks at one file.

---

## §16 — Open Questions for the Implementing Agent

None. All decisions resolved:

- DB shape — verified (`models.py:101-102`, `models.py:122-125`).
- Encoding (continuous-only) — locked by decisions log §1.
- Schema surface (`LifecycleConfig`) — locked by PRP-3.1A.
- Fixture (`phase2_product_attrs_df`) — locked by PRP-3.1A.
- Loader extension scope — deferred to PRP-3.1E (§15 Decision A).
- Column-name convention — pinned (§15 Decision B).
- Logging convention — pinned (§15 Decision C).
- Test-file split — pinned (§15 Decision D).

If a surprise emerges during implementation (e.g., `pyright --strict` chokes on the groupby-on-derived-Series form even with `# type: ignore`, or the diff exceeds 200 LOC because mypy demands explicit typing on every intermediate), STOP and ask before resolving. Do NOT quietly weaken the leakage test or skip the defensive-skip path.

---

## Confidence Score: 9 / 10

**Why 9, not 10:**

- ✅ Every file path and line number cited from the actual repo (verified via Read tool on `service.py`, `schemas.py`, `test_leakage.py`, `conftest.py`, `models.py`).
- ✅ The compute-method shape mirrors `_compute_exogenous_features` line-for-line — no new pattern invention.
- ✅ Leakage test design uses sequential dates as the mathematical detector — same idiom as `TestLagLeakage` at `test_leakage.py:23-76`.
- ✅ All five validation levels are deterministic and runnable as-written.
- ✅ The locked decisions log (continuous-only, no `lifecycle_stage`) is carried forward explicitly.
- ✅ Defensive-skip path keeps the additive-contract invariant intact even before PRP-3.1E lands the loader extension.
- ⚠️ The one residual risk: `pyright --strict` reaction to `(series - series).dt.days` on a derived intermediate may produce `reportUnknownMemberType` (pandas-stubs is imperfect on `.dt` accessors). Mitigation in Gotchas — fall back to an intermediate-typed local if needed. If pyright still complains, a 1-line `# pyright: ignore[reportUnknownMemberType]` on the offending line is acceptable but unwelcome; document the reason inline if used. This is a 5-minute fix, not a blocker.

Goal achieved: an implementing agent with no prior session context can read this PRP, read 4 source files (cited with line numbers), edit 3 files (service.py, test_leakage.py, test_service.py), run 6 commands, and ship a green PR with leakage proof.
