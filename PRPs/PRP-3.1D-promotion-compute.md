# PRP-3.1D: Promotion Compute Method (`_compute_promotion_features`)

**Feature**: `.agents/plans/initial-4-promotion-features.md`
**Parent PRP**: PRP-3.1 (umbrella — Phase 2 feature wiring; PRP-3.1A through PRP-3.1E are the 5 slices)
**Parent PRD**: `.agents/plans/wire-phase2-features-to-featuresets.md`
**Sibling (preceding)**: PRP-3.1A — schemas + fixtures (already landed; `PromotionConfig` lives at `app/features/featuresets/schemas.py:237-276`)
**Sibling (parallel-safe)**: PRP-3.1B (lifecycle), PRP-3.1C (replenishment)
**Status**: Ready for Implementation
**Confidence Score**: 9 / 10 — `PromotionConfig` already exists post-3.1A, the JOIN shape is the most complex of the four families but the date-range semantics are precisely specified, all DB columns verified (`discount_pct` resolved per handoff R7), and validation gates are fully deterministic. Single residual uncertainty: deterministic column-ordering choice (sorted vs input-order) — resolved in §15 "PRP-authoring decisions" with rationale.

---

## Goal

Land the **compute-method-only** slice for the promotion family. Given that PRP-3.1A delivered `PromotionConfig` plus the `phase2_promotion_rows_df` fixture, this PRP wires the pandas computation that consumes them:

1. Implement `FeatureEngineeringService._compute_promotion_features(df, promotion_rows_df) -> tuple[pd.DataFrame, list[str]]` in `app/features/featuresets/service.py`.
2. For each `kind` in `config.kinds_to_track`, emit:
   - `promo_<kind>_active_lag{N}` — int 0/1 (when `config.include_active`)
   - `promo_<kind>_intensity_lag{N}` — float, from `discount_pct` (when `config.include_intensity`). NULL discount → NaN.
3. Wire **one** new branch into `FeatureEngineeringService.compute_features()` — `if self.config.promotion_config:`, placed AFTER `exogenous_config` (mirrors PRP-3.1A field order).
4. Handle chain-wide promotions (`store_id IS NULL`) — a chain-wide row applies to all stores of that product.
5. Add leakage cases in `tests/test_leakage.py` proving: a promotion active on day D MUST NOT appear in day D's `promo_<kind>_active_lag1` (it appears at day D+1 only).
6. Add unit tests in `tests/test_service.py` covering: happy path, multiple kinds, chain-wide vs store-specific, NULL `discount_pct`, overlapping promotions on the same kind, promotion ending exactly on `cutoff_date`.
7. **NO schema changes. NO routes changes. NO new Alembic migration.**

End state — single commit, ≤ 300 LOC net diff, `mypy --strict` + `pyright --strict` clean, `pytest app/features/featuresets/tests/ -v -k promotion` green, full `pytest app/features/featuresets/ -v` shows no regression in pre-existing cases.

---

## Why

- **Closes the data-shape gap for the most operator-visible Phase 2 dimension.** Markdowns and percentage-off campaigns are the demo's marquee scenario; without this slice, toggling "Holiday Rush" in the seeder UI surfaces no observable change in any forecast feature column.
- **Validates the generic-promotion design from Decision 3.** PRP-3.1A locked `PromotionConfig` (rather than `MarkdownConfig`) as the contract. This slice proves the one-JOIN-per-promotion-table approach actually composes — by running for all four `kind` values via a single compute path, we avoid a rewrite when bundles/BOGO/pct_off need features later.
- **First feature method in the slice that does a cross-table JOIN with date-range semantics.** Lag/rolling/calendar/exogenous all operate on columns already present on `sales_daily`. Replenishment (PRP-3.1C) joins on event-date equality; promotion joins on a date-range (`start_date <= D <= end_date`). The leakage surface is genuinely new — every `.rolling()` or `.shift()` is preceded by a date-range filter at `D - lag_days`.
- **Preserves the additive-contract invariant.** No request-body changes, no response-shape changes beyond additive new columns; existing callers that omit `promotion_config` get byte-identical responses (snapshot guard inherited from PRP-3.1A).

---

## What

### User-visible behavior

