"""Shared utility functions."""

import math

from app.shared.schemas import PaginatedResponse, PaginationParams


def paginate_response[T](
    items: list[T],
    total: int,
    pagination: PaginationParams,
) -> PaginatedResponse[T]:
    """Create a paginated response from items and total count.

    Args:
        items: List of items for the current page.
        total: Total count of all items.
        pagination: Pagination parameters used for the query.

    Returns:
        PaginatedResponse with computed page count.
    """
    pages = math.ceil(total / pagination.page_size) if total > 0 else 0
    return PaginatedResponse[T](
        items=items,
        total=total,
        page=pagination.page,
        page_size=pagination.page_size,
        pages=pages,
    )
