"""Pure model-capability catalog for the champion selector (issue #356, Slice A).

No DB, no I/O — :func:`build_model_catalog` is deterministic and unit-tested
directly (mirrors ``ranking.py`` / ``explanations.py``). It surfaces the
forecasting model union as a frontend-consumable catalog so the React
``MODEL_FAMILY_MAP`` / labels never drift from the Python authority.

Capability provenance (BACKEND-OWNED, verified 2026-06-01):
- ``family``         — ``forecasting.feature_metadata.model_family_for`` (lazy
  cross-slice import inside the builder, per the slice's import discipline).
- ``feature_aware``  — the set whose forecasters set ``requires_features=True``
  (RandomForest/Regression/LightGBM/XGBoost/ProphetLike), i.e. exactly the set
  ``ForecastingService.predict()`` rejects (``forecasting/service.py``).
- ``requires_extra`` — ``lightgbm``/``xgboost`` (opt-in extras that may
  ``ImportError`` when the extra is not installed).
- ``supports_auto_predict`` — ``not feature_aware`` (feature-aware winners
  forecast through ``POST /scenarios/simulate``, not the plain predict path).
- ``default_params``  — the FLAT model-tuning defaults pinned from the live
  ``forecasting.schemas.ModelConfig`` members (the internal ``schema_version``
  and ``feature_config_hash`` meta fields are intentionally omitted).
"""

from __future__ import annotations

from dataclasses import dataclass, field

from app.features.model_selection.schemas import (
    CandidateModelInfo,
    ModelCatalogResponse,
)

# Models gated behind the matching opt-in extra (may be absent at runtime).
_REQUIRES_EXTRA: frozenset[str] = frozenset({"lightgbm", "xgboost"})

# Feature-aware models — their forecasters set ``requires_features=True`` and
# ``ForecastingService.predict()`` rejects them (they need an exogenous feature
# frame). Verified against ``forecasting/models.py`` requires_features flags.
_FEATURE_AWARE: frozenset[str] = frozenset(
    {"regression", "prophet_like", "lightgbm", "xgboost", "random_forest"}
)

# The default candidate set the backend ``POST /run`` contract documents — the
# UI pre-selects exactly these.
DEFAULT_CANDIDATE_MODEL_TYPES: list[str] = [
    "naive",
    "seasonal_naive",
    "moving_average",
    "regression",
    "prophet_like",
]


@dataclass(frozen=True)
class _CatalogEntry:
    """Slice-local presentation metadata for one model_type."""

    label: str
    description: str
    default_params: dict[str, object] = field(default_factory=lambda: {})


# Ordered map: model_type → presentation metadata. The KEYS must equal the
# ``ModelType`` Literal in ``schemas.py`` exactly (asserted in
# ``test_capabilities.py``). ``default_params`` are the flat model-tuning
# defaults from the forecasting ``ModelConfig`` members (schema_version /
# feature_config_hash meta fields omitted), pinned 2026-06-01.
_CATALOG: dict[str, _CatalogEntry] = {
    "naive": _CatalogEntry(
        label="Naive",
        description="Repeats the last observed value.",
    ),
    "seasonal_naive": _CatalogEntry(
        label="Seasonal Naive",
        description="Repeats the value from one season ago.",
        default_params={"season_length": 7},
    ),
    "moving_average": _CatalogEntry(
        label="Moving Average",
        description="Averages the last N observed values.",
        default_params={"window_size": 7},
    ),
    "weighted_moving_average": _CatalogEntry(
        label="Weighted Moving Average",
        description="Recency-weighted average of the last N values.",
        default_params={"window_size": 7, "weight_strategy": "linear", "decay": 0.7},
    ),
    "seasonal_average": _CatalogEntry(
        label="Seasonal Average",
        description="Averages the same season-position across recent cycles.",
        default_params={"season_length": 7, "lookback_cycles": 4, "trim_outliers": False},
    ),
    "trend_regression_baseline": _CatalogEntry(
        label="Trend Regression Baseline",
        description="Ridge trend with optional day-of-week / month terms.",
        default_params={"alpha": 1.0, "include_dow": True, "include_month": True},
    ),
    "random_forest": _CatalogEntry(
        label="Random Forest",
        description="Feature-aware random-forest regressor over lag/calendar features.",
        default_params={"n_estimators": 100, "max_depth": 10, "min_samples_leaf": 2},
    ),
    "lightgbm": _CatalogEntry(
        label="LightGBM",
        description="Gradient-boosted trees (opt-in extra) over engineered features.",
        default_params={"n_estimators": 100, "max_depth": 6, "learning_rate": 0.1},
    ),
    "xgboost": _CatalogEntry(
        label="XGBoost",
        description="Extreme gradient boosting (opt-in extra) over engineered features.",
        default_params={"n_estimators": 100, "max_depth": 6, "learning_rate": 0.1},
    ),
    "regression": _CatalogEntry(
        label="Gradient Boosting Regression",
        description="Histogram gradient-boosting over lag, calendar, and exogenous features.",
        default_params={"max_iter": 200, "learning_rate": 0.05, "max_depth": 6},
    ),
    "prophet_like": _CatalogEntry(
        label="Prophet-like Additive",
        description="Additive trend/seasonality Ridge over engineered features.",
        default_params={"alpha": 1.0},
    ),
}


def build_model_catalog() -> ModelCatalogResponse:
    """Build the backend-owned candidate-model catalog (pure, no I/O).

    Iterates the slice-local ``_CATALOG`` in declaration order, deriving each
    entry's ``family`` from the forecasting authority and its capability flags
    from the module-level sets. Returns the full catalog plus the documented
    default candidate set.
    """
    # Lazy cross-slice import (mirror service.py) — avoids closing an alembic
    # cold-boot import cycle through the forecasting slice.
    from app.features.forecasting.feature_metadata import model_family_for

    models: list[CandidateModelInfo] = []
    for model_type, meta in _CATALOG.items():
        feature_aware = model_type in _FEATURE_AWARE
        models.append(
            CandidateModelInfo(
                model_type=model_type,
                label=meta.label,
                # ``ModelFamily`` is a ``str, Enum`` whose ``.value`` is already
                # typed as the ``baseline|tree|additive`` literal the schema wants.
                family=model_family_for(model_type).value,
                feature_aware=feature_aware,
                requires_extra=model_type in _REQUIRES_EXTRA,
                default_params=dict(meta.default_params),
                supports_auto_predict=not feature_aware,
                description=meta.description,
            )
        )
    return ModelCatalogResponse(
        models=models,
        default_candidate_model_types=list(DEFAULT_CANDIDATE_MODEL_TYPES),
    )
