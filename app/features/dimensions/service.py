"""Service layer for dimension discovery operations.

Provides paginated access to Store and Product dimension tables
with filtering and search capabilities.
"""

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.features.data_platform.models import Product, Store
from app.features.dimensions.schemas import (
    ProductListResponse,
    ProductResponse,
    StoreListResponse,
    StoreResponse,
)

logger = get_logger(__name__)


class DimensionService:
    """Service for discovering stores and products.

    Provides paginated access to dimension tables with filtering support.
    All methods are async and use SQLAlchemy 2.0 style queries.
    """

    async def list_stores(
        self,
        db: AsyncSession,
        page: int = 1,
        page_size: int = 20,
        region: str | None = None,
        store_type: str | None = None,
        search: str | None = None,
    ) -> StoreListResponse:
        """List stores with pagination and filtering.

        Args:
            db: Database session.
            page: Page number (1-indexed).
            page_size: Number of stores per page.
            region: Filter by region (exact match).
            store_type: Filter by store type (exact match).
            search: Search in store code and name (case-insensitive).

        Returns:
            Paginated list of stores.
        """
        # Build base query
        stmt = select(Store)

        # Apply filters
        if region is not None:
            stmt = stmt.where(Store.region == region)
        if store_type is not None:
            stmt = stmt.where(Store.store_type == store_type)
        if search is not None and len(search) >= 2:
            search_pattern = f"%{search}%"
            stmt = stmt.where(
                or_(
                    Store.code.ilike(search_pattern),
                    Store.name.ilike(search_pattern),
                )
            )

        # Count total before pagination
        count_stmt = select(func.count()).select_from(stmt.subquery())
        total_result = await db.execute(count_stmt)
        total = total_result.scalar_one()

        # Apply pagination and ordering
        offset = (page - 1) * page_size
        stmt = stmt.order_by(Store.code).offset(offset).limit(page_size)

        # Execute query
        result = await db.execute(stmt)
        stores = result.scalars().all()

        logger.info(
            "dimensions.stores_listed",
            total=total,
            page=page,
            page_size=page_size,
            filters={"region": region, "store_type": store_type, "search": search},
        )

        return StoreListResponse(
            stores=[StoreResponse.model_validate(store) for store in stores],
            total=total,
            page=page,
            page_size=page_size,
        )

    async def get_store(
        self,
        db: AsyncSession,
        store_id: int,
    ) -> StoreResponse | None:
        """Get a single store by ID.

        Args:
            db: Database session.
            store_id: Store primary key.

        Returns:
            Store details or None if not found.
        """
        stmt = select(Store).where(Store.id == store_id)
        result = await db.execute(stmt)
        store = result.scalar_one_or_none()

        if store is None:
            return None

        return StoreResponse.model_validate(store)

    async def get_store_by_code(
        self,
        db: AsyncSession,
        code: str,
    ) -> StoreResponse | None:
        """Get a single store by code.

        Args:
            db: Database session.
            code: Store code (e.g., 'S001').

        Returns:
            Store details or None if not found.
        """
        stmt = select(Store).where(Store.code == code)
        result = await db.execute(stmt)
        store = result.scalar_one_or_none()

        if store is None:
            return None

        return StoreResponse.model_validate(store)

    async def list_products(
        self,
        db: AsyncSession,
        page: int = 1,
        page_size: int = 20,
        category: str | None = None,
        brand: str | None = None,
        search: str | None = None,
    ) -> ProductListResponse:
        """List products with pagination and filtering.

        Args:
            db: Database session.
            page: Page number (1-indexed).
            page_size: Number of products per page.
            category: Filter by category (exact match).
            brand: Filter by brand (exact match).
            search: Search in SKU and name (case-insensitive).

        Returns:
            Paginated list of products.
        """
        # Build base query
        stmt = select(Product)

        # Apply filters
        if category is not None:
            stmt = stmt.where(Product.category == category)
        if brand is not None:
            stmt = stmt.where(Product.brand == brand)
        if search is not None and len(search) >= 2:
            search_pattern = f"%{search}%"
            stmt = stmt.where(
                or_(
                    Product.sku.ilike(search_pattern),
                    Product.name.ilike(search_pattern),
                )
            )

        # Count total before pagination
        count_stmt = select(func.count()).select_from(stmt.subquery())
        total_result = await db.execute(count_stmt)
        total = total_result.scalar_one()

        # Apply pagination and ordering
        offset = (page - 1) * page_size
        stmt = stmt.order_by(Product.sku).offset(offset).limit(page_size)

        # Execute query
        result = await db.execute(stmt)
        products = result.scalars().all()

        logger.info(
            "dimensions.products_listed",
            total=total,
            page=page,
            page_size=page_size,
            filters={"category": category, "brand": brand, "search": search},
        )

        return ProductListResponse(
            products=[ProductResponse.model_validate(product) for product in products],
            total=total,
            page=page,
            page_size=page_size,
        )

    async def get_product(
        self,
        db: AsyncSession,
        product_id: int,
    ) -> ProductResponse | None:
        """Get a single product by ID.

        Args:
            db: Database session.
            product_id: Product primary key.

        Returns:
            Product details or None if not found.
        """
        stmt = select(Product).where(Product.id == product_id)
        result = await db.execute(stmt)
        product = result.scalar_one_or_none()

        if product is None:
            return None

        return ProductResponse.model_validate(product)

    async def get_product_by_sku(
        self,
        db: AsyncSession,
        sku: str,
    ) -> ProductResponse | None:
        """Get a single product by SKU.

        Args:
            db: Database session.
            sku: Product SKU (e.g., 'SKU-001').

        Returns:
            Product details or None if not found.
        """
        stmt = select(Product).where(Product.sku == sku)
        result = await db.execute(stmt)
        product = result.scalar_one_or_none()

        if product is None:
            return None

        return ProductResponse.model_validate(product)
