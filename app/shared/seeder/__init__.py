"""Seeder module for generating synthetic test data.

The Forge - Development and testing data factory for generating realistic
synthetic datasets for the ForecastLabAI system.

Provides:
- Dimension generators (store, product, calendar)
- Fact generators with time-series patterns (sales, inventory, price, promotion)
- Pre-built scenarios for common testing needs
- Safe delete and append operations with confirmation guards
- RAG + Agent E2E validation scenario
"""

from app.shared.seeder.config import (
    RetailPatternConfig,
    ScenarioPreset,
    SeederConfig,
    TimeSeriesConfig,
)
from app.shared.seeder.core import DataSeeder, SeederResult
from app.shared.seeder.rag_scenario import RAGScenarioResult, RAGScenarioRunner, run_rag_scenario

__all__ = [
    "DataSeeder",
    "RAGScenarioResult",
    "RAGScenarioRunner",
    "RetailPatternConfig",
    "ScenarioPreset",
    "SeederConfig",
    "SeederResult",
    "TimeSeriesConfig",
    "run_rag_scenario",
]
