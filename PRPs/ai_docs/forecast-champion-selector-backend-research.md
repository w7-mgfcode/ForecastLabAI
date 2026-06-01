# Forecast Champion Selector Backend Research

Date: 2026-06-01

This note captures external-library and runtime facts used by
`PRPs/forecast-champion-selector-backend.md`. It is intentionally narrow:
only claims that affect backend implementation are recorded here.

## Official Documentation References

- FastAPI APIRouter / multi-file apps:
  https://fastapi.tiangolo.com/tutorial/bigger-applications/
  - Reason: the new `app/features/model_selection/routes.py` must follow the
    existing `APIRouter(prefix=..., tags=...)` slice pattern and be wired in
    `app/main.py`.

- Pydantic v2 strict mode and field-level overrides:
  https://pydantic.dev/docs/validation/latest/concepts/strict_mode/
  - Reason: ForecastLabAI request schemas use `ConfigDict(strict=True)`, but
    JSON request bodies still need date/datetime/UUID/Decimal fields to accept
    JSON-native strings via `Field(strict=False, ...)`.

- SQLAlchemy 2.0 PostgreSQL JSONB:
  https://docs.sqlalchemy.org/en/20/dialects/postgresql.html#json-types
  - Reason: `model_selection_run` should store immutable request/response
    snapshots (`candidate_models`, `ranking_result`, `winner_metrics`,
    `forecast_result`, `business_summary`) as PostgreSQL JSONB.

- Alembic `Operations.create_index`:
  https://alembic.sqlalchemy.org/en/latest/ops.html#alembic.operations.Operations.create_index
  - Reason: the migration should use explicit named indexes; any partial or
    JSONB index must use Alembic operations rather than raw SQL.

- scikit-learn `TimeSeriesSplit`:
  https://scikit-learn.org/stable/modules/generated/sklearn.model_selection.TimeSeriesSplit.html
  - Reason: the selector's recommended split defaults mirror the project's
    own `SplitConfig` semantics and should not assume unsupported parameters.

## Runtime Verification Commands

Run from repository root on 2026-06-01.

```bash
uv run python -c "import inspect; from sqlalchemy import select, table, column; import sqlalchemy; stmt=select(column('id')).select_from(table('t')).with_for_update(skip_locked=True); print('sqlalchemy', sqlalchemy.__version__); print('with_for_update_has_skip_locked', 'skip_locked' in str(inspect.signature(select(column('id')).with_for_update))); print(stmt)"
```

Observed:

```text
sqlalchemy 2.0.46
with_for_update_has_skip_locked True
SELECT id
FROM t FOR UPDATE
```

Note: generic SQL compilation does not render PostgreSQL-specific
`SKIP LOCKED`; use PostgreSQL dialect compilation in tests when asserting
that string.

```bash
uv run python -c "from datetime import date; import pydantic; from pydantic import BaseModel, ConfigDict, Field; M=type('M',(BaseModel,),{'__annotations__':{'d':date},'model_config':ConfigDict(strict=True),'d':Field(strict=False)}); print('pydantic', pydantic.__version__); print(M.model_validate({'d':'2026-06-01'}).d.isoformat())"
```

Observed:

```text
pydantic 2.12.5
2026-06-01
```

```bash
uv run python -c "import inspect, sklearn; from sklearn.model_selection import TimeSeriesSplit; print('sklearn', sklearn.__version__); print(inspect.signature(TimeSeriesSplit)); t=TimeSeriesSplit(n_splits=3, test_size=2, gap=1); print(t)"
```

Observed:

```text
sklearn 1.8.0
(n_splits=5, *, max_train_size=None, test_size=None, gap=0)
TimeSeriesSplit(gap=1, max_train_size=None, n_splits=3, test_size=2)
```

```bash
uv run python -c "import inspect, fastapi; from fastapi import APIRouter, BackgroundTasks; print('fastapi', fastapi.__version__); print('APIRouter_prefix_param', 'prefix' in inspect.signature(APIRouter).parameters); print('BackgroundTasks_add_task', inspect.signature(BackgroundTasks.add_task))"
```

