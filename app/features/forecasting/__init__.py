"""Forecasting module for baseline and ML models.

This module provides a unified interface for training and predicting with
various forecasting models including naive, seasonal naive, and moving average.

Exports:
    Models:
        - BaseForecaster: Abstract base class for all forecasters
        - NaiveForecaster: Predicts last observed value
        - SeasonalNaiveForecaster: Predicts value from same season
        - MovingAverageForecaster: Predicts mean of last N observations
        - model_factory: Create forecaster from config

    Schemas:
        - ModelConfig: Union of all model configurations
        - NaiveModelConfig, SeasonalNaiveModelConfig, MovingAverageModelConfig
        - TrainRequest, TrainResponse
        - PredictRequest, PredictResponse, ForecastPoint

    Persistence:
        - ModelBundle: Container for model + config + metadata
        - save_model_bundle, load_model_bundle

    Service:
        - ForecastingService: Orchestration layer for training/prediction
"""

from app.features.forecasting.models import (
    BaseForecaster,
    FitResult,
    MovingAverageForecaster,
    NaiveForecaster,
    SeasonalNaiveForecaster,
    model_factory,
)
from app.features.forecasting.persistence import (
    ModelBundle,
    load_model_bundle,
    save_model_bundle,
)
from app.features.forecasting.schemas import (
    ForecastPoint,
    LightGBMModelConfig,
    ModelConfig,
    ModelConfigBase,
    MovingAverageModelConfig,
    NaiveModelConfig,
    PredictRequest,
    PredictResponse,
    SeasonalNaiveModelConfig,
    TrainRequest,
    TrainResponse,
)
from app.features.forecasting.service import ForecastingService

__all__ = [
    # Models
    "BaseForecaster",
    "FitResult",
    # Schemas
    "ForecastPoint",
    # Service
    "ForecastingService",
    "LightGBMModelConfig",
    "ModelBundle",
    "ModelConfig",
    "ModelConfigBase",
    "MovingAverageForecaster",
    "MovingAverageModelConfig",
    "NaiveForecaster",
    "NaiveModelConfig",
    "PredictRequest",
    "PredictResponse",
    "SeasonalNaiveForecaster",
    "SeasonalNaiveModelConfig",
    "TrainRequest",
    "TrainResponse",
    # Persistence
    "load_model_bundle",
    "model_factory",
    "save_model_bundle",
]
