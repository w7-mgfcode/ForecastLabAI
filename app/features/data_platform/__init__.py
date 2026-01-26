"""Data platform feature for retail forecasting mini-warehouse.

This module provides the core data models for the ForecastLabAI system:
- Dimension tables: Store, Product, Calendar
- Fact tables: SalesDaily, PriceHistory, Promotion, InventorySnapshotDaily
"""

from app.features.data_platform.models import (
    Calendar,
    InventorySnapshotDaily,
    PriceHistory,
    Product,
    Promotion,
    SalesDaily,
    Store,
)

__all__ = [
    "Calendar",
    "InventorySnapshotDaily",
    "PriceHistory",
    "Product",
    "Promotion",
    "SalesDaily",
    "Store",
]
