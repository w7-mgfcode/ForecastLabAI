"""Dimensions discovery module for Store and Product metadata.

This module provides endpoints for agents to discover available stores and products
before calling ingest, training, or forecasting endpoints.
"""

from app.features.dimensions.routes import router
from app.features.dimensions.schemas import (
    ProductListResponse,
    ProductResponse,
    StoreListResponse,
    StoreResponse,
)
from app.features.dimensions.service import DimensionService

__all__ = [
    "DimensionService",
    "ProductListResponse",
    "ProductResponse",
    "StoreListResponse",
    "StoreResponse",
    "router",
]
