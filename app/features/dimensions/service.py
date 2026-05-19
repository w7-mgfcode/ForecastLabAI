"""Service layer for dimension discovery operations.

Provides paginated access to Store and Product dimension tables
with filtering and search capabilities.
"""

from datetime import UTC, date, datetime, timedelta
from typing import Any

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import InstrumentedAttribute

from app.core.logging import get_logger
from app.features.data_platform.models import Product, Store
from app.features.dimensions.schemas import (
    LifecycleCurveResponse,
    LifecyclePoint,
    ProductListResponse,
    ProductResponse,
    StoreListResponse,
    StoreResponse,
)
from app.shared.seeder.config import LifecycleConfig
from app.shared.seeder.generators.lifecycle import LifecycleGenerator

logger = get_logger(__name__)

# Allow-listed sort columns for the dimension list endpoints. sort_by is user
# input — it MUST resolve through these maps to a real mapped column; an
# unknown key falls back to the default order (never an error, never raw SQL).
_STORE_SORT_COLUMNS: dict[str, InstrumentedAttribute[Any]] = {
    "code": Store.code,
    "name": Store.name,
    "region": Store.region,
    "city": Store.city,
    "store_type": Store.store_type,
}
_PRODUCT_SORT_COLUMNS: dict[str, InstrumentedAttribute[Any]] = {
    "sku": Product.sku,
    "name": Product.name,
    "category": Product.category,
    "brand": Product.brand,
    "base_price": Product.base_price,
}


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
        sort_by: str | None = None,
        sort_order: str = "asc",
    ) -> StoreListResponse:
        """List stores with pagination and filtering.

        Args:
            db: Database session.
            page: Page number (1-indexed).
            page_size: Number of stores per page.
            region: Filter by region (exact match).
            store_type: Filter by store type (exact match).
            search: Search in store code and name (case-insensitive).
            sort_by: Allow-listed sort column (code, name, region, city,
                store_type). Unknown values fall back to the default order.
            sort_order: Sort direction ("asc" or "desc").

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

        # Apply ordering: allow-listed sort column, else the default (code).
        sort_column = _STORE_SORT_COLUMNS.get(sort_by) if sort_by else None
        if sort_column is not None:
            order_by = sort_column.desc() if sort_order == "desc" else sort_column.asc()
        else:
            order_by = Store.code.asc()

        # Apply pagination. Append the unique `code` as a tie-breaker so rows
        # with equal sort values keep a stable order across pages (offset
        # pagination over a non-unique sort key is otherwise non-deterministic).
        offset = (page - 1) * page_size
        stmt = stmt.order_by(order_by, Store.code.asc()).offset(offset).limit(page_size)

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
        sort_by: str | None = None,
        sort_order: str = "asc",
    ) -> ProductListResponse:
        """List products with pagination and filtering.

        Args:
            db: Database session.
            page: Page number (1-indexed).
            page_size: Number of products per page.
            category: Filter by category (exact match).
            brand: Filter by brand (exact match).
            search: Search in SKU and name (case-insensitive).
            sort_by: Allow-listed sort column (sku, name, category, brand,
                base_price). Unknown values fall back to the default order.
            sort_order: Sort direction ("asc" or "desc").

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

        # Apply ordering: allow-listed sort column, else the default (sku).
        sort_column = _PRODUCT_SORT_COLUMNS.get(sort_by) if sort_by else None
        if sort_column is not None:
            order_by = sort_column.desc() if sort_order == "desc" else sort_column.asc()
        else:
            order_by = Product.sku.asc()

        # Apply pagination. Append the unique `sku` as a tie-breaker so rows
        # with equal sort values keep a stable order across pages (offset
        # pagination over a non-unique sort key is otherwise non-deterministic).
        offset = (page - 1) * page_size
        stmt = stmt.order_by(order_by, Product.sku.asc()).offset(offset).limit(page_size)

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

    async def get_product_lifecycle_curve(
        self,
        db: AsyncSession,
        product_id: int,
        start_date: date | None = None,
        end_date: date | None = None,
    ) -> LifecycleCurveResponse | None:
        """Return the reference lifecycle demand curve for a product (Phase 2).

        Uses the default :class:`LifecycleConfig` ramp parameters. The
        curve respects the product's own ``launch_date`` and
        ``discontinue_date`` but is independent of the ``LifecycleConfig``
        used at seeding time (that config is not persisted). Returns
        ``None`` when the product is not found.

        Args:
            db: Database session.
            product_id: Product primary key.
            start_date: Optional curve start. Defaults to the product's
                ``launch_date`` (or today minus 30 days if launch is
                unset).
            end_date: Optional curve end. Defaults to ``start_date + 365``
                days, clamped to ``discontinue_date`` when set.

        Returns:
            ``LifecycleCurveResponse`` or ``None`` if no product.
        """
        stmt = select(Product).where(Product.id == product_id)
        result = await db.execute(stmt)
        product = result.scalar_one_or_none()
        if product is None:
            return None

        launch = product.launch_date
        discontinue = product.discontinue_date
        # Default the curve window around the product's lifecycle dates.
        # When launch_date is unset, fall back to a recent 1-year window
        # so callers get a usable response (the multiplier short-circuits
        # to 1.0 and the stage is ``maturity``).
        if start_date is None:
            start_date = launch or (datetime.now(UTC).date() - timedelta(days=30))
        if end_date is None:
            end_date = start_date + timedelta(days=365)
            if discontinue is not None and discontinue < end_date:
                end_date = discontinue

        if end_date < start_date:
            end_date = start_date

        config = LifecycleConfig(enable=True)
        generator = LifecycleGenerator(config)

        points: list[LifecyclePoint] = []
        current = start_date
        while current <= end_date:
            points.append(
                LifecyclePoint(
                    date=current,
                    stage=generator.stage_for(current, launch, discontinue),
                    multiplier=generator.multiplier_for(current, launch, discontinue),
                )
            )
            current += timedelta(days=1)

        logger.info(
            "dimensions.lifecycle_curve_computed",
            product_id=product_id,
            launch_date=str(launch) if launch else None,
            discontinue_date=str(discontinue) if discontinue else None,
            points=len(points),
        )

        return LifecycleCurveResponse(
            product_id=product.id,
            sku=product.sku,
            launch_date=launch,
            discontinue_date=discontinue,
            start_date=start_date,
            end_date=end_date,
            points=points,
            total=len(points),
        )
