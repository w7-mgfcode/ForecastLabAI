"""API routes for dimension discovery.

These endpoints enable LLM agents and users to discover available stores
and products before calling ingest, training, or forecasting endpoints.
"""

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.logging import get_logger
from app.features.dimensions.schemas import (
    ProductListResponse,
    ProductResponse,
    StoreListResponse,
    StoreResponse,
)
from app.features.dimensions.service import DimensionService

logger = get_logger(__name__)

router = APIRouter(prefix="/dimensions", tags=["dimensions"])


# =============================================================================
# Store Endpoints
# =============================================================================


@router.get(
    "/stores",
    response_model=StoreListResponse,
    summary="List all stores",
    description="""
Discover available stores for use in other API endpoints.

**Purpose**: Resolve store metadata (code, name, region) to store_id values
required by ingest, training, and forecasting endpoints.

**Filtering Options**:
- `region`: Filter by geographic region (exact match)
- `store_type`: Filter by store format (exact match)
- `search`: Search in store code and name (case-insensitive, min 2 chars)

**Pagination**:
- Results are paginated with 1-indexed pages
- Default: 20 items per page, maximum: 100
- Use `total` in response to calculate total pages

**Example Use Cases**:
1. Get all stores: `GET /dimensions/stores`
2. Find stores by region: `GET /dimensions/stores?region=North`
3. Search for a store: `GET /dimensions/stores?search=Main`
""",
)
async def list_stores(
    db: AsyncSession = Depends(get_db),
    page: int = Query(1, ge=1, description="Page number (1-indexed)"),
    page_size: int = Query(20, ge=1, le=100, description="Stores per page (max 100)"),
    region: str | None = Query(None, description="Filter by region (exact match)"),
    store_type: str | None = Query(None, description="Filter by store type (exact match)"),
    search: str | None = Query(
        None,
        min_length=2,
        description="Search in code and name (case-insensitive)",
    ),
) -> StoreListResponse:
    """List stores with pagination and filtering.

    Args:
        db: Database session.
        page: Page number (1-indexed).
        page_size: Number of stores per page.
        region: Filter by region.
        store_type: Filter by store type.
        search: Search in code and name.

    Returns:
        Paginated list of stores.
    """
    service = DimensionService()
    return await service.list_stores(
        db=db,
        page=page,
        page_size=page_size,
        region=region,
        store_type=store_type,
        search=search,
    )


@router.get(
    "/stores/{store_id}",
    response_model=StoreResponse,
    summary="Get store by ID",
    description="""
Get details for a specific store by its internal ID.

**Use Case**: Retrieve full store metadata after obtaining store_id
from list endpoint or another API response.

**Error Handling**:
- Returns 404 if store_id doesn't exist
- Agent should fall back to list endpoint to discover valid IDs
""",
)
async def get_store(
    store_id: int,
    db: AsyncSession = Depends(get_db),
) -> StoreResponse:
    """Get store details by ID.

    Args:
        store_id: Store primary key.
        db: Database session.

    Returns:
        Store details.

    Raises:
        HTTPException: If store not found.
    """
    service = DimensionService()
    result = await service.get_store(db=db, store_id=store_id)

    if result is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Store not found: {store_id}. "
            "Use GET /dimensions/stores to list available stores.",
        )

    return result


# =============================================================================
# Product Endpoints
# =============================================================================


@router.get(
    "/products",
    response_model=ProductListResponse,
    summary="List all products",
    description="""
Discover available products for use in other API endpoints.

**Purpose**: Resolve product metadata (SKU, name, category) to product_id values
required by ingest, training, and forecasting endpoints.

**Filtering Options**:
- `category`: Filter by product category (exact match)
- `brand`: Filter by brand name (exact match)
- `search`: Search in SKU and name (case-insensitive, min 2 chars)

**Pagination**:
- Results are paginated with 1-indexed pages
- Default: 20 items per page, maximum: 100
- Use `total` in response to calculate total pages

**Example Use Cases**:
1. Get all products: `GET /dimensions/products`
2. Find products by category: `GET /dimensions/products?category=Beverage`
3. Search for a product: `GET /dimensions/products?search=Cola`
""",
)
async def list_products(
    db: AsyncSession = Depends(get_db),
    page: int = Query(1, ge=1, description="Page number (1-indexed)"),
    page_size: int = Query(20, ge=1, le=100, description="Products per page (max 100)"),
    category: str | None = Query(None, description="Filter by category (exact match)"),
    brand: str | None = Query(None, description="Filter by brand (exact match)"),
    search: str | None = Query(
        None,
        min_length=2,
        description="Search in SKU and name (case-insensitive)",
    ),
) -> ProductListResponse:
    """List products with pagination and filtering.

    Args:
        db: Database session.
        page: Page number (1-indexed).
        page_size: Number of products per page.
        category: Filter by category.
        brand: Filter by brand.
        search: Search in SKU and name.

    Returns:
        Paginated list of products.
    """
    service = DimensionService()
    return await service.list_products(
        db=db,
        page=page,
        page_size=page_size,
        category=category,
        brand=brand,
        search=search,
    )


@router.get(
    "/products/{product_id}",
    response_model=ProductResponse,
    summary="Get product by ID",
    description="""
Get details for a specific product by its internal ID.

**Use Case**: Retrieve full product metadata after obtaining product_id
from list endpoint or another API response.

**Error Handling**:
- Returns 404 if product_id doesn't exist
- Agent should fall back to list endpoint to discover valid IDs
""",
)
async def get_product(
    product_id: int,
    db: AsyncSession = Depends(get_db),
) -> ProductResponse:
    """Get product details by ID.

    Args:
        product_id: Product primary key.
        db: Database session.

    Returns:
        Product details.

    Raises:
        HTTPException: If product not found.
    """
    service = DimensionService()
    result = await service.get_product(db=db, product_id=product_id)

    if result is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Product not found: {product_id}. "
            "Use GET /dimensions/products to list available products.",
        )

    return result
