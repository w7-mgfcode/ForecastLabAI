"""Integration tests for database constraint enforcement.

These tests require a running PostgreSQL database.
Mark with @pytest.mark.integration.
"""

from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.features.data_platform.models import (
    Calendar,
    InventorySnapshotDaily,
    Product,
    SalesDaily,
    Store,
)


@pytest.mark.integration
class TestSalesDailyConstraints:
    """Integration tests for SalesDaily constraints."""

    async def test_unique_constraint_prevents_duplicates(
        self,
        db_session: AsyncSession,
        sample_store: Store,
        sample_product: Product,
        sample_calendar: Calendar,
    ):
        """Inserting duplicate grain should raise IntegrityError."""
        # First insert should succeed
        sale1 = SalesDaily(
            date=sample_calendar.date,
            store_id=sample_store.id,
            product_id=sample_product.id,
            quantity=10,
            unit_price=Decimal("9.99"),
            total_amount=Decimal("99.90"),
        )
        db_session.add(sale1)
        await db_session.commit()

        # Second insert with same grain should fail
        sale2 = SalesDaily(
            date=sample_calendar.date,
            store_id=sample_store.id,
            product_id=sample_product.id,
            quantity=5,
            unit_price=Decimal("9.99"),
            total_amount=Decimal("49.95"),
        )
        db_session.add(sale2)

        with pytest.raises(IntegrityError):
            await db_session.commit()

    async def test_foreign_key_constraint_enforced(self, db_session: AsyncSession):
        """Inserting with invalid foreign key should raise IntegrityError."""
        sale = SalesDaily(
            date=date(2024, 1, 1),  # No calendar entry
            store_id=99999,  # Non-existent store
            product_id=99999,  # Non-existent product
            quantity=10,
            unit_price=Decimal("9.99"),
            total_amount=Decimal("99.90"),
        )
        db_session.add(sale)

        with pytest.raises(IntegrityError):
            await db_session.commit()

    async def test_check_constraint_quantity_positive(
        self,
        db_session: AsyncSession,
        sample_store: Store,
        sample_product: Product,
        sample_calendar: Calendar,
    ):
        """Negative quantity should raise IntegrityError."""
        sale = SalesDaily(
            date=sample_calendar.date,
            store_id=sample_store.id,
            product_id=sample_product.id,
            quantity=-5,  # Invalid: negative
            unit_price=Decimal("9.99"),
            total_amount=Decimal("99.90"),
        )
        db_session.add(sale)

        with pytest.raises(IntegrityError):
            await db_session.commit()

    async def test_check_constraint_price_positive(
        self,
        db_session: AsyncSession,
        sample_store: Store,
        sample_product: Product,
        sample_calendar: Calendar,
    ):
        """Negative price should raise IntegrityError."""
        sale = SalesDaily(
            date=sample_calendar.date,
            store_id=sample_store.id,
            product_id=sample_product.id,
            quantity=10,
            unit_price=Decimal("-9.99"),  # Invalid: negative
            total_amount=Decimal("99.90"),
        )
        db_session.add(sale)

        with pytest.raises(IntegrityError):
            await db_session.commit()


@pytest.mark.integration
class TestInventorySnapshotDailyConstraints:
    """Integration tests for InventorySnapshotDaily constraints."""

    async def test_unique_constraint_prevents_duplicates(
        self,
        db_session: AsyncSession,
        sample_store: Store,
        sample_product: Product,
        sample_calendar: Calendar,
    ):
        """Inserting duplicate grain should raise IntegrityError."""
        # First insert should succeed
        inv1 = InventorySnapshotDaily(
            date=sample_calendar.date,
            store_id=sample_store.id,
            product_id=sample_product.id,
            on_hand_qty=100,
            on_order_qty=50,
            is_stockout=False,
        )
        db_session.add(inv1)
        await db_session.commit()

        # Second insert with same grain should fail
        inv2 = InventorySnapshotDaily(
            date=sample_calendar.date,
            store_id=sample_store.id,
            product_id=sample_product.id,
            on_hand_qty=200,
            on_order_qty=25,
            is_stockout=False,
        )
        db_session.add(inv2)

        with pytest.raises(IntegrityError):
            await db_session.commit()

    async def test_check_constraint_on_hand_positive(
        self,
        db_session: AsyncSession,
        sample_store: Store,
        sample_product: Product,
        sample_calendar: Calendar,
    ):
        """Negative on_hand_qty should raise IntegrityError."""
        inv = InventorySnapshotDaily(
            date=sample_calendar.date,
            store_id=sample_store.id,
            product_id=sample_product.id,
            on_hand_qty=-10,  # Invalid: negative
            on_order_qty=50,
            is_stockout=True,
        )
        db_session.add(inv)

        with pytest.raises(IntegrityError):
            await db_session.commit()


@pytest.mark.integration
class TestStoreConstraints:
    """Integration tests for Store constraints."""

    async def test_unique_code_constraint(self, db_session: AsyncSession):
        """Duplicate store code should raise IntegrityError."""
        store1 = Store(
            code="STORE001",
            name="First Store",
            region="Region A",
            city="City A",
            store_type="supermarket",
        )
        db_session.add(store1)
        await db_session.commit()

        store2 = Store(
            code="STORE001",  # Duplicate code
            name="Second Store",
            region="Region B",
            city="City B",
            store_type="express",
        )
        db_session.add(store2)

        with pytest.raises(IntegrityError):
            await db_session.commit()


@pytest.mark.integration
class TestProductConstraints:
    """Integration tests for Product constraints."""

    async def test_unique_sku_constraint(self, db_session: AsyncSession):
        """Duplicate product SKU should raise IntegrityError."""
        product1 = Product(
            sku="SKU001",
            name="First Product",
            category="Category A",
            brand="Brand A",
            base_price=Decimal("9.99"),
            base_cost=Decimal("4.99"),
        )
        db_session.add(product1)
        await db_session.commit()

        product2 = Product(
            sku="SKU001",  # Duplicate SKU
            name="Second Product",
            category="Category B",
            brand="Brand B",
            base_price=Decimal("19.99"),
            base_cost=Decimal("9.99"),
        )
        db_session.add(product2)

        with pytest.raises(IntegrityError):
            await db_session.commit()


@pytest.mark.integration
class TestCalendarConstraints:
    """Integration tests for Calendar constraints."""

    async def test_check_constraint_day_of_week(self, db_session: AsyncSession):
        """Invalid day_of_week should raise IntegrityError."""
        cal = Calendar(
            date=date(2024, 2, 1),
            day_of_week=7,  # Invalid: must be 0-6
            month=2,
            quarter=1,
            year=2024,
            is_holiday=False,
        )
        db_session.add(cal)

        with pytest.raises(IntegrityError):
            await db_session.commit()

    async def test_check_constraint_month(self, db_session: AsyncSession):
        """Invalid month should raise IntegrityError."""
        cal = Calendar(
            date=date(2024, 2, 1),
            day_of_week=3,
            month=13,  # Invalid: must be 1-12
            quarter=1,
            year=2024,
            is_holiday=False,
        )
        db_session.add(cal)

        with pytest.raises(IntegrityError):
            await db_session.commit()

    async def test_check_constraint_quarter(self, db_session: AsyncSession):
        """Invalid quarter should raise IntegrityError."""
        cal = Calendar(
            date=date(2024, 2, 1),
            day_of_week=3,
            month=2,
            quarter=5,  # Invalid: must be 1-4
            year=2024,
            is_holiday=False,
        )
        db_session.add(cal)

        with pytest.raises(IntegrityError):
            await db_session.commit()
