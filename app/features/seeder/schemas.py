"""Pydantic schemas for the seeder feature."""

from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, Field


class SeederStatus(BaseModel):
    """Current database state with row counts and metadata."""

    stores: int = Field(description="Number of store records")
    products: int = Field(description="Number of product records")
    calendar: int = Field(description="Number of calendar day records")
    sales: int = Field(description="Number of sales_daily records")
    inventory: int = Field(description="Number of inventory_snapshot_daily records")
    price_history: int = Field(description="Number of price_history records")
    promotions: int = Field(description="Number of promotion records")
    date_range_start: date | None = Field(
        default=None,
        description="Earliest date in sales_daily",
    )
    date_range_end: date | None = Field(
        default=None,
        description="Latest date in sales_daily",
    )
    last_updated: datetime | None = Field(
        default=None,
        description="Timestamp of last data modification",
    )


class ScenarioInfo(BaseModel):
    """Information about a scenario preset."""

    name: str = Field(description="Scenario preset name")
    description: str = Field(description="Human-readable description")
    stores: int = Field(description="Default number of stores")
    products: int = Field(description="Default number of products")
    start_date: date = Field(description="Default start date")
    end_date: date = Field(description="Default end date")


class GenerateParams(BaseModel):
    """Parameters for generating a new dataset."""

    scenario: str = Field(
        default="retail_standard",
        description="Scenario preset name",
    )
    seed: int = Field(
        default=42,
        ge=0,
        description="Random seed for reproducibility",
    )
    stores: int = Field(
        default=10,
        ge=1,
        le=100,
        description="Number of stores to generate",
    )
    products: int = Field(
        default=50,
        ge=1,
        le=500,
        description="Number of products to generate",
    )
    start_date: date = Field(
        default_factory=lambda: date(2024, 1, 1),
        description="Start of date range",
    )
    end_date: date = Field(
        default_factory=lambda: date(2024, 12, 31),
        description="End of date range",
    )
    sparsity: float = Field(
        default=0.0,
        ge=0.0,
        le=1.0,
        description="Fraction of missing store/product combinations",
    )
    dry_run: bool = Field(
        default=False,
        description="Preview only, do not execute",
    )


class AppendParams(BaseModel):
    """Parameters for appending data to existing dataset."""

    start_date: date = Field(description="Start of new date range")
    end_date: date = Field(description="End of new date range")
    seed: int = Field(
        default=43,
        ge=0,
        description="Random seed for reproducibility",
    )


class DeleteParams(BaseModel):
    """Parameters for deleting data."""

    scope: Literal["all", "facts", "dimensions"] = Field(
        default="all",
        description="What to delete: all, facts (sales/inventory/etc), or dimensions (store/product/calendar)",
    )
    dry_run: bool = Field(
        default=False,
        description="Preview what would be deleted without executing",
    )


class GenerateResult(BaseModel):
    """Result of a generation or append operation."""

    success: bool = Field(description="Whether the operation succeeded")
    records_created: dict[str, int] = Field(
        description="Count of records created per table",
    )
    duration_seconds: float = Field(description="Time taken in seconds")
    message: str = Field(description="Human-readable result message")
    seed: int = Field(description="Random seed used")


class DeleteResult(BaseModel):
    """Result of a delete operation."""

    success: bool = Field(description="Whether the operation succeeded")
    records_deleted: dict[str, int] = Field(
        description="Count of records deleted per table",
    )
    message: str = Field(description="Human-readable result message")
    dry_run: bool = Field(description="Whether this was a preview only")


class VerifyCheck(BaseModel):
    """Single verification check result."""

    name: str = Field(description="Check name")
    status: Literal["passed", "warning", "failed"] = Field(
        description="Check status",
    )
    message: str = Field(description="Human-readable result")
    details: list[str] | None = Field(
        default=None,
        description="Additional details if applicable",
    )


class VerifyResult(BaseModel):
    """Result of data verification."""

    passed: bool = Field(description="Whether all critical checks passed")
    checks: list[VerifyCheck] = Field(description="Individual check results")
    total_checks: int = Field(description="Number of checks performed")
    passed_count: int = Field(description="Number of passed checks")
    warning_count: int = Field(description="Number of warnings")
    failed_count: int = Field(description="Number of failures")
