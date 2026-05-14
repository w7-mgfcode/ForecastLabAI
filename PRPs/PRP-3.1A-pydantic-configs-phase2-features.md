# PRP-3.1A: Pydantic Configs + Leakage-Test Harness for Phase 2 Features

**Feature**: `.agents/plans/initial-1-pydantic-configs-and-test-harness.md`
**Parent PRP**: PRP-3.1 (umbrella — Phase 2 feature wiring; PRP-3.1A through PRP-3.1E are the 5 slices)
**Parent PRD**: `.agents/plans/wire-phase2-features-to-featuresets.md`
**Status**: Ready for Implementation
**Confidence Score**: 9 / 10 — schema-only diff, all DB shapes verified, exact pattern source files identified, validation gates fully deterministic. Single uncertainty: `enabled_features` token name (`"promotion"` vs `"markdown"`) — resolved in §15 "PRP-authoring decisions" with rationale.

---

## Goal

Land the foundation of the Phase 2 feature-wiring work as a **schema-only, additive PR**:

1. Three new Pydantic v2 `*Config` classes in `app/features/featuresets/schemas.py` (`LifecycleConfig`, `ReplenishmentConfig`, `PromotionConfig`).
2. Three optional `FeatureSetConfig` fields (`lifecycle_config`, `replenishment_config`, `promotion_config`), all `<T> | None = None`.
3. Extend `FeatureSetConfig.get_enabled_features()` to emit `"lifecycle"`, `"replenishment"`, `"promotion"` when the matching config is set.
4. Per-class schema validation tests in `tests/test_schemas.py` (defaults, bounds, allow-lists, frozen invariant).
5. Phase 2-shaped DataFrame fixtures in `tests/conftest.py` reusable by PRP-3.1B/C/D (compute methods).
6. **NO compute methods, NO `service.py` edits, NO `routes.py` edits.** Schema + fixtures only.

End state — single commit, ≤ 150 LOC net diff, `mypy --strict` + `pyright --strict` clean, `pytest app/features/featuresets/tests/test_schemas.py -v` green, full `pytest app/features/featuresets/ -v` shows no regression in existing cases.

---

## Why

- **Unblocks PRP-3.1B/C/D in parallel.** Once the schemas land, the three compute-method slices (lifecycle, replenishment, promotion) can run as parallel branches without merge conflicts on `schemas.py`.
- **Locks the request-body contract before any service-layer churn.** Schema-pure diffs are trivially reviewable; once `LifecycleConfig` ships, the implementation slices can't accidentally widen the public API mid-PR.
- **Establishes shared fixture infrastructure.** All three downstream slices need DataFrames that mirror the seeder's Phase 2 emission (lifecycle dates on products, replenishment events as a separate table, promotion rows with `kind` discriminator). Building these once in `conftest.py` keeps the leakage-spec invariants consistent across PRP-3.1B/C/D.
- **Preserves the additive-contract invariant** (PRD §6 + PRD §11). All three new `FeatureSetConfig` fields default to `None`; the `config_hash()` deduplication output is byte-identical for pre-PR requests.

---

## What

### User-visible behavior

- `POST /featuresets/compute` accepts (but ignores, in this PR) three new optional body fields:
  ```jsonc
  {
    "lifecycle_config":    { "include_days_since_launch": true, ... } | null,
    "replenishment_config": { "include_days_since_last": true, ... } | null,
    "promotion_config":    { "kinds_to_track": ["markdown"], ... }    | null
  }
  ```
