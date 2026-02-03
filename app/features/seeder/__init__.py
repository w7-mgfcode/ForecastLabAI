"""Seeder feature module for managing synthetic data generation via REST API.

This feature provides REST endpoints for the Data Seeder (The Forge),
allowing management of synthetic test data through the dashboard.
"""

from app.features.seeder.routes import router

__all__ = ["router"]
