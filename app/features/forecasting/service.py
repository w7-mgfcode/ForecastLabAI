"""Forecasting service for model training and prediction.

Orchestrates:
- Loading training data from database
- Model instantiation via factory
- Training and prediction
- Model persistence via ModelBundle

CRITICAL: All operations respect time-safety constraints.
"""

from __future__ import annotations

import math
import time
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from datetime import date as date_type
from pathlib import Path
from typing import TYPE_CHECKING, Any

import numpy as np
import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.features.data_platform.models import Calendar, Product, Promotion, SalesDaily
from app.features.forecasting.models import model_factory
from app.features.forecasting.persistence import (
    ModelBundle,
    load_model_bundle,
    save_model_bundle,
)
from app.features.forecasting.schemas import (
    ForecastPoint,
    ModelConfig,
    PredictResponse,
    TrainResponse,
)
from app.shared.feature_frames import (
    CALENDAR_COLUMNS,
    EXOGENOUS_LAGS,
    HISTORY_TAIL_DAYS,
    build_calendar_columns,
    canonical_feature_columns,
)

if TYPE_CHECKING:
    pass

logger = structlog.get_logger()


@dataclass
class TrainingData:
    """Container for loaded training data.

    Attributes:
        y: Target values as numpy array.
        dates: Corresponding dates.
        store_id: Store ID.
        product_id: Product ID.
        n_observations: Number of observations.
    """

    y: np.ndarray[Any, np.dtype[np.floating[Any]]]
    dates: list[date_type]
    store_id: int
    product_id: int
    n_observations: int = field(init=False)

    def __post_init__(self) -> None:
        """Compute derived fields."""
        self.n_observations = len(self.y)


# Minimum observed rows required to train a regression model — enough to
# resolve the lag features and still leave training signal (PRP-27 GOTCHA #14).
_MIN_REGRESSION_TRAIN_ROWS = 30
# The regression feature-frame contract — the lag offsets (``EXOGENOUS_LAGS``),
# the observed-target tail length (``HISTORY_TAIL_DAYS``), and the canonical
# column set and order (``canonical_feature_columns()``) — is the single source
# of truth in ``app/shared/feature_frames`` (MLZOO-A). This slice imports it
# rather than re-typing it, so a column-order mismatch with the scenarios
# slice's future-frame generator is structurally impossible.


@dataclass
class RegressionFeatureMatrix:
    """Historical feature matrix + bundle metadata for a regression model.

    Attributes:
        X: Feature matrix, shape ``[n_observations, n_features]`` (NaN allowed).
        y: Target values, shape ``[n_observations]``.
        feature_columns: Column order — persisted so the future frame matches.
        history_tail: The last ``HISTORY_TAIL_DAYS`` observed targets, ending
            at the forecast origin ``T``.
        history_tail_dates: ISO dates aligned with ``history_tail``.
        launch_date_iso: The product launch date (ISO) or ``None``.
        n_observations: Number of training rows.
    """

    X: np.ndarray[Any, np.dtype[np.floating[Any]]]
    y: np.ndarray[Any, np.dtype[np.floating[Any]]]
    feature_columns: list[str]
    history_tail: list[float]
    history_tail_dates: list[str]
    launch_date_iso: str | None
    n_observations: int


