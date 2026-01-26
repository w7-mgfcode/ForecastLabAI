"""Pydantic schemas for ingest API."""

from datetime import date as date_type
from decimal import Decimal

from pydantic import BaseModel, Field


class SalesDailyIngestRow(BaseModel):
    """Single row in sales daily ingest payload.

    Uses natural keys (store_code, sku) instead of internal IDs.
    Service resolves these to store_id, product_id before upsert.

    Note: total_amount is accepted as-is without validation against
    quantity * unit_price, as source systems may apply discounts or
    rounding that we trust.
    """

    date: date_type
    store_code: str = Field(
        ..., min_length=1, max_length=20, description="Store code (natural key)"
    )
    sku: str = Field(..., min_length=1, max_length=50, description="Product SKU (natural key)")
    quantity: int = Field(..., ge=0, description="Units sold (non-negative)")
    unit_price: Decimal = Field(..., ge=0, decimal_places=2, description="Price per unit")
    total_amount: Decimal = Field(
        ...,
        ge=0,
        decimal_places=2,
        description="Total sales amount (trusted as-is from source system)",
    )


class SalesDailyIngestRequest(BaseModel):
    """Request body for POST /ingest/sales-daily."""

    records: list[SalesDailyIngestRow] = Field(
        ...,
        min_length=1,
        max_length=10000,
        description="Sales records to upsert",
    )


class IngestRowError(BaseModel):
    """Error detail for a single rejected row."""

    row_index: int = Field(..., description="0-based index of the failed row")
    store_code: str = Field(..., description="Store code from the row")
    sku: str = Field(..., description="SKU from the row")
    date: date_type = Field(..., description="Date from the row")
    error_code: str = Field(..., description="Machine-readable error code")
    error_message: str = Field(..., description="Human-readable error message")


class SalesDailyIngestResponse(BaseModel):
    """Response body for POST /ingest/sales-daily.

    Note: Due to PostgreSQL ON CONFLICT semantics, we cannot distinguish
    inserts from updates without additional complexity. The `processed_count`
    field represents all rows successfully written (inserted or updated).
    """

    processed_count: int = Field(
        ..., ge=0, description="Number of rows successfully written (inserted or updated)"
    )
    rejected_count: int = Field(..., ge=0, description="Number of rows rejected")
    total_received: int = Field(..., ge=0, description="Total rows received in request")
    errors: "list[IngestRowError]" = Field(  # pyright: ignore[reportUnknownVariableType]
        default_factory=list, description="Details of rejected rows"
    )
    duration_ms: float = Field(..., ge=0, description="Processing duration in milliseconds")