Observed:

```text
fastapi 0.128.0
APIRouter_prefix_param True
BackgroundTasks_add_task (self, func: ..., *args: P.args, **kwargs: P.kwargs) -> None
```

```bash
uv run python -c "import inspect, alembic; from alembic.operations import Operations; print('alembic', alembic.__version__); print(inspect.signature(Operations.create_index))"
```

Observed:

```text
alembic 1.18.4
(self, index_name, table_name, columns, *, schema=None, unique=False, if_not_exists=None, **kw) -> None
```

## Implementation Consequences

- Use `Literal[...]` request fields for JSON string enums under
  `ConfigDict(strict=True)`; convert to ORM enums at service boundaries.
- Use `Field(strict=False, ...)` on every request-body date/datetime/UUID/
  Decimal field, or `app/core/tests/test_strict_mode_policy.py` can fail.
- Persist selector decisions in JSONB snapshots because registry metrics are
  free-form JSONB and metric key names differ across layers.
- Do not assume a batch backtest item contains fold-level chart data. Batch
  metrics are intentionally pinned to `{wape, smape, mae, bias, sample_size}`.
- If an implementation compiles SQL for PostgreSQL-specific clauses, compile
  with the PostgreSQL dialect rather than relying on generic SQL strings.

## Verified Internal Service Contracts (read from source 2026-06-01)

These are the in-repo signatures the selector orchestrates. They were the prior
draft's #1 residual risk; recorded here so they survive and can be re-verified on
refactor. Re-verify with `grep -n "async def run_backtest\|async def train_model\|async def predict" app/features/backtesting/service.py app/features/forecasting/service.py`.

### BacktestingService — `app/features/backtesting/service.py:213`

```python
# __init__(self) -> None  — takes NO db; instantiate as BacktestingService()
async def run_backtest(
    self, db: AsyncSession, store_id: int, product_id: int,
    start_date: date, end_date: date, config: BacktestConfig,
) -> BacktestResponse
```

`BacktestConfig` (`backtesting/schemas.py:81`, `frozen=True, extra="forbid"`):
`split_config: SplitConfig`, `model_config_main: Annotated[ModelConfig, Field(discriminator="model_type")]`,
`include_baselines: bool = True`, `store_fold_details: bool = True`.

`SplitConfig` (`:24`): `strategy: Literal["expanding","sliding"]="expanding"`,
`n_splits: int=5 (ge=2,le=20)`, `min_train_size: int=30 (ge=7)`, `gap: int=0 (ge=0,le=30)`,
`horizon: int=14 (ge=1,le=90)`; validator `horizon > gap`.

### BacktestResponse — `backtesting/schemas.py:257`

`main_model_results: ModelBacktestResult`, `baseline_results: list[ModelBacktestResult] | None`,
plus `backtest_id, store_id, product_id, config_hash, split_config, comparison_summary,
duration_ms, leakage_check_passed`.

`ModelBacktestResult` (`:180`): `model_type, config_hash, fold_results: list[FoldResult],
aggregated_metrics: dict[str,float], metric_std: dict[str,float],
bucketed_aggregated_metrics: dict|None, feature_aware: bool, exogenous_policy`.

`FoldResult` (`:147`): `fold_index, split, dates: list[date], actuals: list[float],
predictions: list[float], metrics: dict[str,float], horizon_bucket_metrics`.

**Metric keys (CORRECTION to the prior draft):** `aggregated_metrics` has **five** keys —
`{"mae", "rmse", "smape", "wape", "bias"}` (`backtesting/metrics.py:347`; PRP-36 added `rmse`).
`metric_std` keys are suffixed `"{name}_stability"` (a coefficient of variation, not a raw std).
`sample_size` is NOT in `aggregated_metrics` — derive from fold actuals length or n_folds.
Fold chart data path: `main_model_results.fold_results[i].{dates,actuals,predictions}` — populated
only when `config.store_fold_details=True`.