- Pydantic v2 rejects out-of-bounds or out-of-allowlist values with a 422 (via FastAPI's existing handler → RFC 7807 in `app/core/problem_details.py`).
- `FeatureSetConfig(...).get_enabled_features()` includes the new family tokens when the matching config is set; existing tokens (`lag`, `rolling`, `calendar`, `exogenous`) are unchanged in position or naming.

### Success Criteria

- [ ] Three new classes exist in `schemas.py`, each inheriting `FeatureConfigBase` (frozen, extra="forbid", schema_version, config_hash()).
- [ ] Three new `FeatureSetConfig` fields with `<T> | None = None` default; field order: append after `exogenous_config`, before `imputation_config`.
- [ ] `get_enabled_features()` emits `"lifecycle"`, `"replenishment"`, `"promotion"` (in that order, after `"exogenous"`).
- [ ] `tests/test_schemas.py` has one `TestLifecycleConfig`, one `TestReplenishmentConfig`, one `TestPromotionConfig` class, each with ≥4 cases (default, bounds reject, allow-list reject, frozen).
- [ ] `tests/conftest.py` has three new fixtures: `phase2_product_attrs_df` (lifecycle dates), `phase2_replenishment_events_df`, `phase2_promotion_rows_df`. Each documented with a docstring giving grain + column names.
- [ ] `uv run pytest app/features/featuresets/tests/test_schemas.py -v` → all green.
- [ ] `uv run pytest app/features/featuresets/ -v` → no regression vs pre-PR (existing tests still pass byte-identically).
- [ ] `uv run ruff check app/features/featuresets/` → clean.
- [ ] `uv run mypy app/features/featuresets/schemas.py` → 0 errors.
- [ ] `uv run pyright app/features/featuresets/schemas.py` → 0 errors.
- [ ] Snapshot proof of additive contract: `FeatureSetConfig(name="x").config_hash()` is byte-identical pre/post PR when no new fields are passed.

---

## All Needed Context

### Documentation & References

```yaml
# MUST READ before writing schemas
- file: app/features/featuresets/schemas.py
  lines: 18-45
  why: FeatureConfigBase — the inheritance target. Provides frozen=True,
       extra="forbid", schema_version regex, and config_hash(). ALL three new
       Configs MUST inherit from this — not BaseModel directly.

- file: app/features/featuresets/schemas.py
  lines: 151-183
  why: ExogenousConfig is the canonical template — mirror its style for
       `Field(default=..., description=...)`, `tuple[int, ...]` for lag/window
       lists, and `@field_validator` to reject zero / empty / negative.

- file: app/features/featuresets/schemas.py
  lines: 95-117
  why: RollingConfig shows the `tuple[Literal["mean","std",...], ...]` pattern
       — use this for PromotionConfig.kinds_to_track (tuple, NOT list — required
       so the frozen model stays hashable and matches the codebase style).

- file: app/features/featuresets/schemas.py
  lines: 212-264
  why: FeatureSetConfig — where the three new optional fields land.
       get_enabled_features at lines 249-264 is the derivation to extend.
       Field-order convention: feature sub-configs declared in execution order.

- file: app/features/featuresets/tests/test_schemas.py
  lines: 107-115
  why: TestExogenousConfig is the exact validation-rejection idiom to copy.
       Use `pytest.raises(ValidationError) as exc_info` + `"positive integers"
       in str(exc_info.value).lower()` style.

- file: app/features/featuresets/tests/conftest.py
  lines: 17-60
  why: sample_time_series + multi_series_time_series are the existing fixture
       patterns. Phase 2 fixtures go in the same file, NOT inside test_leakage.py
       (the INITIAL says test_leakage.py but conftest.py is the project
       convention — see §15 decision A).

- file: app/features/data_platform/models.py
  lines: 80-126
  why: Product table — verified columns for LifecycleConfig: launch_date,
       discontinue_date are both `Date | None` (lines 101-102). lifecycle_stage
       allow-list is 5 values but we DO NOT use the categorical (Decision 1).

- file: app/features/data_platform/models.py
  lines: 274-342
  why: Promotion table — discount_pct is `Numeric(5,4)` 0..1 (line 306),
       kind ∈ {pct_off, bogo, bundle, markdown} via CHECK (line 334). Resolves
       handoff R7 (the placeholder column was `discount_pct`, not `value_pct`).

- file: app/features/data_platform/models.py
  lines: 471-514
  why: ReplenishmentEvent table — `(store_id, product_id, date)` index,
       lead_time_days/ordered_qty/received_qty, with
       received_qty <= ordered_qty check.

- url: https://docs.pydantic.dev/2.10/concepts/models/#strict-mode
  why: Strict-mode behavior and frozen-model semantics — `model_validator`
       return types must be explicit (pyright --strict catches `Any` returns).

- url: https://docs.pydantic.dev/2.10/api/fields/#pydantic.fields.Field
  why: Field(ge=..., le=...) bounds and the constraint reporting that produces
       Pydantic's auto-generated error messages.

- url: https://docs.pydantic.dev/2.10/concepts/types/#literal-types
  why: tuple[Literal[...], ...] support and how Pydantic v2 reports
       allow-list violations.

- docfile: .agents/plans/phase2-decisions-and-prp-prep.md
  why: §1 (lifecycle continuous-only), §3 (PromotionConfig generalization).
       These are the LOCKED decisions overriding the original PRD.

- docfile: .agents/plans/wire-phase2-features-to-featuresets.md
  sections: §7 (feature specs, post-decision shape), §9 (security/config
       boundary rules), §11 (success criteria)
  why: Parent PRD — read §6 "Time-safety contract" before any schema design.

- file: .claude/rules/security-patterns.md
  why: "Allow-lists over deny-lists" — every Literal/tuple must be tight.
       Pydantic v2 validation MUST happen at the boundary (HTTP body).

- file: .claude/rules/test-requirements.md
  why: Leakage tests are load-bearing. Even though this slice writes no
       compute methods, the fixtures it lands ARE the spec for downstream
       slices' leakage cases.
```

### Current Codebase tree (relevant subset)

```bash
app/features/featuresets/
├── __init__.py
├── routes.py             # unchanged in this PRP
├── schemas.py            # +3 classes, +3 fields, +1 enabled_features extension
├── service.py            # unchanged in this PRP
└── tests/
    ├── __init__.py
    ├── conftest.py       # +3 Phase 2-shaped fixtures
    ├── test_leakage.py   # unchanged in this PRP (compute methods not yet here)
    ├── test_schemas.py   # +3 test classes (one per new Config)
    └── test_service.py   # unchanged in this PRP

app/features/data_platform/
└── models.py             # READ ONLY — sources for fixture column shapes
```

### Desired Codebase tree (after this PR)

```bash
app/features/featuresets/
├── schemas.py            # +~75 LOC: 3 new classes + 3 FSC fields + get_enabled_features
└── tests/
    ├── conftest.py       # +~60 LOC: 3 fixtures + their docstrings
    └── test_schemas.py   # +~50 LOC: 3 test classes
```

Net diff target: **≤ 150 LOC** (additions only; no existing line modified except `FeatureSetConfig` field block + the `get_enabled_features` body).

### Known Gotchas & Library Quirks

```python
# CRITICAL: FeatureConfigBase has `model_config = ConfigDict(frozen=True, extra="forbid")`.
#   - `frozen=True` makes instances immutable. Mutating after construction raises
#     ValidationError (NOT TypeError). Your test must assert ValidationError, not
#     AttributeError — see test_schemas.py:201-205 for the existing pattern.
#   - `extra="forbid"` rejects unknown fields at __init__. Your tests should
#     verify this (mirror test_schemas.py:213-215).

# CRITICAL: The frozen-model + hashable invariant means containers MUST be tuples,
#   not lists. ExogenousConfig.price_lags is `tuple[int, ...]`, NOT `list[int]`.
#   PromotionConfig.kinds_to_track MUST be `tuple[Literal[...], ...]`.

# CRITICAL: schema_version inherits from FeatureConfigBase (regex `^\d+\.\d+(\.\d+)?$`).
#   DO NOT redeclare it on the subclass. The base class default of "1.0" applies.

# CRITICAL: `@field_validator` in Pydantic v2 must be `@classmethod`-decorated
#   AND typed as `cls: type[Self]` is forbidden under pyright --strict — use the
#   existing pattern `cls` (untyped, implicit) — see schemas.py:71-79.

# CRITICAL: `Optional[T]` is forbidden by repo style. Use `T | None` (PEP 604).
#   See FeatureSetConfig fields at schemas.py:243-247.

# CRITICAL: `get_enabled_features()` returns `list[str]` and the order matters
#   for tests. Append new tokens after "exogenous"; preserve existing order.

# GOTCHA: The INITIAL says "emit 'markdown'" in get_enabled_features. The
#   decisions log renames MarkdownConfig → PromotionConfig (Decision 3). The
#   CLASS is now `PromotionConfig`, so the family token should be "promotion",
#   not "markdown". See §15 decision B for rationale.

# GOTCHA: `model_validator` return types must be `Self` (from `typing`), not
#   `BaseModel` — pyright --strict reports this otherwise. None of the three
#   Configs need a model_validator (per-field validators suffice); skip them
#   unless cross-field validation is added.

# GOTCHA: Pydantic v2 `field_validator` rejects empty tuples differently from
#   empty lists. For `tuple[int, ...]`, the validator runs on the tuple instance.
#   Match the existing pattern in schemas.py:71-79 exactly.

# GOTCHA: Pyright --strict on `tuple[Literal[...], ...]` types: avoid declaring
#   the validator return type as `tuple[Literal[...], ...]` — it tries to enforce
#   the Literal at runtime and fails. Use `tuple[str, ...]` in the validator
#   signature (Pydantic still narrows at construction).

# CRITICAL FOR FIXTURES: The existing `sample_time_series` produces sequential
#   quantities (1..30). For Phase 2 fixtures, follow the same idiom — use
#   sequential/derivable values per series so any downstream leakage test
#   can mathematically detect contamination (see test_leakage.py:25-51).
```

---

## Implementation Blueprint

### Data models (Pydantic v2)

```python
# app/features/featuresets/schemas.py — additions only, byte-identical above & below

class LifecycleConfig(FeatureConfigBase):
    """Configuration for product-lifecycle features.

    Lifecycle features capture time-since-launch and time-since-discontinue
    as continuous integer date-deltas (NOT categorical stage). LightGBM splits
    discover stage boundaries from the continuous variable naturally — see
    PRP-3.1 decisions log §1.

    All features are derived from product.launch_date and
    product.discontinue_date (both nullable on Phase 2 products).

    Attributes:
        include_days_since_launch: Emit days_since_launch_lag{N} columns.
        include_days_since_discontinue: Emit days_since_discontinue_lag{N}.
        lag_days: Lag offset in days (≥ 1 to prevent leakage).
    """

    include_days_since_launch: bool = True
    include_days_since_discontinue: bool = True
    lag_days: int = Field(default=1, ge=1, le=30, description="Lag offset in days")


class ReplenishmentConfig(FeatureConfigBase):
    """Configuration for replenishment-event features.

    Replenishment features capture inbound-stock cadence via:
      * `days_since_last_replenishment_lag{N}` — gap to previous event
      * `replenishment_count_w{W}_lag{N}` — rolling count over window W

    Source: `replenishment_event` table (separate from sales_daily).
    The JOIN happens in service.py (PRP-3.1C) — this slice only declares
    the contract.

    Attributes:
        include_days_since_last: Emit days_since_last_replenishment_lag{N}.
        include_count_window: Emit replenishment_count_w{W}_lag{N}.
        lag_days: Lag offset (≥ 1).
        count_window_days: Rolling-window size for count features (7-60).
    """

    include_days_since_last: bool = True
    include_count_window: bool = True
    lag_days: int = Field(default=1, ge=1, le=30)
    count_window_days: int = Field(default=14, ge=7, le=60)


class PromotionConfig(FeatureConfigBase):
    """Configuration for generic promotion-family features.

    GENERALIZED from the original MarkdownConfig design (PRP-3.1 decisions
    log §3) to cover all four `promotion.kind` values via one JOIN:
    pct_off | bogo | bundle | markdown. Default `kinds_to_track=("markdown",)`
    preserves the original PRD intent; caller opts in to others.

    Produced columns (per kind in kinds_to_track):
      * `promo_<kind>_active_lag{N}`     — int 0/1
      * `promo_<kind>_intensity_lag{N}`  — float (when include_intensity)

    Intensity source: `promotion.discount_pct` (Numeric(5,4), 0..1 range)
    per data_platform/models.py:306. NULL discounts produce NaN columns.

    Attributes:
        kinds_to_track: Allow-listed promotion kinds (tuple required for
            frozen-model hashability).
        include_active: Emit promo_<kind>_active_lag{N}.
        include_intensity: Emit promo_<kind>_intensity_lag{N}.
        lag_days: Lag offset (≥ 1).
    """

    kinds_to_track: tuple[Literal["pct_off", "bogo", "bundle", "markdown"], ...] = Field(
        default=("markdown",),
        description="Promotion kinds to track (subset of promotion.kind allow-list)",
    )
    include_active: bool = True
    include_intensity: bool = True
    lag_days: int = Field(default=1, ge=1, le=30)

    @field_validator("kinds_to_track")
    @classmethod
    def validate_kinds_non_empty_unique(cls, v: tuple[str, ...]) -> tuple[str, ...]:
        """Reject empty tuple and duplicates."""
        if not v:
            raise ValueError("At least one promotion kind must be specified")
        if len(set(v)) != len(v):
            raise ValueError("Duplicate promotion kinds are not allowed")
        return v
```

### `FeatureSetConfig` extension

```python
# app/features/featuresets/schemas.py — modify in place at the existing class
# Insert AFTER `exogenous_config`, BEFORE `imputation_config`:

class FeatureSetConfig(FeatureConfigBase):
    # ... existing fields above ...

    exogenous_config: ExogenousConfig | None = None
    # --- Phase 2 additions (PRP-3.1A) ---
    lifecycle_config: LifecycleConfig | None = None
    replenishment_config: ReplenishmentConfig | None = None
    promotion_config: PromotionConfig | None = None
    # --- end Phase 2 additions ---
    imputation_config: ImputationConfig | None = None

    def get_enabled_features(self) -> list[str]:
        enabled: list[str] = []
        if self.lag_config:
            enabled.append("lag")
        if self.rolling_config:
            enabled.append("rolling")
        if self.calendar_config:
            enabled.append("calendar")
        if self.exogenous_config:
            enabled.append("exogenous")
        # --- Phase 2 additions (PRP-3.1A) ---
        if self.lifecycle_config:
            enabled.append("lifecycle")
        if self.replenishment_config:
            enabled.append("replenishment")
        if self.promotion_config:
            enabled.append("promotion")
        # --- end Phase 2 additions ---
        return enabled
```

### Phase 2 fixtures (in `conftest.py`)

```python
# Pseudocode — exact column names match the verified DB schema

@pytest.fixture
def phase2_product_attrs_df() -> pd.DataFrame:
    """Phase 2 product lifecycle attributes.

    Shape mirrors `Product` (subset): id, launch_date, discontinue_date.
    Two products: P1 launched 2023-06-01, discontinued 2025-12-31;
                  P2 launched 2024-03-15, still active (discontinue_date=NaT).
    """
    return pd.DataFrame({
        "product_id":       [1, 2],
        "launch_date":      [date(2023, 6, 1), date(2024, 3, 15)],
        "discontinue_date": [date(2025, 12, 31), pd.NaT],
    })


@pytest.fixture
def phase2_replenishment_events_df() -> pd.DataFrame:
    """Phase 2 replenishment events.

    Shape mirrors `ReplenishmentEvent`: store_id, product_id, event_date,
    lead_time_days, ordered_qty, received_qty.
    Three events per (store=1, product=1) on 2024-01-05, 2024-01-12,
    2024-01-26 so PRP-3.1C tests can compute days-since-last + rolling count.
    """
    return pd.DataFrame({
        "store_id":        [1, 1, 1],
        "product_id":      [1, 1, 1],
        "event_date":      [date(2024, 1, 5), date(2024, 1, 12), date(2024, 1, 26)],
        "lead_time_days":  [7, 5, 10],
        "ordered_qty":     [100, 100, 200],
        "received_qty":    [98, 100, 195],
    })


@pytest.fixture
def phase2_promotion_rows_df() -> pd.DataFrame:
    """Phase 2 promotion rows (one row per active campaign).

    Shape mirrors `Promotion` (subset): product_id, store_id, kind,
    discount_pct, start_date, end_date. NULL store_id = chain-wide.
    Mix of kinds to exercise PRP-3.1D's per-kind one-hot branch.
    """
    return pd.DataFrame({
        "product_id":   [1, 1, 2],
        "store_id":     [1, None, 1],            # None = chain-wide
        "kind":         ["markdown", "pct_off", "bogo"],
        "discount_pct": [0.20, 0.10, None],      # bogo has no discount_pct
        "start_date":   [date(2024, 1, 7),  date(2024, 1, 1),  date(2024, 1, 15)],
        "end_date":     [date(2024, 1, 14), date(2024, 1, 31), date(2024, 1, 28)],
    })
```

### List of tasks (in execution order)

```yaml
Task 1 — Add three new *Config classes:
MODIFY app/features/featuresets/schemas.py:
  - FIND pattern: "class ExogenousConfig(FeatureConfigBase):"
  - INJECT new classes AFTER the entire ExogenousConfig class (i.e. after
    line 183 — its closing `return v`) and BEFORE `class ImputationConfig`.
  - Order: LifecycleConfig, ReplenishmentConfig, PromotionConfig.
  - MIRROR style from ExogenousConfig (Field bounds, docstring, validator).
  - PRESERVE all existing class signatures byte-identically.

Task 2 — Extend FeatureSetConfig:
MODIFY app/features/featuresets/schemas.py:
  - FIND pattern: "exogenous_config: ExogenousConfig | None = None"
  - INSERT three new fields AFTER that line, BEFORE
    `imputation_config: ImputationConfig | None = None`.
  - FIND pattern: in `get_enabled_features`, the line
    `if self.exogenous_config:` block.
  - INJECT three new `if self.<family>_config: enabled.append("<token>")`
    blocks AFTER the exogenous block. Tokens in order: "lifecycle",
    "replenishment", "promotion".
  - PRESERVE field order: feature sub-configs in execution order;
    Phase 2 sub-configs slot AFTER exogenous, BEFORE imputation.

Task 3 — Add Phase 2 fixtures to conftest.py:
MODIFY app/features/featuresets/tests/conftest.py:
  - APPEND three new `@pytest.fixture` functions at end-of-file
    (NOT inside a class). Order: phase2_product_attrs_df,
    phase2_replenishment_events_df, phase2_promotion_rows_df.
  - Use sequential-and-derivable values so leakage is mathematically
    detectable in PRP-3.1B/C/D (mirror sample_time_series:25-32 style).
  - Import `from datetime import date` at the top if not already present
    (it is not — sample fixtures use pd.date_range only).

Task 4 — Add per-class schema tests:
MODIFY app/features/featuresets/tests/test_schemas.py:
  - FIND pattern: "class TestExogenousConfig:"
  - APPEND three new classes AFTER the existing TestImputationConfig but
    BEFORE TestFeatureSetConfig:
      * TestLifecycleConfig
      * TestReplenishmentConfig
      * TestPromotionConfig
  - Each class MUST have:
      - test_default_values
      - test_rejects_out_of_bounds_lag_days (ge / le violation)
      - test_rejects_invalid_kind / allow-list violation
        (only TestPromotionConfig)
      - test_frozen_after_construction
  - MIRROR rejection idiom from TestExogenousConfig at lines 110-115.

Task 5 — Extend TestFeatureSetConfig:
MODIFY app/features/featuresets/tests/test_schemas.py:
  - FIND pattern: "def test_get_enabled_features(self):"
  - APPEND a new test in TestFeatureSetConfig:
    `test_get_enabled_features_includes_phase2` — asserts that a config
    with all three new sub-configs returns ["lifecycle","replenishment",
    "promotion"] among the tokens.
  - ADD `test_config_hash_unchanged_when_phase2_omitted` — snapshot
    of `FeatureSetConfig(name="x").config_hash()` against an explicit
    pre-PR value (compute it once locally and inline as a constant
    + comment "regression guard for the additive-contract invariant").

Task 6 — Validation gates (run locally + CI):
RUN:
  uv run ruff check app/features/featuresets/
  uv run ruff format --check app/features/featuresets/
  uv run mypy app/features/featuresets/schemas.py
  uv run pyright app/features/featuresets/schemas.py
  uv run pytest app/features/featuresets/tests/test_schemas.py -v
  uv run pytest app/features/featuresets/ -v   # full module regression
```

### Per-task pseudocode (only where non-obvious)

```python
# Task 1 — LifecycleConfig (the rest of the three follow this shape)
# CRITICAL: inherit FeatureConfigBase, NOT BaseModel.
# CRITICAL: use Pydantic Field(ge=..., le=...) — NOT manual validators — for ints.
class LifecycleConfig(FeatureConfigBase):
    """<docstring as shown above>"""
    include_days_since_launch: bool = True
    include_days_since_discontinue: bool = True
    lag_days: int = Field(default=1, ge=1, le=30, description="Lag offset in days")


# Task 1 — PromotionConfig kinds_to_track validator
# CRITICAL: validator signature uses `tuple[str, ...]` not the Literal-narrowed type
# (pyright --strict won't accept Literal[...] at runtime in validator return).
@field_validator("kinds_to_track")
@classmethod
def validate_kinds_non_empty_unique(cls, v: tuple[str, ...]) -> tuple[str, ...]:
    if not v:
        raise ValueError("At least one promotion kind must be specified")
    if len(set(v)) != len(v):
        raise ValueError("Duplicate promotion kinds are not allowed")
    return v


# Task 4 — TestPromotionConfig pattern (mirror TestExogenousConfig)
class TestPromotionConfig:
    """Tests for PromotionConfig validation."""

    def test_default_values(self):
        config = PromotionConfig()
        assert config.kinds_to_track == ("markdown",)
        assert config.include_active is True
        assert config.include_intensity is True
        assert config.lag_days == 1

    def test_rejects_empty_kinds(self):
        with pytest.raises(ValidationError) as exc_info:
            PromotionConfig(kinds_to_track=())
        assert "at least one promotion kind" in str(exc_info.value).lower()

    def test_rejects_duplicate_kinds(self):
        with pytest.raises(ValidationError) as exc_info:
            PromotionConfig(kinds_to_track=("markdown", "markdown"))
        assert "duplicate" in str(exc_info.value).lower()

    def test_rejects_invalid_kind(self):
        # Allow-list violation handled by Pydantic itself, not the validator.
        with pytest.raises(ValidationError):
            PromotionConfig(kinds_to_track=("invalid_kind",))  # type: ignore[arg-type]

    def test_rejects_lag_days_out_of_bounds(self):
        with pytest.raises(ValidationError):
            PromotionConfig(lag_days=0)
        with pytest.raises(ValidationError):
            PromotionConfig(lag_days=31)

    def test_frozen_after_construction(self):
        config = PromotionConfig()
        with pytest.raises(ValidationError):
            config.lag_days = 7  # type: ignore[misc]


# Task 5 — Snapshot guard for additive-contract invariant
def test_config_hash_unchanged_when_phase2_omitted(self):
    """Regression guard: minimal config's hash must NOT change when new
    Phase 2 fields are added with None defaults. If this fails, the
    additive-contract invariant (PRD §6) is broken."""
    config = FeatureSetConfig(name="x")
    # First-run capture: compute locally, inline the value, freeze it.
    EXPECTED_HASH = "<paste actual hash from first local run>"
    assert config.config_hash() == EXPECTED_HASH, (
        "config_hash changed when no Phase 2 fields were set — "
        "the additive-contract invariant is broken"
    )
```

### Integration Points

```yaml
DATABASE:
  - NO migration required (verified — all Phase 2 columns exist in
    a8b9c0d1e234_add_retail_depth_columns_and_replenishment_event_table.py)

CONFIG:
  - NO new env vars (per PRD §9 — Phase 2 configs are request-body only)

ROUTES:
  - NO changes (the request body is FeatureSetConfig; new optional
    fields are picked up by FastAPI automatically via Pydantic v2)

DOCS:
  - NO docs touched in this slice. PRP-3.1E updates
    docs/PHASE/3-FEATURE_ENGINEERING.md and DOMAIN_MODEL.md after
    the compute methods land.

ALEMBIC:
  - NO new revision. Existing revision a8b9c0d1e234_* covers all columns.

DOWNSTREAM PRPs:
  - PRP-3.1B (lifecycle compute) — depends on LifecycleConfig +
    phase2_product_attrs_df fixture
  - PRP-3.1C (replenishment compute) — depends on ReplenishmentConfig +
    phase2_replenishment_events_df fixture
  - PRP-3.1D (promotion compute) — depends on PromotionConfig +
    phase2_promotion_rows_df fixture
  - PRP-3.1E (E2E + docs) — depends on B, C, D
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
uv run mypy app/features/featuresets/schemas.py
uv run pyright app/features/featuresets/schemas.py

# Expected: 0 errors on each. Common failure modes:
#   - pyright "reportUnknownVariableType" on tuple[Literal[...], ...] —
#     ensure the validator signature uses `tuple[str, ...]`, NOT the
#     Literal-narrowed type.
#   - mypy "incompatible return type" on get_enabled_features —
#     ensure return type stays `list[str]` (do not infer).
```

### Level 3: Unit Tests (new schemas + existing schema regressions)

```bash
# Tests for the new Configs only:
uv run pytest app/features/featuresets/tests/test_schemas.py -v

# Full module sweep — must show 0 regressions in pre-existing tests:
uv run pytest app/features/featuresets/ -v

# If failing: read the error, find root cause (NEVER mock the existing
# fixture infra to pass — the additive-contract invariant is on trial).
```

### Level 4: Additive-contract proof

```bash
# Manual verification before opening PR:
# 1. On the current branch (post-changes), compute the hash:
uv run python -c "
from app.features.featuresets.schemas import FeatureSetConfig
print('post-PR hash:', FeatureSetConfig(name='x').config_hash())
"
# 2. Check out the PR base (dev) and compute the same:
git stash
git switch dev
uv run python -c "
from app.features.featuresets.schemas import FeatureSetConfig
print('pre-PR hash:', FeatureSetConfig(name='x').config_hash())
"
git switch -
git stash pop
# 3. The two hashes MUST match — if not, the additive-contract is broken
#    (one of the new fields has a non-None default or the field order
#    changed model_dump_json output).
```

### Level 5: Integration (HTTP boundary)

```bash
# Start the API:
docker compose up -d
uv run alembic upgrade head
uv run uvicorn app.main:app --reload --port 8123 &
APP_PID=$!

# A pre-PR caller sending no new fields gets byte-identical response shape:
curl -s -X POST http://localhost:8123/featuresets/compute \
  -H "Content-Type: application/json" \
  -d '{"store_id":1,"product_id":1,"cutoff_date":"2024-01-31","config":{"name":"smoke"}}' \
  | jq '.config_hash, .feature_columns'
# Expected: same hash + feature_columns as the same request on `dev` HEAD.

# A new caller sending lifecycle_config gets a VALIDATED config — but since
# this slice has no compute method, expect:
#   - 200 OK with the same response shape (lifecycle config is parsed +
#     stored, but no lifecycle columns appear because the compute method
#     doesn't exist yet)
#   - OR 422 if the Pydantic schema rejects the body.
curl -s -X POST http://localhost:8123/featuresets/compute \
  -H "Content-Type: application/json" \
  -d '{
    "store_id":1,"product_id":1,"cutoff_date":"2024-01-31",
    "config":{
      "name":"phase2-smoke",
      "lifecycle_config":{"include_days_since_launch":true,"lag_days":1}
    }
  }' \
  | jq '.feature_columns | length'
# Expected: same length as the no-config case (compute is not wired yet —
# emit a log line "phase2 config parsed but compute not implemented" if
# you want, but the schema slice deliberately doesn't add compute behavior).

# Invalid bound — Pydantic must reject:
curl -s -X POST http://localhost:8123/featuresets/compute \
  -H "Content-Type: application/json" \
  -d '{
    "store_id":1,"product_id":1,"cutoff_date":"2024-01-31",
    "config":{"name":"bad","lifecycle_config":{"lag_days":0}}
  }' \
  | jq '.title'
# Expected: "validation_error" (RFC 7807 problem+json)

kill $APP_PID
```

---

## Final Validation Checklist

- [ ] All tests pass: `uv run pytest app/features/featuresets/ -v`
- [ ] No linting errors: `uv run ruff check app/features/featuresets/`
- [ ] No formatting drift: `uv run ruff format --check app/features/featuresets/`
- [ ] No mypy errors: `uv run mypy app/features/featuresets/schemas.py`
- [ ] No pyright errors: `uv run pyright app/features/featuresets/schemas.py`
- [ ] Additive-contract proof: `config_hash()` on `FeatureSetConfig(name="x")` is identical pre/post PR (Level 4)
- [ ] HTTP smoke OK: invalid bounds rejected with RFC 7807 (Level 5)
- [ ] Diff stat: ≤ +150 / -5 LOC (verify with `git diff --stat dev...`)
- [ ] Single commit, message: `feat(features): add pydantic configs and leakage fixtures for phase 2 features (#<issue>)` (use the parent issue from handoff Next Step #2)
- [ ] No `service.py` changes, no `routes.py` changes (verify with `git diff dev... -- app/features/featuresets/service.py app/features/featuresets/routes.py` → empty)

---

## Anti-Patterns to Avoid

- ❌ **Do NOT add a compute method.** Even a stub one. This slice is schema + fixtures only. The whole point is parallelism for PRP-3.1B/C/D.
- ❌ **Do NOT use `list[...]` for hashable model fields.** Use `tuple[...]` to match ExogenousConfig.price_lags and RollingConfig.windows.
- ❌ **Do NOT inherit from `BaseModel` directly.** Inherit from `FeatureConfigBase` so frozen + schema_version + config_hash come for free.
- ❌ **Do NOT use `Optional[T]` in fresh code.** Project style is `T | None` (PEP 604).
- ❌ **Do NOT redeclare `schema_version`** on a subclass. The base class default applies.
- ❌ **Do NOT change `FeatureSetConfig` field ordering** for pre-existing fields. Only INSERT new fields between `exogenous_config` and `imputation_config`.
- ❌ **Do NOT add `model_validator` for cross-field invariants** unless one is genuinely required. The three Configs in this slice do NOT need them; per-field validators suffice.
- ❌ **Do NOT touch `test_leakage.py`** in this slice. The compute methods live in PRP-3.1B/C/D; their leakage cases land there.
- ❌ **Do NOT widen `_compute_*` callsites in `compute()`.** No new `if self.config.<...>_config:` branches in service.py here.
- ❌ **Do NOT add an AI co-author trailer** to the commit (forbidden by `.claude/rules/commit-format.md`).

---

## §15 — PRP-Authoring Decisions

These are decisions made during PRP authoring that the INITIAL didn't lock — recorded here so a future session can audit the reasoning.

### Decision A — Fixtures go in `conftest.py`, not `test_leakage.py`

**INITIAL said:** "Shared leakage-test fixtures in `tests/test_leakage.py`."
**Decision:** Put fixtures in `tests/conftest.py`.
**Why:** The existing project convention (`conftest.py` lines 17-60) puts all reusable fixtures there. PRP-3.1B/C/D will write their own `test_leakage.py` cases; making the fixtures discoverable via the same conftest the existing `sample_time_series` lives in keeps the pattern coherent. A fixture defined inside a `test_*.py` file is not auto-discovered by sibling test modules.
**Impact:** Trivial — pure file location.

### Decision B — `get_enabled_features` emits `"promotion"`, not `"markdown"`

**INITIAL said:** Emit `"markdown"` for the promotion family.
**Decisions log said:** Class renamed from `MarkdownConfig` to `PromotionConfig` (Decision 3).
**My call:** Emit `"promotion"`.
**Why:** The token semantically describes the FAMILY (lag, rolling, calendar, exogenous all describe families). The default `kinds_to_track=("markdown",)` is a runtime value of one instance, not a name. Emitting `"markdown"` when the class is `PromotionConfig` and the field is `promotion_config` would be inconsistent. A caller who sets `kinds_to_track=("bogo",)` would still see `"markdown"` in `enabled_features`, which is confusingly misleading.
**Risk if reversed:** Downstream (PRP-3.1D, PRP-3.1E) may key off this token in the registry or docs; switching it later requires a registry-name migration. Locking `"promotion"` now is the additive-safe choice.
**How to apply:** If a reviewer prefers `"markdown"`, the change is a 1-line edit and the test in Task 5 updates accordingly. No downstream blocker.

### Decision C — `kinds_to_track` is `tuple[Literal[...], ...]`, not `list[Literal[...]]`

**INITIAL said:** `list[Literal[...]]`.
**My call:** `tuple[Literal[...], ...]`.
**Why:** `FeatureConfigBase` is `frozen=True`. Frozen Pydantic models with list-typed fields work, but lists in a hashed model defeat the "deterministic hash" guarantee of `config_hash()` because `model_dump_json` serializes lists order-preservingly while semantically order-irrelevant — two configs with the same kinds in different orders would have different hashes. Tuples force the caller to commit to an ordering; combined with the `validate_kinds_non_empty_unique` validator, this matches how `RollingConfig.aggregations` (line 99) is shaped — a tuple of Literals.
**How to apply:** If a caller passes a list, Pydantic v2 coerces to tuple at validation. No public-API regression.

### Decision D — No HTTP behavior change for unconsumed Phase 2 configs

**Question raised in Level 5:** What does the API do when a caller sends `lifecycle_config` but no compute method exists yet?
**My call:** Accept the body, validate it, store it on the parsed `FeatureSetConfig`, ignore it in compute. No 400, no warning header.
**Why:** This matches the additive-contract principle — pre-PR callers get byte-identical responses; new callers get a parsed-and-validated config object that has no observable effect until PRP-3.1B/C/D land. Adding a "not implemented yet" 501 would couple this slice to the others, defeating the parallelism goal.
**Mitigation:** An optional log line (`logger.info("featuresets.phase2_config_parsed_but_compute_pending", ...)`) is acceptable but NOT required. Skip if it bloats the diff.

---

## §16 — Open Questions for the Implementing Agent

None. All four PRD-level open questions were resolved in the decisions log:

- Q1 (lifecycle encoding) — resolved: continuous-only, no categorical
- Q2 (markdown vs bundles) — resolved: PromotionConfig handles all kinds
- Q3 (PRP path) — resolved: `PRPs/PRP-3.1A-pydantic-configs-phase2-features.md` (this file)
- R7 (`Promotion.value_pct` column name) — resolved during PRP research: the actual column is `discount_pct` (Numeric(5,4), 0..1), verified at `app/features/data_platform/models.py:306`

If a downstream surprise emerges (the diff exceeds 150 LOC, a validator turns out to need a `model_validator`, or `pyright --strict` flags a Literal-tuple combination), STOP and ask before resolving — don't quietly weaken the schema.

---

## Confidence Score: 9 / 10

**Why 9, not 10:**
- ✅ All file paths verified (no dead references).
- ✅ All DB column names verified against `data_platform/models.py` (including the R7 resolution).
- ✅ Exact line numbers cited for every pattern source.
- ✅ Locked decisions explicitly carried forward from `phase2-decisions-and-prp-prep.md`.
- ✅ Validation gates are deterministic and executable as-written.
- ✅ Additive-contract invariant has a snapshot test guarding it.
- ⚠️ The one residual risk: `pyright --strict` reaction to `tuple[Literal["a","b","c","d"], ...]` in field validator return types varies by pyright version. Mitigation in Gotchas (use `tuple[str, ...]` in validator signature). If pyright still complains, fall back to a model-level `@model_validator(mode="after")` for the kinds check.

Goal achieved: an implementing agent with no prior session context can read this PRP, edit 2 files, run 5 commands, and ship a green PR.
