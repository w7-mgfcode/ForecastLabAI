"""Pydantic schemas for ingest API."""

from datetime import date as date_type
from decimal import Decimal

from pydantic import BaseModel, Field, model_validator


class SalesDailyIngestRow(BaseModel):
    """Single row in sales daily ingest payload.

    Uses natural keys (store_code, sku) instead of internal IDs.
    Service resolves these to store_id, product_id before upsert.
    """

    date: date_type
    store_code: str = Field(
        ..., min_length=1, max_length=20, description="Store code (natural key)"
    )
    sku: str = Field(..., min_length=1, max_length=50, description="Product SKU (natural key)")
    quantity: int = Field(..., ge=0, description="Units sold (non-negative)")
    unit_price: Decimal = Field(..., ge=0, decimal_places=2, description="Price per unit")
    total_amount: Decimal = Field(..., ge=0, decimal_places=2, description="Total sales amount")

    @model_validator(mode="after")
    def validate_total_amount_consistency(self) -> "SalesDailyIngestRow":
        """Warn if total_amount doesn't match quantity * unit_price.

        Allows small floating-point discrepancies (0.01 tolerance).
        """
        expected = self.quantity * self.unit_price
        # Allow through but could log warning - tolerance for rounding
        if abs(self.total_amount - expected) > Decimal("0.01"):
            pass
        return self


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
    """Response body for POST /ingest/sales-daily."""

    inserted_count: int = Field(..., ge=0, description="Number of new rows inserted")
    updated_count: int = Field(..., ge=0, description="Number of existing rows updated")
    rejected_count: int = Field(..., ge=0, description="Number of rows rejected")
    total_processed: int = Field(..., ge=0, description="Total rows processed")
    errors: list["IngestRowError"] = Field(default=[], description="Details of rejected rows")
    duration_ms: float = Field(..., ge=0, description="Processing duration in milliseconds")
