"""Pydantic schemas for dimension discovery endpoints.

These schemas are optimized for LLM tool-calling with rich descriptions
that help agents understand how to use each field.
"""

from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field

# =============================================================================
# Store Schemas
# =============================================================================


class StoreResponse(BaseModel):
    """Store dimension record for agent discovery.

    Use the GET /dimensions/stores endpoint to discover available stores
    before calling ingest, training, or forecasting endpoints.

    The 'id' field should be used as the store_id parameter in other API calls.
    """

    model_config = ConfigDict(from_attributes=True)

    id: int = Field(
        ...,
        description="Internal store ID. Use this value for store_id parameters "
        "in /ingest/sales-daily, /forecasting/train, and /forecasting/predict.",
    )
    code: str = Field(
        ...,
        description="Business store code (e.g., 'S001'). Unique human-readable identifier. "
        "Use this for display and matching with external data sources.",
    )
    name: str = Field(
        ...,
        description="Human-readable store name for display purposes.",
    )
    region: str | None = Field(
        None,
        description="Geographic region (e.g., 'North', 'South', 'East', 'West'). "
        "Filter using the 'region' query parameter.",
    )
    city: str | None = Field(
        None,
        description="City where the store is located.",
    )
    store_type: str | None = Field(
        None,
        description="Store format (e.g., 'supermarket', 'express', 'warehouse'). "
        "Filter using the 'store_type' query parameter.",
    )
    created_at: datetime = Field(
        ...,
        description="Timestamp when the store record was created.",
    )
    updated_at: datetime = Field(
        ...,
        description="Timestamp when the store record was last updated.",
    )


class StoreListResponse(BaseModel):
    """Paginated list of stores with filtering metadata.

    Use pagination parameters (page, page_size) to navigate large result sets.
    Filtering by region or store_type reduces the result set before pagination.
    """

    stores: list[StoreResponse] = Field(
        ...,
        description="Array of store records for the current page. "
        "Empty if no stores match the filters.",
    )
    total: int = Field(
        ...,
        ge=0,
        description="Total number of stores matching the applied filters. "
        "Use to calculate total pages: ceil(total / page_size).",
    )
    page: int = Field(
        ...,
        ge=1,
        description="Current page number (1-indexed). First page is 1.",
    )
    page_size: int = Field(
        ...,
        ge=1,
        description="Number of stores per page. Maximum is 100.",
    )


# =============================================================================
# Product Schemas
# =============================================================================


class ProductResponse(BaseModel):
    """Product dimension record for agent discovery.

    Use the GET /dimensions/products endpoint to discover available products
    before calling ingest, training, or forecasting endpoints.

    The 'id' field should be used as the product_id parameter in other API calls.
    """

    model_config = ConfigDict(from_attributes=True)

    id: int = Field(
        ...,
        description="Internal product ID. Use this value for product_id parameters "
        "in /ingest/sales-daily, /forecasting/train, and /forecasting/predict.",
    )
    sku: str = Field(
        ...,
        description="Stock Keeping Unit - unique product identifier (e.g., 'SKU-001'). "
        "Use this for matching with external inventory systems.",
    )
    name: str = Field(
        ...,
        description="Human-readable product name for display purposes.",
    )
    category: str | None = Field(
        None,
        description="Product category (e.g., 'Beverage', 'Snacks', 'Dairy'). "
        "Filter using the 'category' query parameter.",
    )
    brand: str | None = Field(
        None,
        description="Product brand name. Filter using the 'brand' query parameter.",
    )
    base_price: Decimal | None = Field(
        None,
        description="Standard retail price for this product. "
        "Actual sale prices may vary by promotion.",
    )
    base_cost: Decimal | None = Field(
        None,
        description="Standard cost/COGS for this product. Used for margin calculations.",
    )
    created_at: datetime = Field(
        ...,
        description="Timestamp when the product record was created.",
    )
    updated_at: datetime = Field(
        ...,
        description="Timestamp when the product record was last updated.",
    )


class ProductListResponse(BaseModel):
    """Paginated list of products with filtering metadata.

    Use pagination parameters (page, page_size) to navigate large result sets.
    Filtering by category or brand reduces the result set before pagination.
    """

    products: list[ProductResponse] = Field(
        ...,
        description="Array of product records for the current page. "
        "Empty if no products match the filters.",
    )
    total: int = Field(
        ...,
        ge=0,
        description="Total number of products matching the applied filters. "
        "Use to calculate total pages: ceil(total / page_size).",
    )
    page: int = Field(
        ...,
        ge=1,
        description="Current page number (1-indexed). First page is 1.",
    )
    page_size: int = Field(
        ...,
        ge=1,
        description="Number of products per page. Maximum is 100.",
    )
