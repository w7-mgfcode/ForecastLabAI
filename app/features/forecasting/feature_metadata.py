"""Pure-function feature-importance extraction for advanced-model runs.

This module surfaces what every feature-aware forecaster (PRP-29 / PRP-30 /
PRP-MLZOO-C1 / PRP-MLZOO-C2) already exposes on its fitted estimator
(``.feature_importances_`` for the tree models, ``coef_`` for the additive
prophet_like Ridge) into a JSON-ready :class:`FeatureImportanceItem` list the
dashboard can render.

No I/O, no FastAPI, no DB — pure functions. The lightgbm and xgboost packages
are NOT imported at module scope: the wrapper classes
(:class:`LightGBMForecaster` etc.) are always importable from
``forecasting.models`` because the lazy ``import`` lives inside ``fit``, and
reading ``.feature_importances_`` off an *already-unpickled* estimator does
not require re-importing the library.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import numpy as np
import structlog

from app.features.forecasting.models import (
    LightGBMForecaster,
    ProphetLikeForecaster,
    RegressionForecaster,
    XGBoostForecaster,
)
from app.features.forecasting.schemas import FeatureImportanceItem, ModelFamily

if TYPE_CHECKING:
    from app.features.forecasting.models import BaseForecaster

logger = structlog.get_logger(__name__)


# Canonical map: model_type string → ModelFamily. Unknown types log a warning
# and classify as BASELINE (forward-compatible for new families before this
# map is updated). Keep in sync with the ``ModelType`` Literal in
# ``forecasting/models.py`` (line 1133-1135).
_MODEL_FAMILY_MAP: dict[str, ModelFamily] = {
    "naive": ModelFamily.BASELINE,
    "seasonal_naive": ModelFamily.BASELINE,
    "moving_average": ModelFamily.BASELINE,
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


class FeatureImportanceUnavailableError(ValueError):
    """The estimator does not expose a usable feature-importance vector.

    Subclass of :class:`ValueError` so existing ``except ValueError`` clauses
    keep working; the service layer uses ``isinstance`` to map this specific
    case to a 422 :class:`~app.core.exceptions.UnprocessableEntityError`
    (resource-state) instead of the 400 it maps other ``ValueError`` raises
    to. The clearest example is
    ``sklearn.ensemble.HistGradientBoostingRegressor`` — a histogram-based
    booster that, unlike its tree cousin :class:`GradientBoostingRegressor`,
    does NOT expose ``feature_importances_``.
    """


def importance_type_for(model: BaseForecaster) -> str | None:
    """Return the importance kind the dashboard should label the values with.

    - LightGBM: ``importance_type`` attribute (default ``'split'``).
    - XGBoost: ``importance_type`` attribute (default ``'weight'`` — but the
      sklearn-API wrapper exposes ``None`` on a freshly-constructed instance,
      so we fall back to the documented XGBoost default).
    - :class:`RegressionForecaster` (``HistGradientBoostingRegressor``):
      ``'permutation'`` — the only honest label we can give a HistGBR fit
      whose ``feature_importances_`` we never get to read (see
      :class:`FeatureImportanceUnavailableError`).
    - :class:`ProphetLikeForecaster`: ``'ridge_coef'``.
    - Anything else: ``None``.
    """
    if isinstance(model, LightGBMForecaster):
        return getattr(model._estimator, "importance_type", None) or "split"  # pyright: ignore[reportPrivateUsage]
    if isinstance(model, XGBoostForecaster):
        return getattr(model._estimator, "importance_type", None) or "weight"  # pyright: ignore[reportPrivateUsage]
    if isinstance(model, RegressionForecaster):
        return "permutation"
    if isinstance(model, ProphetLikeForecaster):
        return "ridge_coef"
    return None


def extract_feature_importance(
    model: BaseForecaster,
    feature_columns: list[str],
) -> list[FeatureImportanceItem]:
    """Extract a sorted :class:`FeatureImportanceItem` list from a fitted model.

    Branches on the concrete forecaster class:

    - :class:`LightGBMForecaster` / :class:`XGBoostForecaster` /
      :class:`RegressionForecaster` → ``estimator.feature_importances_``
      (non-negative; ``kind='tree'``).
    - :class:`ProphetLikeForecaster` → ``pipeline.named_steps['ridge'].coef_``
      (signed; ``kind='linear_coef'``). The sign carries directional
      information and MUST be preserved end-to-end.

    Items are sorted by ``|importance|`` descending and 1-indexed ``rank``.

    Args:
        model: A fitted feature-aware forecaster. Caller must ensure the
            estimator is fitted; this function does not check.
        feature_columns: The canonical column order the model was trained on
            (always 14 for v0.2.16 — see
            ``app/shared/feature_frames/contract.py``).

    Returns:
        A list of :class:`FeatureImportanceItem`, length matching
        ``feature_columns``, sorted by ``|importance|`` desc with 1-indexed
        ``rank``.

    Raises:
        ValueError: If ``model`` is not one of the four feature-aware classes,
            or if the importance vector length does not match
            ``feature_columns``.
    """
    raw: np.ndarray[Any, np.dtype[np.floating[Any]]]
    kind: str
    if isinstance(model, (LightGBMForecaster, XGBoostForecaster, RegressionForecaster)):
        estimator: Any = model._estimator  # pyright: ignore[reportPrivateUsage]
        # HistGradientBoostingRegressor (RegressionForecaster's wrapped
        # estimator) does NOT expose ``feature_importances_`` — it is the one
        # tree-family booster that doesn't. Surface this as a dedicated
        # 422-eligible error rather than the generic AttributeError sklearn
        # would otherwise throw, so the route can render a clear
        # remediation hint.
        if not hasattr(estimator, "feature_importances_"):
            raise FeatureImportanceUnavailableError(
                f"Feature importance is not available for "
                f"{type(estimator).__name__}. Histogram-based boosters "
                "(HistGradientBoostingRegressor) do not expose "
                "feature_importances_; use lightgbm or xgboost for native "
                "tree-importance, or prophet_like for signed coefficients."
            )
        raw = np.asarray(estimator.feature_importances_, dtype=np.float64)
        kind = "tree"
    elif isinstance(model, ProphetLikeForecaster):
        # MIRROR models.py:1094-1098 — drill into the Ridge step of the
        # Pipeline. The `.coef_` here is signed, shape (n_kept_features,).
        #
        # GOTCHA: sklearn's `SimpleImputer(strategy="median")` (default
        # ``keep_empty_features=False`` since 1.2) DROPS columns whose
        # training values are all-NaN. The downstream Ridge therefore
        # learns one fewer coefficient than the bundle's input contract
        # (``feature_columns``) advertises. We realign by inspecting the
        # imputer's ``statistics_`` (length = n_features_in_, NaN entries
        # mark dropped columns) and padding the coef vector back to the
        # full input width with 0.0 for dropped columns — an honest
        # "the model assigned no weight to this feature because the
        # training data had no observed values for it" signal.
        estimator = model._estimator  # pyright: ignore[reportPrivateUsage]
        imputer: Any = estimator.named_steps["impute"]
        ridge: Any = estimator.named_steps["ridge"]
        coef = np.asarray(ridge.coef_, dtype=np.float64)
        stats = np.asarray(imputer.statistics_, dtype=np.float64)
        kept_mask = ~np.isnan(stats)
        if coef.shape[0] == stats.shape[0]:
            # No columns were dropped by the imputer — coef already aligns.
            raw = coef
        elif int(kept_mask.sum()) == coef.shape[0]:
            # Pad coef back to the full input width, 0.0 for dropped columns.
            raw = np.zeros(stats.shape[0], dtype=np.float64)
            raw[kept_mask] = coef
        else:
            raise FeatureImportanceUnavailableError(
                f"ProphetLike coefficient/imputer alignment failed: ridge.coef_ "
                f"has {coef.shape[0]} entries, imputer kept "
                f"{int(kept_mask.sum())} of {stats.shape[0]} columns. "
                "The bundle metadata cannot be reconciled with the fitted "
                "estimator's shape; re-train the model with a recent "
                "scikit-learn version."
            )
        kind = "linear_coef"
    else:
        raise ValueError(
            f"model_type '{type(model).__name__}' is not feature-aware; "
            "feature importance is available for LightGBM, XGBoost, "
            "RegressionForecaster, and ProphetLikeForecaster only."
        )

    if len(raw) != len(feature_columns):
        raise ValueError(
            f"feature_columns length mismatch: importance vector has {len(raw)} "
            f"elements, feature_columns has {len(feature_columns)}"
        )

    # Sort by absolute magnitude descending; preserve sign in the value for
    # linear_coef. argsort returns ascending indices, so we negate the abs
    # vector to flip the order in one pass.
    indices_by_magnitude = np.argsort(-np.abs(raw))
    items: list[FeatureImportanceItem] = [
        FeatureImportanceItem(
            name=feature_columns[int(idx)],
            importance=float(raw[int(idx)]),
            kind="tree" if kind == "tree" else "linear_coef",
            rank=rank,
        )
        for rank, idx in enumerate(indices_by_magnitude, start=1)
    ]
    return items
