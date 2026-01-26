"""Shared Pydantic schemas for API responses."""

from pydantic import BaseModel, Field


class ErrorDetail(BaseModel):
    """Detailed error information."""

    code: str = Field(..., description="Machine-readable error code")
    message: str = Field(..., description="Human-readable error message")
    details: dict[str, str | int | float | bool | None] = Field(
        default_factory=dict,
        description="Additional error context",
    )
    request_id: str | None = Field(None, description="Request correlation ID")


class ErrorResponse(BaseModel):
    """Standard error response wrapper."""

    error: ErrorDetail


class PaginationParams(BaseModel):
    """Pagination query parameters."""

    page: int = Field(1, ge=1, description="Page number (1-indexed)")
    page_size: int = Field(50, ge=1, le=1000, description="Items per page")

    @property
    def offset(self) -> int:
        """Calculate SQL offset from page number."""
        return (self.page - 1) * self.page_size

    @property
    def limit(self) -> int:
        """Return page size as SQL limit."""
        return self.page_size


class PaginatedResponse[T](BaseModel):
    """Generic paginated response wrapper."""

    items: list[T] = Field(..., description="Page of items")
    total: int = Field(..., ge=0, description="Total item count")
    page: int = Field(..., ge=1, description="Current page number")
    page_size: int = Field(..., ge=1, description="Items per page")
    pages: int = Field(..., ge=0, description="Total number of pages")
