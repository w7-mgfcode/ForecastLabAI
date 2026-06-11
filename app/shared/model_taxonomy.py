"""Model-family taxonomy shared across slices (#268).

``ModelFamily`` + ``model_family_for`` moved here from the forecasting slice
(``forecasting/schemas.py:617`` / ``forecasting/feature_metadata.py:38``):
``registry.schemas`` needs ``ModelFamily`` at module scope for the
``RunResponse.model_family`` computed field, and while the enum lived inside
a feature slice that one eager import forced lazy-import workarounds across
the registry boundary (the forecasting↔registry alembic cold-boot cycle).
A neutral ``app/shared`` home keeps the import graph one-way:
``app/features/* → app/shared`` only.
"""

from __future__ import annotations

from enum import Enum

from app.core.logging import get_logger

logger = get_logger(__name__)


class ModelFamily(str, Enum):
    """Classifier for advanced-model UI surfacing.

    Derived from ``model_type``; not persisted in the DB. Surfaced on
    ``RunResponse`` via a computed field and consumed by the dashboard for the
    family Badge and the feature-importance panel routing. Unknown model types
    classify as ``BASELINE`` (forward-compatible for new families before the
    map below is updated).
    """

    BASELINE = "baseline"  # naive, seasonal_naive, moving_average
    TREE = "tree"  # regression (HistGBR), lightgbm, xgboost
    ADDITIVE = "additive"  # prophet_like (Ridge pipeline)


# Canonical map: model_type string → ModelFamily. Unknown types log a warning
# and classify as BASELINE. Keep in sync with the ``ModelType`` Literal in
# ``app/features/forecasting/models.py``.
_MODEL_FAMILY_MAP: dict[str, ModelFamily] = {
    "naive": ModelFamily.BASELINE,
    "seasonal_naive": ModelFamily.BASELINE,
    "moving_average": ModelFamily.BASELINE,
    "weighted_moving_average": ModelFamily.BASELINE,
    "seasonal_average": ModelFamily.BASELINE,
    "trend_regression_baseline": ModelFamily.ADDITIVE,
    "random_forest": ModelFamily.TREE,
    "regression": ModelFamily.TREE,
    "lightgbm": ModelFamily.TREE,
    "xgboost": ModelFamily.TREE,
    "prophet_like": ModelFamily.ADDITIVE,
}


def model_family_for(model_type: str) -> ModelFamily:
    """Return the :class:`ModelFamily` for a given ``model_type`` string.

    Unknown types log a warning and return :attr:`ModelFamily.BASELINE` so a
    new model registered in :mod:`forecasting.models` before this map is
    updated does not raise — it just shows up in the dashboard as a baseline
    until the map catches up.
    """
    family = _MODEL_FAMILY_MAP.get(model_type)
    if family is None:
        logger.warning(
            "forecasting.unknown_model_family",
            model_type=model_type,
            fallback=ModelFamily.BASELINE.value,
        )
        return ModelFamily.BASELINE
    return family