- `POST /featuresets/compute` with `{"config": {"name": "x", "promotion_config": {"kinds_to_track": ["markdown"], "include_active": true, "include_intensity": true, "lag_days": 1}}}` returns a feature matrix that includes `promo_markdown_active_lag1` (int 0/1) and `promo_markdown_intensity_lag1` (float, NaN where no markdown was active on `D - 1`).
- Multi-kind: `kinds_to_track=["markdown","pct_off"]` produces four columns (active + intensity per kind).
- Chain-wide promotions (`promotion.store_id IS NULL`) apply to every store of that product.
- NULL `discount_pct` (the natural state for `bogo` / `bundle` rows per `models.py:306` + the `ck_promotion_bundle_members_consistency` CHECK at `models.py:337-341`) produces `NaN` in the intensity column. The active column is still `1`.
- Overlapping promotions on the same kind on the same `(store, product, date)` — intensity is the `max(discount_pct)` across overlaps (per `.agents/plans/initial-4-promotion-features.md:42` and decisions log §8 R8). Active is `1` (it's a 0/1 indicator).
- `get_enabled_features()` already includes `"promotion"` (delivered by PRP-3.1A); no change needed there.

### Success Criteria

- [ ] `_compute_promotion_features` exists on `FeatureEngineeringService` with signature `(self, df: pd.DataFrame, promotion_rows_df: pd.DataFrame) -> tuple[pd.DataFrame, list[str]]`.
- [ ] One new branch in `compute_features()` (`if self.config.promotion_config:`) located AFTER the existing exogenous branch at `service.py:132-134`.
- [ ] For `kinds_to_track=("markdown",)` with both `include_active=True` and `include_intensity=True` and default `lag_days=1`, the result contains exactly the columns `promo_markdown_active_lag1` and `promo_markdown_intensity_lag1` — no more, no less. (Plus any other configured-family columns.)
- [ ] Column ordering is deterministic: sorted ascending by `kind` first, then `active` before `intensity` (see §15 Decision A).
- [ ] Chain-wide rows (`store_id` NaN/None) apply to all stores of that product.
- [ ] Overlapping promotions on the same kind use `max(discount_pct)` for intensity (and `1` for active).
- [ ] At least 4 new leakage cases in `test_leakage.py`: (1) shift-invariance per `(store, product)`; (2) promotion ending exactly on `cutoff_date - 1` produces `active_lag1=1` at `cutoff_date`; (3) promotion starting exactly on `cutoff_date` is NOT in `active_lag1` at `cutoff_date` (would require `lag_days=0`); (4) chain-wide-promotion does not bleed across products.
- [ ] At least 6 new unit cases in `test_service.py`: happy path (single kind), multi-kind, chain-wide-vs-store-specific, NULL `discount_pct` (bogo with intensity → NaN), overlapping promotions (max aggregation), no-active-promotion period (all zeros + NaN intensity).
- [ ] `uv run pytest app/features/featuresets/tests/ -v -k promotion` → all green.
- [ ] `uv run pytest app/features/featuresets/ -v` → no regression vs pre-PR.
- [ ] `uv run ruff check app/features/featuresets/` → clean.
- [ ] `uv run mypy app/features/featuresets/service.py` → 0 errors.
- [ ] `uv run pyright app/features/featuresets/service.py` → 0 errors.
- [ ] Diff stat: ≤ +300 / -10 LOC (more kinds = more code; 4-kind × 2-column × N-lag matrix is the upper bound).

---

## All Needed Context

### Documentation & References

```yaml
# MUST READ before writing the compute method

- file: app/features/featuresets/service.py
  lines: 360-404
  why: _compute_exogenous_features is the canonical pattern to mirror.
       Signature shape (df -> tuple[df, list[str]]), use of self.entity_cols,
       use of groupby([store_id, product_id]).shift(lag). The intensity
       computation in particular borrows this idiom directly.

- file: app/features/featuresets/service.py
  lines: 75-162
  why: compute_features() — where the new branch lands. The exogenous block
       is at lines 132-134; promotion goes IMMEDIATELY AFTER it. Note that
       compute_features takes `cutoff_date` and applies it at line 106-108
       BEFORE any _compute_* call — the promotion method must respect this
       (it receives an already-cutoff-filtered df).

- file: app/features/featuresets/service.py
  lines: 164-193
  why: _compute_lag_features — shows the canonical
       `groupby(self.entity_cols, observed=True)[col].shift(lag)` pattern.
       Promotion compute uses the SAME entity grouping for its date-range
       indicator-then-shift.

- file: app/features/featuresets/service.py
  lines: 220-228
  why: The nested-function pattern used by _compute_rolling_features to
       avoid lambda-capture issues with shift/rolling. Not strictly needed
       for promotion (no rolling), but reference if pyright --strict
       complains about a lambda's inferred return type.

- file: app/features/featuresets/schemas.py
  lines: 237-276
  why: PromotionConfig — already exists (PRP-3.1A). Fields:
         * kinds_to_track: tuple[Literal["pct_off","bogo","bundle","markdown"], ...]
         * include_active: bool = True
         * include_intensity: bool = True
         * lag_days: int = Field(default=1, ge=1, le=30)
       Frozen, hashable, schema-versioned. Read this — your compute method
       reads these fields verbatim.

- file: app/features/featuresets/schemas.py
  lines: 305-360
  why: FeatureSetConfig (already includes promotion_config | None = None)
       and get_enabled_features() (already emits "promotion"). DO NOT EDIT
       this file in PRP-3.1D — PRP-3.1A landed both changes.

- file: app/features/featuresets/tests/conftest.py
  why: phase2_promotion_rows_df fixture (landed by PRP-3.1A) provides the
       input DataFrame. Shape: product_id, store_id (nullable for chain-wide),
       kind, discount_pct, start_date, end_date. Three rows mixing kinds
       (markdown + pct_off + bogo) to exercise the per-kind one-hot branch
       and the NULL-discount intensity case (bogo row has discount_pct=None).

- file: app/features/featuresets/tests/conftest.py
  lines: 17-60
  why: sample_time_series + multi_series_time_series — pure-pandas fixtures
       that promotion compute tests build on. Sequential `quantity` values
       (1..30) let leakage tests detect contamination mathematically.

- file: app/features/featuresets/tests/test_leakage.py
  lines: 23-77
  why: TestLagLeakage — the load-bearing leakage idiom. Mirror its assertion
       style for the new TestPromotionLeakage class. Sequential values +
       arithmetic-equality assertions are the project standard.

- file: app/features/featuresets/tests/test_leakage.py
  lines: 148-201
  why: TestCutoffLeakage — the boundary-date idiom. Promotion leakage tests
       construct a promotion that ENDS on cutoff_date - 1 to assert
       active_lag1 = 1 at cutoff (since "yesterday was still active").

- file: app/features/data_platform/models.py
  lines: 274-342
  why: Promotion table — VERIFIED column names. Key facts:
         * store_id is `Integer | None` (nullable, line 301-303) — chain-wide
         * kind ∈ {pct_off, bogo, bundle, markdown} (CHECK at line 333-336)
         * discount_pct Numeric(5, 4), 0..1 range, nullable (line 306)
         * start_date Date, indexed (line 315)
         * end_date Date (line 316)
         * ck_promotion_bundle_members_consistency forces bogo/bundle rows
           to have bundle_member_product_ids non-null, which is why the
           fixture's bogo row has discount_pct=None (Numeric(5,4) is the
           OTHER discount field; bogo uses bundle_member_product_ids for
           its mechanics, not a percentage discount).
         * Indexed by (product_id, start_date, end_date) — JOIN-friendly.

- file: alembic/versions/a8b9c0d1e234_add_retail_depth_columns_and_replenishment_event_table.py
  why: Migration that introduced `kind` + `discount_pct` + the CHECK
       constraints. Confirms NO new migration is needed for this PRP.

- file: app/features/featuresets/tests/test_service.py
  lines: 18-80
  why: TestLagFeatures — unit-test style template. Mirror this class
       structure for TestPromotionFeatures (same assertion idiom: explicit
       arithmetic expected values, no fuzzy matchers).

- url: https://pandas.pydata.org/docs/reference/api/pandas.DataFrame.merge.html
  why: Left-merge with multiple keys; how-to handle NULL on a merge key
       (chain-wide promotions). The merge for promotion compute is NOT
       a simple equi-join — it's a date-range expansion done in pandas
       (see Implementation Blueprint).

- url: https://pandas.pydata.org/docs/reference/api/pandas.Series.between.html
  why: `start_date <= D <= end_date` is the date-range predicate;
       `between(inclusive="both")` is the project-style idiom.

- url: https://pandas.pydata.org/docs/reference/api/pandas.DataFrame.groupby.html
  why: groupby + transform pattern used downstream of the
       per-kind indicator expansion. Mirrors _compute_exogenous at line 382.

- docfile: .agents/plans/initial-4-promotion-features.md
  why: The slice's INITIAL — locks scope and the "max(discount_pct)" choice
       for overlapping promotions (line 42).

- docfile: .agents/plans/phase2-decisions-and-prp-prep.md
  sections: §3 (PromotionConfig generalization — Decision 3), §8 R8
       (overlapping aggregation = `max`)
  why: Locked design choices that this PRP implements.

- docfile: .agents/plans/wire-phase2-features-to-featuresets.md
  sections: §6 (time-safety contract), §7.3 (original markdown spec —
       superseded but conceptually identical), §9 (security/config
       boundary), §11 (success criteria)
  why: Parent PRD — the "Pattern fidelity" principle (§6) governs the
       compute-method shape.

- file: .claude/rules/security-patterns.md
  why: Allow-lists over deny-lists (kinds_to_track already enforced at the
       Pydantic boundary). No raw SQL — promotion compute is in-memory
       pandas operating on the seeded fixture, with the DB JOIN performed
       at the API/service-layer boundary OUTSIDE this method (downstream
       wiring is PRP-3.1E's concern; this PRP takes promotion_rows_df as
       a pure-pandas input).

- file: .claude/rules/test-requirements.md
  why: Leakage cases are LOAD-BEARING. Add the leakage test BEFORE the
       compute method (test-first per PRD §6 Pattern fidelity row 5).

- file: .claude/rules/product-vision.md
  why: Principle 5 — Time-safe features only. The compute method's design
       must make leakage mathematically impossible at the row level, not
       just statistically unlikely.
```

### Current Codebase tree (relevant subset)

```bash
app/features/featuresets/
├── __init__.py
├── routes.py             # unchanged in this PRP
├── schemas.py            # READ-ONLY (PRP-3.1A landed PromotionConfig)
├── service.py            # +1 method, +1 branch in compute_features()
└── tests/
    ├── __init__.py
    ├── conftest.py       # READ-ONLY (PRP-3.1A landed phase2_promotion_rows_df)
    ├── test_leakage.py   # +1 class (TestPromotionLeakage, ≥ 4 cases)
    ├── test_schemas.py   # unchanged (PRP-3.1A covered schema tests)
    └── test_service.py   # +1 class (TestPromotionFeatures, ≥ 6 cases)

app/features/data_platform/
└── models.py             # READ-ONLY (Promotion table at lines 274-342)
```

### Desired Codebase tree (after this PR)

```bash
app/features/featuresets/
├── service.py            # +~120 LOC: _compute_promotion_features + 1 branch
└── tests/
    ├── test_leakage.py   # +~80 LOC: TestPromotionLeakage class (4-5 cases)
    └── test_service.py   # +~100 LOC: TestPromotionFeatures class (6-8 cases)
```

Net diff target: **≤ 300 LOC** (additions only; the existing exogenous block at `service.py:132-134` is the only edit point in `compute_features()`).

### Known Gotchas & Library Quirks

```python
# CRITICAL: compute_features() filters df by cutoff_date at service.py:106-108
#   BEFORE calling any _compute_* method. So the input `df` is already
#   restricted to date <= cutoff_date. The promotion_rows_df, however,
#   may include promotions that start AFTER cutoff — your compute method
#   MUST filter `promotion_rows_df` to rows where `start_date <= cutoff`.
#   The lag offset additionally restricts to `start_date <= D - lag_days`
#   per-row, so cutoff filtering is a coarse prefilter; per-row date-range
#   matching is the load-bearing check.

# CRITICAL: Date-range "active on day D" semantics are INCLUSIVE both sides.
#   active = (start_date <= D) & (D <= end_date)
#   The leakage test constructs end_date == cutoff_date - 1 and asserts
#   active_lag1 == 1 at row cutoff_date (because D - 1 == cutoff - 1 ==
#   end_date, which is inclusive).

# CRITICAL: store_id is `Integer | None` on Promotion (models.py:301).
#   In the input DataFrame, NULL stores arrive as pd.NA / None. A row with
#   store_id=None means "chain-wide" — it applies to EVERY store of that
#   product. Implementation must NOT do a naive equi-join on store_id;
#   instead, do a TWO-PASS match:
#     pass 1: store-specific overlap   — promo.store_id == row.store_id
#     pass 2: chain-wide overlap        — promo.store_id IS NULL
#   then union (OR) the active flags and take max() of the intensities.

# CRITICAL: discount_pct is NULLABLE in the seeder/DB (Numeric(5,4)).
#   For bogo / bundle rows, the value is naturally NULL because the
#   discount is encoded in bundle_member_product_ids, not as a percentage.
#   In the result DataFrame, this means:
#     promo_bogo_intensity_lag1 = NaN for rows where the only matching
#       promo is a bogo with discount_pct=None
#     promo_bogo_active_lag1   = 1 (it's still an indicator)
#   pandas.Series with NULL discount_pct will be dtype float64 with NaN,
#   not pd.NA — use `.fillna(np.nan)` if needed to normalize. Never
#   coerce NaN to 0 in intensity (would corrupt the signal for downstream
#   imputation strategies).

# CRITICAL: `df` is sorted by [store_id, product_id, date] at
#   service.py:103. The shift(lag_days) in promotion compute relies on
#   THIS ordering. Re-sort defensively at method entry to match the
#   exogenous compute idiom (mirror _compute_exogenous_features which
#   relies on the same invariant — it does NOT re-sort because
#   compute_features pre-sorts; promotion compute does the SAME).

# CRITICAL: Use `groupby(self.entity_cols, observed=True)` — the
#   `observed=True` matters when entity columns are categorical.
#   Mirror service.py:186 idiom EXACTLY. Without `observed=True`,
#   pyright --strict and certain pandas 3.x edge cases produce
#   warnings for missing categories.

# CRITICAL: Column ordering MUST be deterministic. PromotionConfig
#   stores `kinds_to_track` as a TUPLE (insertion-ordered).
#   Decision A (§15): sort by kind alphabetically, then within each
#   kind emit `active` before `intensity`. This makes the column list
#   pure-derivable from `kinds_to_track` regardless of insertion order
#   and matches the model_dump_json hash-stability expectations.

# CRITICAL: `T | None` instead of `Optional[T]` (PEP 604). The compute
#   method signature takes `promotion_rows_df: pd.DataFrame` — non-optional;
#   when no promotion config is enabled, the branch in compute_features()
#   short-circuits and the method is never called. There is no "no rows"
#   case to special-case; an empty DataFrame is a valid input and yields
#   all-zeros active columns + all-NaN intensity columns.

# GOTCHA: pandas merge with NaN keys does NOT match by default. The
#   chain-wide pass requires explicit filtering (`promo.store_id.isna()`)
#   rather than merging on NaN. Treat it as two separate joins + union.

# GOTCHA: `pd.NA` vs `np.nan` in Boolean indexers — pandas raises
#   "Cannot mask with non-boolean array containing NA / NaN values"
#   if a Boolean mask contains NA. Use `.fillna(False)` on the mask
#   BEFORE indexing, or coerce intermediate booleans to numpy bool.

# GOTCHA: `.astype(int)` on a boolean Series produces 0/1 ints — the
#   project-standard cast for the `active` column. NaN booleans (from
#   shift introducing NaN at the start of each series) survive as
#   float NaN; don't cast to int blindly without a fill. The
#   service.py:286 pattern (`.astype(int)` on a clean boolean) is the
#   reference for the indicator-after-shift case; promotion compute
#   intentionally KEEPS NaN at the start of each series (mirroring
#   how lag features have NaN in the first `lag_days` rows).

# GOTCHA: pyright --strict on `pd.Series[bool] | pd.Series[int]` unions
#   — annotate the local variable as `pd.Series[Any]` (NOT `pd.Series`
#   bare, NOT a union of generics). Pandas' pyright stubs in this repo
#   accept `pd.Series[Any]` cleanly; see service.py:223.

# GOTCHA: numpy bool_ vs Python bool — `df["a"] & df["b"]` returns
#   numpy bool_, which `.astype(int)` handles but mypy may complain
#   about. Cast through `bool` only at scalar level; for Series, the
#   `.astype(int)` cast is canonical.

# GOTCHA: For overlapping promotions on the same kind, the natural
#   reduction is `groupby(...).max()` — but `max()` on a Series with
#   ALL NaN returns NaN (correct). On a Series with mixed NaN+float,
#   `max()` skips NaN by default — which is what we want for intensity.
#   Active column is 0/1 ints; max gives the correct OR-semantics.
```

---

## Implementation Blueprint

### Data flow (high-level)

```
compute_features(df, cutoff_date)
  │
  ├─ df sorted + cutoff-filtered (existing infrastructure)
  │
  ├─ ...existing lag/rolling/calendar/exogenous branches...
  │
  └─ if self.config.promotion_config:           ← NEW BRANCH (1 line wrapper)
       df, cols = self._compute_promotion_features(df, self._promotion_rows_df)
                                                   ↑
                                                   set on service instance
                                                   by caller (PRP-3.1E)
                                                   or by unit tests directly
       feature_columns.extend(cols)
```

The compute method itself:

```
_compute_promotion_features(df, promotion_rows_df)
  │
  ├─ 1. PRE-FILTER promotion_rows_df:
  │     keep only rows where start_date <= df["date"].max()
  │     (coarse cutoff; per-row matching below is the load-bearing check)
  │
  ├─ 2. SORT df by [store_id, product_id, date]  (defensive; matches caller)
  │
  ├─ 3. For each kind in sorted(config.kinds_to_track):
  │       a. Filter promotion_rows_df to this kind
  │       b. Build store-specific overlap mask
  │       c. Build chain-wide   overlap mask
  │       d. Combine: active_today = (store_specific.any) | (chain_wide.any)
  │           intensity_today = max(discount_pct across overlapping promos)
  │       e. groupby([store_id, product_id]).shift(lag_days) on both
  │       f. Cast active to int (NaN preserved); intensity stays float
  │
  └─ Return (df, columns) — columns in deterministic sort order
```

### Pseudocode of the compute method

```python
# app/features/featuresets/service.py — append AFTER _compute_exogenous_features (line 404).
# CRITICAL: Signature mirrors the exogenous template but takes an EXTRA
# promotion_rows_df argument — the only feature method to do so (because
# promotion data lives in a separate table, not on sales_daily).

def _compute_promotion_features(
    self,
    df: pd.DataFrame,
    promotion_rows_df: pd.DataFrame,
) -> tuple[pd.DataFrame, list[str]]:
    """Compute promotion-family features (active + intensity per kind).

    CRITICAL: Time-safe via shift(lag_days) per (store_id, product_id).
    Per the time-safety contract (PRD §6), the active indicator for
    day D is computed from promotions whose date-range overlaps day D,
    THEN shifted by lag_days so the feature row at day D reads activity
    from day D - lag_days.

    Args:
        df: Sales DataFrame, pre-sorted and cutoff-filtered (per
            compute_features pipeline).
        promotion_rows_df: Promotion table rows. Schema mirrors
            phase2_promotion_rows_df fixture: columns
            [product_id, store_id, kind, discount_pct, start_date, end_date].
            store_id may be NaN (chain-wide).

    Returns:
        Tuple of (DataFrame with new columns, list of new column names).
    """
    config = self.config.promotion_config
    if config is None:
        raise RuntimeError("_compute_promotion_features called without promotion_config")

    result = df.copy()
    columns: list[str] = []
    lag = config.lag_days

    # Defensive re-sort to match the exogenous-compute invariant.
    result = result.sort_values([*self.entity_cols, self.date_col])
    dates = pd.to_datetime(result[self.date_col]).dt.date

    # Deterministic column ordering: sorted kinds, active before intensity.
    sorted_kinds: tuple[str, ...] = tuple(sorted(config.kinds_to_track))

    for kind in sorted_kinds:
        kind_rows = promotion_rows_df[promotion_rows_df["kind"] == kind]

        # Build a per-row Boolean (active today) and float (intensity today).
        active_today = pd.Series(0, index=result.index, dtype="int64")
        intensity_today = pd.Series(np.nan, index=result.index, dtype="float64")

        # PASS 1: store-specific promos (store_id matches the row's store_id).
        store_specific = kind_rows[kind_rows["store_id"].notna()]
        # PASS 2: chain-wide promos (store_id IS NULL).
        chain_wide = kind_rows[kind_rows["store_id"].isna()]

        # For each promo row, OR its active span into active_today and
        # take max() with its discount_pct into intensity_today.
        # This is the load-bearing date-range step — explicit and auditable.
        for _, promo in store_specific.iterrows():
            mask = (
                (result["store_id"] == promo["store_id"])
                & (result["product_id"] == promo["product_id"])
                & (dates >= promo["start_date"])
                & (dates <= promo["end_date"])
            )
            active_today = active_today.where(~mask, 1)
            disc = promo["discount_pct"]
            if pd.notna(disc):
                intensity_today = pd.concat(
                    [intensity_today, intensity_today.where(~mask, float(disc))],
                    axis=1,
                ).max(axis=1)
                # ^^ overlapping-on-same-kind reduction = max (Decision R8).

        for _, promo in chain_wide.iterrows():
            mask = (
                (result["product_id"] == promo["product_id"])
                & (dates >= promo["start_date"])
                & (dates <= promo["end_date"])
            )
            active_today = active_today.where(~mask, 1)
            disc = promo["discount_pct"]
            if pd.notna(disc):
                intensity_today = pd.concat(
                    [intensity_today, intensity_today.where(~mask, float(disc))],
                    axis=1,
                ).max(axis=1)

        # CRITICAL: shift(lag) per (store_id, product_id) — the leakage gate.
        # active feature at row D reads active_today at D - lag.
        if config.include_active:
            col = f"promo_{kind}_active_lag{lag}"
            shifted_active = result.assign(_a=active_today).groupby(
                self.entity_cols, observed=True
            )["_a"].shift(lag)
            # NaN from shift at series start preserved (matches lag-feature idiom).
            result[col] = shifted_active.astype("Int64")  # nullable int dtype
            columns.append(col)

        if config.include_intensity:
            col = f"promo_{kind}_intensity_lag{lag}"
            shifted_intensity = result.assign(_i=intensity_today).groupby(
                self.entity_cols, observed=True
            )["_i"].shift(lag)
            result[col] = shifted_intensity.astype("float64")
            columns.append(col)

    return result, columns
```

### How the compute method is wired into `compute_features()`

```python
# app/features/featuresets/service.py — INSERT after line 134
# (the closing of the exogenous block).

# 5. Exogenous features
if self.config.exogenous_config:
    result, cols = self._compute_exogenous_features(result)
    feature_columns.extend(cols)

# 6. Promotion features (Phase 2)
if self.config.promotion_config:
    promotion_rows_df = getattr(self, "_promotion_rows_df", None)
    if promotion_rows_df is None:
        # PRP-3.1E wires the DB JOIN that sets this attribute.
        # In unit tests, the test sets it directly on the service instance.
        # An empty DataFrame is the safe no-op fallback.
        promotion_rows_df = pd.DataFrame(
            columns=["product_id", "store_id", "kind",
                     "discount_pct", "start_date", "end_date"]
        )
    result, cols = self._compute_promotion_features(result, promotion_rows_df)
    feature_columns.extend(cols)
```

> Why the `getattr` indirection: this PRP delivers the pure-pandas compute
> method only. PRP-3.1E will land the DB JOIN (`_load_promotions_up_to_cutoff`)
> and the service-instance attribute. Unit tests in this PRP set
> `service._promotion_rows_df = fixture_df` directly. The fallback to an
> empty DataFrame means a misconfigured request never crashes — it just
> produces all-zero / all-NaN promotion columns (consistent with the
> "no active promotions" semantics).

### Test pseudocode

```python
# app/features/featuresets/tests/test_leakage.py — APPEND a new class.

class TestPromotionLeakage:
    """Tests verifying promotion features never use future data."""

    def test_promotion_active_no_leakage_at_same_day(
        self,
        sample_time_series: pd.DataFrame,
        phase2_promotion_rows_df: pd.DataFrame,
    ) -> None:
        """CRITICAL: A promotion active on day D MUST NOT appear in day D's
        promo_<kind>_active_lag1. It must only appear at day D+1."""
        # Build a single markdown promo: store=1, product=1,
        # start=2024-01-07, end=2024-01-14 (already in the fixture).
        config = FeatureSetConfig(
            name="test",
            entity_columns=("store_id", "product_id"),
            promotion_config=PromotionConfig(
                kinds_to_track=("markdown",),
                include_active=True,
                include_intensity=False,
                lag_days=1,
            ),
        )
        service = FeatureEngineeringService(config)
        service._promotion_rows_df = phase2_promotion_rows_df  # type: ignore[attr-defined]
        result = service.compute_features(sample_time_series)

        # The markdown is active 2024-01-07 .. 2024-01-14 (8 days).
        # promo_markdown_active_lag1 should be 1 on 2024-01-08 .. 2024-01-15.
        df = result.df.reset_index(drop=True)
        dates = pd.to_datetime(df["date"]).dt.date

        # Day BEFORE start (D=Jan 6): lag1 reads Jan 5 — inactive. EXPECT 0.
        assert df.loc[dates == date(2024, 1, 6), "promo_markdown_active_lag1"].iloc[0] == 0

        # Day OF start (D=Jan 7): lag1 reads Jan 6 — inactive. EXPECT 0.
        #   This is the load-bearing leakage check: same-day MUST NOT leak.
        assert df.loc[dates == date(2024, 1, 7), "promo_markdown_active_lag1"].iloc[0] == 0

        # Day AFTER start (D=Jan 8): lag1 reads Jan 7 — active. EXPECT 1.
        assert df.loc[dates == date(2024, 1, 8), "promo_markdown_active_lag1"].iloc[0] == 1

        # Day AFTER end (D=Jan 15): lag1 reads Jan 14 — last active day. EXPECT 1.
        assert df.loc[dates == date(2024, 1, 15), "promo_markdown_active_lag1"].iloc[0] == 1

        # Two days AFTER end (D=Jan 16): lag1 reads Jan 15 — inactive. EXPECT 0.
        assert df.loc[dates == date(2024, 1, 16), "promo_markdown_active_lag1"].iloc[0] == 0

    def test_promotion_boundary_end_date_at_cutoff(
        self,
        sample_time_series: pd.DataFrame,
    ) -> None:
        """A promo ending exactly on cutoff_date - 1 yields active_lag1=1 at cutoff."""
        cutoff = date(2024, 1, 15)
        promo_rows = pd.DataFrame({
            "product_id":   [1],
            "store_id":     [1],
            "kind":         ["markdown"],
            "discount_pct": [0.20],
            "start_date":   [date(2024, 1, 10)],
            "end_date":     [date(2024, 1, 14)],     # cutoff - 1
        })
        config = FeatureSetConfig(
            name="test",
            entity_columns=("store_id", "product_id"),
            promotion_config=PromotionConfig(kinds_to_track=("markdown",), lag_days=1),
        )
        service = FeatureEngineeringService(config)
        service._promotion_rows_df = promo_rows  # type: ignore[attr-defined]
        result = service.compute_features(sample_time_series, cutoff_date=cutoff)

        df = result.df.reset_index(drop=True)
        dates = pd.to_datetime(df["date"]).dt.date
        # At cutoff (Jan 15), lag1 reads Jan 14 — end_date, INCLUSIVE → active.
        last = df.loc[dates == cutoff].iloc[0]
        assert last["promo_markdown_active_lag1"] == 1, (
            "Boundary leakage: end_date INCLUSIVE on the previous day failed"
        )

    def test_promotion_starts_on_cutoff_not_in_lag1(
        self,
        sample_time_series: pd.DataFrame,
    ) -> None:
        """A promo starting exactly on cutoff is NOT in active_lag1 at cutoff."""
        cutoff = date(2024, 1, 15)
        promo_rows = pd.DataFrame({
            "product_id":   [1],
            "store_id":     [1],
            "kind":         ["markdown"],
            "discount_pct": [0.20],
            "start_date":   [cutoff],                # starts today
            "end_date":     [date(2024, 1, 25)],
        })
        config = FeatureSetConfig(
            name="test",
            entity_columns=("store_id", "product_id"),
            promotion_config=PromotionConfig(kinds_to_track=("markdown",), lag_days=1),
        )
        service = FeatureEngineeringService(config)
        service._promotion_rows_df = promo_rows  # type: ignore[attr-defined]
        result = service.compute_features(sample_time_series, cutoff_date=cutoff)

        df = result.df.reset_index(drop=True)
        dates = pd.to_datetime(df["date"]).dt.date
        last = df.loc[dates == cutoff].iloc[0]
        # lag1 reads cutoff - 1 = Jan 14, BEFORE start_date.
        assert last["promo_markdown_active_lag1"] == 0, (
            "Same-day leakage: promo starting on D appeared in active_lag1 at D"
        )

    def test_chain_wide_promo_does_not_bleed_across_products(
        self,
        multi_series_time_series: pd.DataFrame,
    ) -> None:
        """A chain-wide promo on product=1 must NOT activate features for product=2."""
        promo_rows = pd.DataFrame({
            "product_id":   [1],
            "store_id":     [None],                  # chain-wide
            "kind":         ["markdown"],
            "discount_pct": [0.30],
            "start_date":   [date(2024, 1, 3)],
            "end_date":     [date(2024, 1, 7)],
        })
        config = FeatureSetConfig(
            name="test",
            entity_columns=("store_id", "product_id"),
            promotion_config=PromotionConfig(kinds_to_track=("markdown",), lag_days=1),
        )
        service = FeatureEngineeringService(config)
        service._promotion_rows_df = promo_rows  # type: ignore[attr-defined]
        result = service.compute_features(multi_series_time_series)

        df = result.df
        # Product 1 should see activity 2024-01-04 .. 2024-01-08 (lag1).
        prod1 = df[df["product_id"] == 1]
        assert int(prod1["promo_markdown_active_lag1"].sum()) == 5 * 2  # 2 stores × 5 days
        # Product 2 should see ZERO activity (chain-wide is product-scoped).
        prod2 = df[df["product_id"] == 2]
        assert int(prod2["promo_markdown_active_lag1"].sum()) == 0


# app/features/featuresets/tests/test_service.py — APPEND a new class.

class TestPromotionFeatures:
    """Tests for promotion feature computation."""

    def test_single_kind_happy_path(
        self,
        sample_time_series: pd.DataFrame,
        phase2_promotion_rows_df: pd.DataFrame,
    ) -> None:
        """Single-kind config produces exactly active+intensity columns for that kind."""
        config = FeatureSetConfig(
            name="test",
            promotion_config=PromotionConfig(kinds_to_track=("markdown",)),
        )
        service = FeatureEngineeringService(config)
        service._promotion_rows_df = phase2_promotion_rows_df  # type: ignore[attr-defined]
        result = service.compute_features(sample_time_series)

        assert "promo_markdown_active_lag1" in result.feature_columns
        assert "promo_markdown_intensity_lag1" in result.feature_columns
        # Determinism: exactly 2 columns, sorted in (active, intensity) order.
        promo_cols = [c for c in result.feature_columns if c.startswith("promo_")]
        assert promo_cols == ["promo_markdown_active_lag1", "promo_markdown_intensity_lag1"]

    def test_multi_kind_produces_all_columns_sorted(
        self,
        sample_time_series: pd.DataFrame,
        phase2_promotion_rows_df: pd.DataFrame,
    ) -> None:
        """Multi-kind config produces 4 columns in deterministic (sorted-kind) order."""
        config = FeatureSetConfig(
            name="test",
            promotion_config=PromotionConfig(
                kinds_to_track=("pct_off", "markdown"),  # intentionally unsorted input
            ),
        )
        service = FeatureEngineeringService(config)
        service._promotion_rows_df = phase2_promotion_rows_df  # type: ignore[attr-defined]
        result = service.compute_features(sample_time_series)

        promo_cols = [c for c in result.feature_columns if c.startswith("promo_")]
        # Decision A: sorted by kind, then active before intensity.
        assert promo_cols == [
            "promo_markdown_active_lag1",
            "promo_markdown_intensity_lag1",
            "promo_pct_off_active_lag1",
            "promo_pct_off_intensity_lag1",
        ]

    def test_chain_wide_promo_applies_to_all_stores(
        self,
        multi_series_time_series: pd.DataFrame,
    ) -> None:
        """A chain-wide promo (store_id IS NULL) applies to every store of the product."""
        promo_rows = pd.DataFrame({
            "product_id":   [1],
            "store_id":     [None],
            "kind":         ["pct_off"],
            "discount_pct": [0.10],
            "start_date":   [date(2024, 1, 3)],
            "end_date":     [date(2024, 1, 5)],
        })
        config = FeatureSetConfig(
            name="test",
            promotion_config=PromotionConfig(kinds_to_track=("pct_off",)),
        )
        service = FeatureEngineeringService(config)
        service._promotion_rows_df = promo_rows  # type: ignore[attr-defined]
        result = service.compute_features(multi_series_time_series)

        # All product=1 rows in 2024-01-04..2024-01-06 (lag1) should be active.
        df = result.df
        prod1_active = df[(df["product_id"] == 1) & (df["promo_pct_off_active_lag1"] == 1)]
        # 2 stores × 3 active-lagged days = 6
        assert len(prod1_active) == 6

    def test_null_discount_pct_yields_nan_intensity_but_active_one(self) -> None:
        """A bogo promo with NULL discount_pct: active=1, intensity=NaN."""
        sample = pd.DataFrame({
            "date": pd.date_range("2024-01-01", periods=10, freq="D"),
            "store_id": [1] * 10,
            "product_id": [1] * 10,
            "quantity": list(range(1, 11)),
            "unit_price": [10.0] * 10,
            "total_amount": [q * 10.0 for q in range(1, 11)],
        })
        promo_rows = pd.DataFrame({
            "product_id":   [1],
            "store_id":     [1],
            "kind":         ["bogo"],
            "discount_pct": [None],
            "start_date":   [date(2024, 1, 3)],
            "end_date":     [date(2024, 1, 5)],
        })
        config = FeatureSetConfig(
            name="test",
            promotion_config=PromotionConfig(kinds_to_track=("bogo",)),
        )
        service = FeatureEngineeringService(config)
        service._promotion_rows_df = promo_rows  # type: ignore[attr-defined]
        result = service.compute_features(sample)

        df = result.df.reset_index(drop=True)
        dates = pd.to_datetime(df["date"]).dt.date
        # D=Jan 4 reads Jan 3 (start). active=1.
        row = df.loc[dates == date(2024, 1, 4)].iloc[0]
        assert row["promo_bogo_active_lag1"] == 1
        assert pd.isna(row["promo_bogo_intensity_lag1"])

    def test_overlapping_promos_intensity_uses_max(self) -> None:
        """Two markdowns active on the same (store, product, day) → intensity = max."""
        sample = pd.DataFrame({
            "date": pd.date_range("2024-01-01", periods=10, freq="D"),
            "store_id": [1] * 10,
            "product_id": [1] * 10,
            "quantity": list(range(1, 11)),
            "unit_price": [10.0] * 10,
            "total_amount": [q * 10.0 for q in range(1, 11)],
        })
        promo_rows = pd.DataFrame({
            "product_id":   [1, 1],
            "store_id":     [1, 1],
            "kind":         ["markdown", "markdown"],
            "discount_pct": [0.15, 0.25],          # overlap → max = 0.25
            "start_date":   [date(2024, 1, 3), date(2024, 1, 4)],
            "end_date":     [date(2024, 1, 6), date(2024, 1, 5)],
        })
        config = FeatureSetConfig(
            name="test",
            promotion_config=PromotionConfig(kinds_to_track=("markdown",)),
        )
        service = FeatureEngineeringService(config)
        service._promotion_rows_df = promo_rows  # type: ignore[attr-defined]
        result = service.compute_features(sample)

        df = result.df.reset_index(drop=True)
        dates = pd.to_datetime(df["date"]).dt.date
        # D=Jan 5 reads Jan 4 — BOTH active. intensity = max(0.15, 0.25) = 0.25.
        row = df.loc[dates == date(2024, 1, 5)].iloc[0]
        assert row["promo_markdown_active_lag1"] == 1
        assert row["promo_markdown_intensity_lag1"] == pytest.approx(0.25)

    def test_no_active_promo_yields_zero_active_and_nan_intensity(
        self,
        sample_time_series: pd.DataFrame,
    ) -> None:
        """No promo rows at all → active column is all zero (after lag NaN), intensity all NaN."""
        config = FeatureSetConfig(
            name="test",
            promotion_config=PromotionConfig(kinds_to_track=("markdown",)),
        )
        service = FeatureEngineeringService(config)
        service._promotion_rows_df = pd.DataFrame(  # type: ignore[attr-defined]
            columns=["product_id", "store_id", "kind", "discount_pct", "start_date", "end_date"]
        )
        result = service.compute_features(sample_time_series)

        active = result.df["promo_markdown_active_lag1"]
        intensity = result.df["promo_markdown_intensity_lag1"]
        # First row of each series has NaN from the lag shift; remaining rows are 0.
        assert pd.isna(active.iloc[0])
        assert (active.iloc[1:] == 0).all()
        assert intensity.isna().all()
```

### List of tasks (in execution order)

```yaml
Task 1 — Add the leakage tests FIRST (test-first per PRD §6 row 5):
MODIFY app/features/featuresets/tests/test_leakage.py:
  - ADD imports at the top of file:
      from app.features.featuresets.schemas import PromotionConfig
  - APPEND new class `TestPromotionLeakage` at end-of-file (NOT inside
    an existing class). Include at minimum these cases:
      * test_promotion_active_no_leakage_at_same_day
      * test_promotion_boundary_end_date_at_cutoff
      * test_promotion_starts_on_cutoff_not_in_lag1
      * test_chain_wide_promo_does_not_bleed_across_products
  - Use `service._promotion_rows_df = ...  # type: ignore[attr-defined]`
    to inject the test promo data — the attribute is a private hook,
    not part of the public API.
  - These tests MUST FAIL until Task 2 lands (verify by running them now).

Task 2 — Implement the compute method:
MODIFY app/features/featuresets/service.py:
  - ADD top-of-file imports if not already present:
      import numpy as np   (already imported at line 17)
  - INSERT `_compute_promotion_features(self, df, promotion_rows_df)`
    method AFTER `_compute_exogenous_features` (line 404), BEFORE
    the `class FeatureDataLoader` declaration (line 407).
  - MIRROR the exogenous-compute style — use self.entity_cols,
    self.date_col, self.target_col where appropriate.
  - Implement the two-pass match: store-specific + chain-wide.
  - Use sorted(config.kinds_to_track) for deterministic column order.
  - groupby(self.entity_cols, observed=True).shift(lag_days) is the
    load-bearing time-safety gate.
  - Cast active to Int64 (nullable int dtype) to preserve NaN at series start.

Task 3 — Wire the branch into compute_features():
MODIFY app/features/featuresets/service.py:
  - FIND pattern: `if self.config.exogenous_config:` (line 132).
  - INSERT immediately after the exogenous block (line 134) a new
    branch handling promotion_config. The branch reads
    `getattr(self, "_promotion_rows_df", None)` and falls back to
    an empty DataFrame with the documented column schema.
  - DO NOT modify any other line in compute_features.

Task 4 — Add the unit tests:
MODIFY app/features/featuresets/tests/test_service.py:
  - ADD imports at the top:
      from app.features.featuresets.schemas import PromotionConfig
      from datetime import date
  - APPEND new class `TestPromotionFeatures` at end-of-file. Include
    at minimum these cases:
      * test_single_kind_happy_path
      * test_multi_kind_produces_all_columns_sorted
      * test_chain_wide_promo_applies_to_all_stores
      * test_null_discount_pct_yields_nan_intensity_but_active_one
      * test_overlapping_promos_intensity_uses_max
      * test_no_active_promo_yields_zero_active_and_nan_intensity
  - MIRROR style of TestLagFeatures (test_service.py:18-69).

Task 5 — Validation gates (run locally + CI):
RUN (must all pass):
  uv run ruff check app/features/featuresets/
  uv run ruff format --check app/features/featuresets/
  uv run mypy app/features/featuresets/service.py
  uv run pyright app/features/featuresets/service.py
  uv run pytest app/features/featuresets/tests/test_leakage.py -v
  uv run pytest app/features/featuresets/tests/test_service.py -v -k promotion
  uv run pytest app/features/featuresets/ -v   # full module regression

Task 6 — Commit:
  Single commit, message:
  `feat(features): implement promotion compute method (#<issue>)`
  No AI co-author trailer. Reference the parent issue from
  the PRP-3.1 umbrella (same issue PRP-3.1A used).
```

### Integration Points

```yaml
DATABASE:
  - NO migration required. Promotion table already exists per
    alembic/versions/a8b9c0d1e234_add_retail_depth_columns_and_replenishment_event_table.py.

CONFIG:
  - NO new env vars (per PRD §9). PromotionConfig already in place from PRP-3.1A.

ROUTES:
  - NO changes. The request body is FeatureSetConfig — already accepts
    promotion_config (PRP-3.1A).

SCHEMAS:
  - NO changes. PromotionConfig at schemas.py:237-276 is final.
  - FeatureSetConfig.promotion_config field at schemas.py:323 is in place.
  - get_enabled_features() already emits "promotion".

SERVICE:
  - +_compute_promotion_features method (~80 LOC)
  - +1 branch in compute_features (~7 LOC)
  - +getattr(self, "_promotion_rows_df", None) indirection — the DB JOIN
    helper (_load_promotions_up_to_cutoff) is intentionally deferred to
    PRP-3.1E so this slice stays pure-pandas-testable.

TESTS:
  - +TestPromotionLeakage in test_leakage.py
  - +TestPromotionFeatures in test_service.py

DOCS:
  - NO docs touched here. PRP-3.1E updates
    docs/PHASE/3-FEATURE_ENGINEERING.md and DOMAIN_MODEL.md after all
    Phase 2 compute methods land.

DOWNSTREAM PRPs:
  - PRP-3.1E (E2E + docs) — depends on this PRP plus PRP-3.1B/3.1C.
    PRP-3.1E will:
      * Add async helper `_load_promotions_up_to_cutoff(db, store_ids,
        product_ids, cutoff_date)` in service.py
      * Wire the helper into compute_features_for_series at line 535
      * Set service._promotion_rows_df from the loaded DataFrame
      * Add an integration test that exercises a real Postgres seed
        through the full pipeline
```

---

## Validation Loop

### Level 1: Syntax & Style

```bash
# Run from repo root. Fix errors before proceeding to Level 2.
uv run ruff check app/features/featuresets/ --fix
uv run ruff format --check app/features/featuresets/

# If formatting drifts:
uv run ruff format app/features/featuresets/

# Expected: clean.
```

### Level 2: Type Checks (BOTH must be clean — merge gate)

```bash
uv run mypy app/features/featuresets/service.py
uv run pyright app/features/featuresets/service.py

# Expected: 0 errors on each. Common failure modes:
#   - pyright "reportUnknownMemberType" on a pandas Series boolean op —
#     annotate the local as `pd.Series[Any]` per service.py:223.
#   - mypy "Incompatible return value type" — ensure the return is
#     `tuple[pd.DataFrame, list[str]]`, NOT a bare tuple.
#   - pyright "Argument type for getattr default is invalid" — wrap the
#     empty-DataFrame fallback in a local variable BEFORE the getattr
#     call if needed.
```

### Level 3: Leakage Tests (load-bearing — the spec)

```bash
# Run leakage tests in isolation first — they MUST pass before any
# other test gate can be trusted.
uv run pytest app/features/featuresets/tests/test_leakage.py -v -k promotion

# Expected: all four (or more) TestPromotionLeakage cases green.
# If any case fails:
#   - DO NOT weaken the assertion to make it pass.
#   - DO NOT add an `if promo.start_date == cutoff: skip` special case.
#   - Read the failure, understand which day's feature is reading
#     which day's underlying data, and fix the shift(lag) wiring.
```

### Level 4: Unit Tests (full sweep — regression-safe)

```bash
# Promotion-specific unit tests:
uv run pytest app/features/featuresets/tests/test_service.py -v -k promotion

# Full module — must show 0 regressions in pre-existing tests:
uv run pytest app/features/featuresets/ -v

# If a non-promotion test fails: STOP. Either compute_features() was
# accidentally modified, or the new branch is firing when it shouldn't.
# Roll back the wiring change in Task 3 and re-test.
```

### Level 5: Additive-contract proof (no regression on `config_hash`)

```bash
# Manual verification before opening PR:
# 1. On current branch (post-changes):
uv run python -c "
from app.features.featuresets.schemas import FeatureSetConfig
print('post-PR hash (no promotion):', FeatureSetConfig(name='x').config_hash())
"

# 2. Check out dev:
git stash
git switch dev
uv run python -c "
from app.features.featuresets.schemas import FeatureSetConfig
print('pre-PR hash (no promotion):', FeatureSetConfig(name='x').config_hash())
"
git switch -
git stash pop

# 3. The two hashes MUST match — promotion compute is a service-layer
#    addition; the schema is unchanged.
```

### Level 6: Integration (HTTP boundary)

```bash
# Start the API:
docker compose up -d
uv run alembic upgrade head
uv run uvicorn app.main:app --reload --port 8123 &
APP_PID=$!

# A pre-PR caller (no promotion_config) gets byte-identical responses:
curl -s -X POST http://localhost:8123/featuresets/compute \
  -H "Content-Type: application/json" \
  -d '{"store_id":1,"product_id":1,"cutoff_date":"2024-01-31","config":{"name":"smoke"}}' \
  | jq '.config_hash, .feature_columns'

# A new caller with promotion_config gets the new columns. NOTE: this PRP
# does NOT wire the DB JOIN — without PRP-3.1E in place, the service will
# fall back to the empty DataFrame and emit all-zero / all-NaN promotion
# columns. The endpoint must still return 200 OK with the column names
# present in feature_columns.
curl -s -X POST http://localhost:8123/featuresets/compute \
  -H "Content-Type: application/json" \
  -d '{
    "store_id":1,"product_id":1,"cutoff_date":"2024-01-31",
    "config":{
      "name":"promo-smoke",
      "promotion_config":{
        "kinds_to_track":["markdown"],"include_active":true,
        "include_intensity":true,"lag_days":1
      }
    }
  }' \
  | jq '.feature_columns'