def _assemble_regression_rows(
    *,
    dates: list[date_type],
    quantities: list[float],
    prices: list[float],
    baseline_price: float,
    promo_dates: set[date_type],
    holiday_dates: set[date_type],
    launch_date: date_type | None,
) -> list[list[float]]:
    """Assemble the historical regression feature matrix — pure, leakage-safe.

    Time-safe by construction: every lag column at row ``i`` reads only the
    observed target at ``i - lag`` (a strictly earlier day); calendar columns
    are pure functions of the date; ``price_factor`` / ``promo_active`` /
    ``is_holiday`` / ``days_since_launch`` read the same-day exogenous
    attributes. No row reads a future observation.

    Column order is ``canonical_feature_columns()`` exactly: the target lags,
    then the calendar columns, then ``price_factor``, ``promo_active``,
    ``is_holiday``, ``days_since_launch``.

    Extracted from :meth:`ForecastingService._build_regression_features` so the
    leakage invariant can be unit-tested without a database
    (``test_regression_features_leakage.py``).

    Args:
        dates: Observed days in chronological order.
        quantities: Observed target values aligned with ``dates``.
        prices: Observed unit prices aligned with ``dates``.
        baseline_price: The typical price; ``price_factor`` is the ratio to it.
        promo_dates: Days a promotion covered.
        holiday_dates: Calendar holiday days.
        launch_date: The product's launch date, or ``None``.

    Returns:
        Row-major feature matrix ``[n_observations][n_features]``; ``NaN`` marks
        a lag whose source day precedes the series, and ``days_since_launch``
        when the product has no launch date.
    """
    calendar_columns = build_calendar_columns(dates)
    rows: list[list[float]] = []
    for index, day in enumerate(dates):
        row: list[float] = []
        # Target long-lag columns — read only strictly-earlier observations.
        for lag in EXOGENOUS_LAGS:
            row.append(quantities[index - lag] if index >= lag else math.nan)
        # Calendar columns — pure functions of the date (shared builder).
        for name in CALENDAR_COLUMNS:
            row.append(calendar_columns[name][index])
        # Exogenous columns — same-day observed attributes.
        row.append(prices[index] / baseline_price)
        row.append(1.0 if day in promo_dates else 0.0)
        row.append(1.0 if day in holiday_dates else 0.0)
        row.append(float((day - launch_date).days) if launch_date is not None else math.nan)
        rows.append(row)
    return rows