### ForecastingService — `app/features/forecasting/service.py`

```python
# __init__(self) -> None
async def train_model(                                            # :247
    self, db: AsyncSession, store_id: int, product_id: int,
    train_start_date: date, train_end_date: date, config: ModelConfig,
    *, feature_frame_version: int = 1, feature_groups: list[str] | None = None,
) -> TrainResponse                                                # TrainResponse.model_path is the artifact path

async def predict(                                                # :402  — NO db arg
    self, store_id: int, product_id: int, horizon: int, model_path: str,
) -> PredictResponse                                              # PredictResponse.forecasts: list[ForecastPoint]
```

`predict()` rejects feature-aware models (`service.py:491`) — feature-aware winners must route
through `/scenarios/simulate`; catch and warn rather than 500.

### ModelConfig union — `forecasting/schemas.py:417`

Plain PEP 604 union (`NaiveModelConfig | SeasonalNaiveModelConfig | … | ProphetLikeModelConfig`),
discriminated by each member's `model_type` Literal. Members are **flat** (`SeasonalNaiveModelConfig`
has `model_type` + `season_length`, NOT a nested `params`). No module-level `TypeAdapter`/helper.
Build from `{"model_type": ..., "params": {...}}` by FLATTENING:

```python
from pydantic import TypeAdapter
from app.features.forecasting.schemas import ModelConfig
TypeAdapter(ModelConfig).validate_python({"model_type": c.model_type, **c.params})
```

Members are `frozen=True, extra="forbid"` → bad params raise `ValidationError` (treat as a failed
candidate). `model_type` values: `naive, seasonal_naive, moving_average, weighted_moving_average,
seasonal_average, trend_regression_baseline, random_forest, lightgbm, xgboost, regression,
prophet_like` (`lightgbm`/`xgboost` are opt-in extras → may `ImportError`).

### Data-platform ORM column names — `data_platform/models.py`

`Store` (`:40`): `id` (int PK), `code` (business key — NOT `store_code`). `Product` (`:68`): `id`,
`sku`, `launch_date: date|None`. `SalesDaily` (`:172`): `date` (FK calendar.date), `store_id`,
`product_id`, `quantity` (Integer, CHECK ≥0), `unit_price`, `total_amount`; grain unique
`(date, store_id, product_id)`. `Promotion` (`:274`): `product_id` NOT NULL, `store_id` NULLABLE
(NULL = chain-wide, applies to all stores), date RANGE `[start_date, end_date]`,
`kind ∈ {pct_off,bogo,bundle,markdown}`.

### Cross-cutting patterns

- Exceptions (`app/core/exceptions.py`): `BadRequestError`(400), `NotFoundError`(404),
  `DatabaseError`(500), `ConflictError`(409), `UnprocessableEntityError`(422); each
  `(message=..., details=None)`. Routes map `ValueError→BadRequestError`,
  `SQLAlchemyError→DatabaseError` (mirror `backtesting/routes.py:60`).
- `validate_date_range` is slice-local in `analytics/routes.py:36` (raises `BadRequestError`,
  inverted-range + 730-day-max) — NOT importable cross-slice; reimplement locally.
- `TimestampMixin` (`app/shared/models.py`): `created_at`/`updated_at`, `server_default func.now()`,
  `updated_at onupdate func.now()`. Mix in first: `class X(TimestampMixin, Base)`.
- JSONB import differs: migration `from sqlalchemy.dialects import postgresql` →
  `postgresql.JSONB(astext_type=sa.Text())`; ORM `from sqlalchemy.dialects.postgresql import JSONB`.
- `app/main.py` wires routers as `from app.features.<slice>.routes import router as <slice>_router`
  + `app.include_router(<slice>_router)` (NO prefix at include; the router carries it).
- Current alembic head observed: `c1d2e3f40512` (`create_batch_tables`).