# Expected output includes "promo_markdown_active_lag1" and
# "promo_markdown_intensity_lag1".

kill $APP_PID
```

---

## Final Validation Checklist

- [ ] All leakage tests pass: `uv run pytest app/features/featuresets/tests/test_leakage.py -v -k promotion`
- [ ] All unit tests pass: `uv run pytest app/features/featuresets/tests/test_service.py -v -k promotion`
- [ ] Full module green: `uv run pytest app/features/featuresets/ -v`
- [ ] No linting errors: `uv run ruff check app/features/featuresets/`
- [ ] No formatting drift: `uv run ruff format --check app/features/featuresets/`
- [ ] No mypy errors: `uv run mypy app/features/featuresets/service.py`
- [ ] No pyright errors: `uv run pyright app/features/featuresets/service.py`
- [ ] Additive-contract proof: `config_hash()` on `FeatureSetConfig(name="x")` is identical pre/post PR (Level 5)
- [ ] HTTP smoke OK: empty-promotion-data response has the new columns and 200 status (Level 6)
- [ ] Diff stat: ≤ +300 / -10 LOC (verify with `git diff --stat dev...`)
- [ ] Single commit, message: `feat(features): implement promotion compute method (#<issue>)` (use the parent issue from PRP-3.1 umbrella)
- [ ] No `schemas.py` changes, no `routes.py` changes (verify with `git diff dev... -- app/features/featuresets/schemas.py app/features/featuresets/routes.py` → empty)
- [ ] No new Alembic migration created (verify with `git diff --name-only dev... | grep alembic` → empty)
- [ ] No AI co-author trailer in the commit message

---

## Anti-Patterns to Avoid

- ❌ **Do NOT touch `schemas.py`.** `PromotionConfig` is final from PRP-3.1A. Any tweak here breaks the additive-contract proof.
- ❌ **Do NOT add an Alembic migration.** All required tables and columns exist (`alembic/versions/a8b9c0d1e234_*`).
- ❌ **Do NOT do `.rolling(...).shift(lag)`.** The order is `groupby(...).shift(lag)` on an already-computed daily indicator — there is no rolling here.
- ❌ **Do NOT use `.fillna(0)` on intensity.** NULL `discount_pct` must surface as `NaN` so downstream imputation strategies (`ImputationConfig`) can choose how to handle it. Forcing zero corrupts the signal for bogo/bundle.
- ❌ **Do NOT collapse the two-pass match into a single `pd.merge`.** NaN-valued merge keys silently drop chain-wide rows; two explicit passes are auditable and correct.
- ❌ **Do NOT preserve input order of `kinds_to_track`** in the column list. Use `sorted(...)` — Decision A. This makes column-name presence deterministic regardless of caller order.
- ❌ **Do NOT take `sum()` over overlapping promos.** Decision R8: `max(discount_pct)` matches real-world consumer experience (a shopper sees the deepest discount, not the sum of overlapping advertised discounts).
- ❌ **Do NOT iterate over `df.iterrows()` for the SALES side.** The promotion-side iteration is bounded by the number of promo rows (small); iterating over sales rows is O(rows × promos) and forbidden by the project's pandas idiom (vectorized boolean masks instead).
- ❌ **Do NOT silently swallow an out-of-allowlist kind.** Pydantic v2's `Literal` allow-list on `kinds_to_track` already rejects at the boundary; do NOT add a runtime `if kind not in {...}` fallback that masks the validation error.
- ❌ **Do NOT cast `active` to plain `int` without preserving NaN.** Use `Int64` (pandas nullable int) to keep the first-`lag_days`-rows-NaN behavior consistent with the lag-feature idiom.
- ❌ **Do NOT wire the DB JOIN here.** `_load_promotions_up_to_cutoff` is PRP-3.1E's deliverable. This PRP is a pure-pandas compute method that takes a DataFrame in.
- ❌ **Do NOT modify `compute_features_for_series` at `service.py:535`.** That function is the production-path caller; PRP-3.1E will extend it. Modifying it here couples this slice to PRP-3.1E and defeats parallelism.
- ❌ **Do NOT add an AI co-author trailer** (`.claude/rules/commit-format.md` forbids it).

---

## §15 — PRP-Authoring Decisions

These are decisions made during PRP authoring that the INITIAL/PRD did not explicitly lock — recorded here so a future session can audit the reasoning.

### Decision A — Deterministic column order: sort `kinds_to_track` alphabetically

**INITIAL said:** Loop over kinds in `kinds_to_track`; column ordering left implicit.
**Decision:** Sort kinds alphabetically inside the compute method; within each kind, emit `active` before `intensity`.
**Why:** `kinds_to_track` is a tuple (insertion-ordered) — but two callers passing `("markdown","pct_off")` vs `("pct_off","markdown")` semantically describe the same feature set. If column order followed tuple order, the produced `feature_columns` list would be hash-divergent across callers. Sorting forces a single canonical order, which matters for:
  1. `model_dump_json` stability (config-hash invariance is unaffected because `kinds_to_track` is hashed by Pydantic preserving insertion order — but the materialized feature matrix has a single canonical layout).
  2. Backtest run-comparison in the Registry — same kinds in different orders ⇒ same column names ⇒ same artifact shape.
  3. Test determinism — `assert promo_cols == [...]` becomes a stable assertion.
**Risk if reversed:** Two callers with the same kinds but different order would produce mismatched `feature_columns` lists, causing spurious Registry-comparison failures. Low operational risk, high test-flakiness risk.
**How to apply:** `for kind in sorted(config.kinds_to_track):` inside the method. One line.

### Decision B — Take the promotion data as a method argument, not a service-instance attribute (with a graceful fallback)

**INITIAL said:** "Async SQLAlchemy helper `_load_promotions_up_to_cutoff(...)` returns a DataFrame" — implying the service does the load itself.
**Decision:** Method signature takes `promotion_rows_df: pd.DataFrame` as a positional argument. The `compute_features()` wiring reads `getattr(self, "_promotion_rows_df", None)` and falls back to an empty DataFrame.
**Why:** Two competing goals:
  - **Parallelism with PRP-3.1B/C:** PRP-3.1E lands the DB JOIN. If this PRP also lands a DB call, PRP-3.1E and PRP-3.1D conflict on `service.py`.
  - **Unit-testability:** Pure-pandas methods are 100× easier to test than methods that call `db.execute()`.
By making the method take a DataFrame, this PRP delivers a fully testable unit. The `getattr` indirection in `compute_features()` is a 3-line bridge that PRP-3.1E removes (replacing it with an `await self._load_promotions_up_to_cutoff(...)` call). The empty-DataFrame fallback means the API never crashes if no caller set the attribute.
**Risk if reversed:** Either this PRP grows by ~80 LOC to include an async helper and an integration test, OR PRP-3.1D and PRP-3.1E end up serialized.
**How to apply:** Already specified in the Implementation Blueprint above. The `_promotion_rows_df` attribute is a private convention — `# type: ignore[attr-defined]` is acceptable at the test sites because PRP-3.1E will move it to a proper `__init__` field.

### Decision C — Overlapping-promo intensity uses `max(discount_pct)`, not `sum`

**INITIAL said:** "decide; recommend `max`" (line 42).
**Decisions log §8 R8 said:** "pick `max`".
**My call:** `max`.
**Why:** From the consumer perspective, when two markdowns overlap on a single (store, product, day), the shopper experiences the deepest single discount, not the additive total. `sum` would over-state intensity (and could exceed the `0..1` Numeric(5,4) CHECK constraint's semantics, even though the constraint is on the source column, not the derived feature).
**How to apply:** `pd.concat([prev, masked_new], axis=1).max(axis=1)` — vectorized, NaN-skipping.

### Decision D — `active` column dtype is `Int64` (pandas nullable int), not `int64`

**INITIAL said:** "int (0/1)".
**Decision:** Use `Int64` (capital I, pandas extension dtype).
**Why:** The first `lag_days` rows of each series naturally have `NaN` after the `groupby(...).shift(lag)` — same as the lag-feature idiom (`test_leakage.py` enforces this for lag at line 302). With plain `int64`, the cast would error on NaN (or silently convert to `0`, hiding the leakage detection). With `Int64`, NaN is preserved as `pd.NA`, and downstream imputation can handle it consistently.
**Risk if reversed:** The leakage test `test_first_row_never_has_valid_lag` pattern doesn't transfer cleanly to promotion; a caller might see a misleading `0` in row 0 of each series and infer "no promo was active yesterday" — when in fact "yesterday" doesn't exist for that series.
**How to apply:** `.astype("Int64")` (pandas extension dtype) at the end of the active-column write.

### Decision E — Skip the DataFrame-merge approach; use boolean-mask iteration over promos

**Alternative considered:** Cross-join the sales DataFrame with the promotion DataFrame, filter on date-range overlap, then groupby-aggregate.
**Decision:** Iterate over promotion rows (not sales rows), apply boolean masks on the sales DataFrame.
**Why:** The promotion table is small (O(100s) of rows for a typical scenario); the sales DataFrame is large (O(10k+ rows). Iterating over promos and applying `df.where(~mask, value)` is O(promos × sales) but vectorized — pandas's C-level boolean ops dominate. A cross-join would be O(promos × sales) materialized, which is wasteful memory-wise.
**Risk if reversed:** Memory-bloat in production-shaped data; harder to read in code review.
**How to apply:** `for _, promo in promotion_rows_df.iterrows():` — explicit, line-by-line auditable.

---

## §16 — Open Questions for the Implementing Agent

None. All inherited PRD-level open questions were resolved in earlier slices:

- Q1 (lifecycle encoding) — resolved in PRP-3.1A.
- Q2 (markdown vs bundles) — resolved: `PromotionConfig` handles all four kinds.
- Q3 (PRP path) — resolved: this is the D-slice (`PRP-3.1D-promotion-compute.md`).
- R7 (`Promotion.value_pct` column name) — resolved in PRP-3.1A: actual column is `discount_pct` (`models.py:306`).
- R8 (overlapping aggregation) — resolved: `max(discount_pct)` (Decision C).

If a downstream surprise emerges (the diff exceeds 300 LOC, pyright --strict flags a pandas-stub edge case, or the leakage test reveals an off-by-one in the date-range semantics), STOP and ask before resolving — don't quietly weaken the time-safety contract.

---

## Confidence Score: 9 / 10

**Why 9, not 10:**
- ✅ All file paths verified (no dead references).
- ✅ All DB column names verified against `data_platform/models.py` lines 274-342.
- ✅ Exact line numbers cited for every pattern source.
- ✅ Locked decisions explicitly carried forward from PRP-3.1A and `phase2-decisions-and-prp-prep.md`.
- ✅ Validation gates are deterministic and executable as-written.
- ✅ Leakage tests are test-first (Task 1 before Task 2) and load-bearing.
- ✅ The additive-contract invariant is preserved (no schema edits, getattr fallback to empty DataFrame).
- ✅ Parallel-safe with PRP-3.1B and PRP-3.1C (only one file shared: `service.py`; the compute method is appended, the `compute_features()` edit is a single inserted block).
- ⚠️ The one residual risk: pyright --strict reaction to pandas' boolean-Series `.where(~mask, value)` chain when the value is a Python `int` literal. Mitigation in Gotchas (annotate the local as `pd.Series[Any]`). Fall back to an explicit `Series.astype(...)` cast if pyright still complains.

Goal achieved: an implementing agent with no prior session context can read this PRP, edit 3 files (service.py + test_leakage.py + test_service.py), run 7 commands, and ship a green PR.