class ForecastingService:
    """Service for training and predicting with forecasting models.

    Provides orchestration layer for:
    - Loading training data from database
    - Training models with configured parameters
    - Saving trained models as bundles
    - Loading models and generating predictions

    CRITICAL: All operations use Settings for reproducibility.
    """

    def __init__(self) -> None:
        """Initialize the forecasting service."""
        self.settings = get_settings()

    async def train_model(
        self,
        db: AsyncSession,
        store_id: int,
        product_id: int,
        train_start_date: date_type,
        train_end_date: date_type,
        config: ModelConfig,
    ) -> TrainResponse:
        """Train a forecasting model and save to disk.

        Args:
            db: Database session.
            store_id: Store ID to train for.
            product_id: Product ID to train for.
            train_start_date: Start date of training period.
            train_end_date: End date of training period (inclusive).
            config: Model configuration.

        Returns:
            TrainResponse with training results.

        Raises:
            ValueError: If insufficient training data.
        """
        start_time = time.perf_counter()

        logger.info(
            "forecasting.train_started",
            store_id=store_id,
            product_id=product_id,
            train_start_date=str(train_start_date),
            train_end_date=str(train_end_date),
            model_type=config.model_type,
            config_hash=config.config_hash(),
        )

        # Build the model first (cheap — no fit), then branch on its capability
        # rather than on a ``model_type`` string. A feature-aware model
        # (``requires_features``) consumes a historical feature matrix; every
        # target-only model trains on the raw target series exactly as before.
        model = model_factory(config, random_state=self.settings.forecast_random_seed)
        extra_metadata: dict[str, object] = {}
        if model.requires_features:
            features = await self._build_regression_features(
                db=db,
                store_id=store_id,
                product_id=product_id,
                start_date=train_start_date,
                end_date=train_end_date,
            )
            model.fit(features.y, features.X)
            n_observations = features.n_observations
            extra_metadata = {
                "feature_columns": features.feature_columns,
                "history_tail": features.history_tail,
                "history_tail_dates": features.history_tail_dates,
                "launch_date": features.launch_date_iso,
            }
        else:
            training_data = await self._load_training_data(
                db=db,
                store_id=store_id,
                product_id=product_id,
                start_date=train_start_date,
                end_date=train_end_date,
            )
            if training_data.n_observations == 0:
                raise ValueError(
                    f"No training data found for store={store_id}, product={product_id} "
                    f"between {train_start_date} and {train_end_date}"
                )
            model.fit(training_data.y)
            n_observations = training_data.n_observations

        # Create bundle with metadata
        bundle = ModelBundle(
            model=model,
            config=config,
            metadata={
                "store_id": store_id,
                "product_id": product_id,
                "train_start_date": str(train_start_date),
                "train_end_date": str(train_end_date),
                "n_observations": n_observations,
                **extra_metadata,
            },
        )

        # Save bundle
        model_id = uuid.uuid4().hex[:12]
        model_path = Path(self.settings.forecast_model_artifacts_dir) / f"model_{model_id}"
        saved_path = save_model_bundle(bundle, model_path)

        duration_ms = (time.perf_counter() - start_time) * 1000

        logger.info(
            "forecasting.train_completed",
            store_id=store_id,
            product_id=product_id,
            model_type=config.model_type,
            config_hash=config.config_hash(),
            n_observations=n_observations,
            model_path=str(saved_path),
            duration_ms=duration_ms,
        )

        return TrainResponse(
            store_id=store_id,
            product_id=product_id,
            model_type=config.model_type,
            model_path=str(saved_path),
            config_hash=config.config_hash(),
            n_observations=n_observations,
            train_start_date=train_start_date,
            train_end_date=train_end_date,
            duration_ms=duration_ms,
        )

    async def predict(
        self,
        store_id: int,
        product_id: int,
        horizon: int,
        model_path: str,
    ) -> PredictResponse:
        """Generate forecasts using a saved model.

        Args:
            store_id: Store ID to predict for.
            product_id: Product ID to predict for.
            horizon: Number of days to forecast.
            model_path: Path to saved model bundle.

        Returns:
            PredictResponse with forecasts.

        Raises:
            FileNotFoundError: If model bundle not found.
            ValueError: If model was trained for different store/product.
        """
        start_time = time.perf_counter()

        logger.info(
            "forecasting.predict_started",
            store_id=store_id,
            product_id=product_id,
            horizon=horizon,
            model_path=model_path,
        )

        # Security: Validate model_path before loading
        # Resolve to absolute path and validate extension and location
        resolved_path = Path(model_path).resolve()
        artifacts_dir = Path(self.settings.forecast_model_artifacts_dir).resolve()

        # Check for .joblib extension
        if resolved_path.suffix != ".joblib":
            logger.warning(
                "forecasting.predict_rejected",
                model_path=model_path,
                resolved_path=str(resolved_path),
                reason="invalid_extension",
            )
            raise ValueError(
                f"Invalid model path: '{model_path}'. Model files must have .joblib extension."
            )

        # Check path is within artifacts directory
        try:
            resolved_path.relative_to(artifacts_dir)
        except ValueError:
            logger.warning(
                "forecasting.predict_rejected",
                model_path=model_path,
                resolved_path=str(resolved_path),
                artifacts_dir=str(artifacts_dir),
                reason="path_traversal_attempt",
            )
            raise ValueError(
                f"Invalid model path: '{model_path}'. "
                f"Model path must be within the configured artifacts directory: '{artifacts_dir}'."
            ) from None

        # Load model bundle (path already validated)
        bundle = load_model_bundle(resolved_path)

        # Validate store/product match
        bundle_store_id = bundle.metadata.get("store_id")
        bundle_product_id = bundle.metadata.get("product_id")

        if bundle_store_id != store_id:
            raise ValueError(
                f"Model was trained for store={bundle_store_id}, "
                f"but prediction requested for store={store_id}"
            )

        if bundle_product_id != product_id:
            raise ValueError(
                f"Model was trained for product={bundle_product_id}, "
                f"but prediction requested for product={product_id}"
            )

        # Feature-aware models need an exogenous feature frame to forecast —
        # that is built (from scenario assumptions) by POST /scenarios/simulate.
        # The plain predict endpoint cannot supply one, so it rejects them
        # cleanly. Branching on ``requires_features`` (not a ``model_type``
        # string) keeps this future-proof as the model zoo grows.
        if bundle.model.requires_features:
            raise ValueError(
                "Feature-aware models forecast through POST /scenarios/simulate, "
                "which supplies the exogenous feature frame. POST /forecasting/"
                "predict does not support them."
            )

        # Generate forecasts
        forecasts_array = bundle.model.predict(horizon)

        # Get the training end date to compute forecast dates
        train_end_date_str = bundle.metadata.get("train_end_date")
        if isinstance(train_end_date_str, str):
            train_end_date = date_type.fromisoformat(train_end_date_str)
        else:
            # Default to today if not stored
            train_end_date = datetime.now(UTC).date()

        # Create forecast points
        forecasts: list[ForecastPoint] = []
        for h in range(horizon):
            forecast_date = train_end_date + timedelta(days=h + 1)
            forecasts.append(
                ForecastPoint(
                    date=forecast_date,
                    forecast=float(forecasts_array[h]),
                )
            )

        duration_ms = (time.perf_counter() - start_time) * 1000

        logger.info(
            "forecasting.predict_completed",
            store_id=store_id,
            product_id=product_id,
            horizon=horizon,
            model_type=bundle.config.model_type,
            config_hash=bundle.config.config_hash(),
            duration_ms=duration_ms,
        )

        return PredictResponse(
            store_id=store_id,
            product_id=product_id,
            forecasts=forecasts,
            model_type=bundle.config.model_type,
            config_hash=bundle.config.config_hash(),
            horizon=horizon,
            duration_ms=duration_ms,
        )

    async def _load_training_data(
        self,
        db: AsyncSession,
        store_id: int,
        product_id: int,
        start_date: date_type,
        end_date: date_type,
    ) -> TrainingData:
        """Load training data from database.

        Args:
            db: Database session.
            store_id: Store ID.
            product_id: Product ID.
            start_date: Start date (inclusive).
            end_date: End date (inclusive).

        Returns:
            TrainingData container with loaded data.
        """
        stmt = (
            select(
                SalesDaily.date,
                SalesDaily.quantity,
            )
            .where(
                (SalesDaily.store_id == store_id)
                & (SalesDaily.product_id == product_id)
                & (SalesDaily.date >= start_date)
                & (SalesDaily.date <= end_date)
            )
            .order_by(SalesDaily.date)
        )

        result = await db.execute(stmt)
        rows = result.all()

        if not rows:
            return TrainingData(
                y=np.array([], dtype=np.float64),
                dates=[],
                store_id=store_id,
                product_id=product_id,
            )

        dates = [row.date for row in rows]
        y = np.array([float(row.quantity) for row in rows], dtype=np.float64)

        return TrainingData(
            y=y,
            dates=dates,
            store_id=store_id,
            product_id=product_id,
        )

    async def _build_regression_features(
        self,
        db: AsyncSession,
        store_id: int,
        product_id: int,
        start_date: date_type,
        end_date: date_type,
    ) -> RegressionFeatureMatrix:
        """Build the historical feature matrix for a regression model.

        Time-safe by construction: every lag column at row ``i`` reads only
        the observed target at ``i - lag`` (a strictly earlier day); calendar
        columns are pure functions of the date; ``price_factor`` /
        ``promo_active`` / ``is_holiday`` / ``days_since_launch`` read the
        same-day exogenous attributes. No row reads a future observation.

        The column set and order are ``canonical_feature_columns()`` from
        ``app/shared/feature_frames`` — the single source of truth shared with
        the scenarios slice's future-frame generator. The pure row assembly is
        factored into :func:`_assemble_regression_rows` (unit-tested for
        leakage without a database).

        Args:
            db: Database session.
            store_id: Store ID.
            product_id: Product ID.
            start_date: Start of the training window (inclusive).
            end_date: End of the training window (inclusive) — the origin ``T``.

        Returns:
            The feature matrix plus the bundle metadata the future frame needs.

        Raises:
            ValueError: When fewer than ``_MIN_REGRESSION_TRAIN_ROWS`` observed
                days are available.
        """
        sales_rows = (
            await db.execute(
                select(SalesDaily.date, SalesDaily.quantity, SalesDaily.unit_price)
                .where(
                    (SalesDaily.store_id == store_id)
                    & (SalesDaily.product_id == product_id)
                    & (SalesDaily.date >= start_date)
                    & (SalesDaily.date <= end_date)
                )
                .order_by(SalesDaily.date)
            )
        ).all()
        if len(sales_rows) < _MIN_REGRESSION_TRAIN_ROWS:
            raise ValueError(
                f"A regression model needs at least {_MIN_REGRESSION_TRAIN_ROWS} "
                f"observed days; store={store_id} product={product_id} has "
                f"{len(sales_rows)} between {start_date} and {end_date}."
            )

        dates = [row.date for row in sales_rows]
        quantities = [float(row.quantity) for row in sales_rows]
        prices = [float(row.unit_price) for row in sales_rows]

        # Baseline price = median of the positive prices, so price_factor is
        # ~1.0 on a typical day and < 1.0 on a markdown/promo day.
        positive_prices = sorted(price for price in prices if price > 0.0)
        baseline_price = positive_prices[len(positive_prices) // 2] if positive_prices else 1.0

        holiday_dates: set[date_type] = set(
            (
                await db.execute(
                    select(Calendar.date).where(
                        Calendar.date >= start_date,
                        Calendar.date <= end_date,
                        Calendar.is_holiday.is_(True),
                    )
                )
            )
            .scalars()
            .all()
        )

        # Promotion-active days: store-specific OR chain-wide rows that overlap
        # the training window, expanded to the set of dates they cover.
        promo_rows = (
            await db.execute(
                select(Promotion.start_date, Promotion.end_date).where(
                    Promotion.product_id == product_id,
                    (Promotion.store_id == store_id) | (Promotion.store_id.is_(None)),
                    Promotion.start_date <= end_date,
                    Promotion.end_date >= start_date,
                )
            )
        ).all()
        promo_dates: set[date_type] = set()
        for promo in promo_rows:
            day = max(promo.start_date, start_date)
            last = min(promo.end_date, end_date)
            while day <= last:
                promo_dates.add(day)
                day += timedelta(days=1)

        launch_date: date_type | None = await db.scalar(
            select(Product.launch_date).where(Product.id == product_id)
        )

        feature_columns = canonical_feature_columns()
        feature_rows = _assemble_regression_rows(
            dates=dates,
            quantities=quantities,
            prices=prices,
            baseline_price=baseline_price,
            promo_dates=promo_dates,
            holiday_dates=holiday_dates,
            launch_date=launch_date,
        )

        tail = quantities[-HISTORY_TAIL_DAYS:]
        tail_dates = [day.isoformat() for day in dates[-HISTORY_TAIL_DAYS:]]

        logger.info(
            "forecasting.regression_features_built",
            store_id=store_id,
            product_id=product_id,
            n_observations=len(dates),
            n_features=len(feature_columns),
        )

        return RegressionFeatureMatrix(
            X=np.array(feature_rows, dtype=np.float64),
            y=np.array(quantities, dtype=np.float64),
            feature_columns=feature_columns,
            history_tail=[float(value) for value in tail],
            history_tail_dates=tail_dates,
            launch_date_iso=launch_date.isoformat() if launch_date is not None else None,
            n_observations=len(dates),
        )
