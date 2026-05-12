"""Integration tests for Phase 2 retail-depth schema constraints.

Covers the new SQL CHECK constraints + the ``replenishment_event`` table.
Requires PostgreSQL (docker-compose up -d).
"""

from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.features.data_platform.models import (
    Calendar,
    Product,
    Promotion,
    ReplenishmentEvent,
    SalesDaily,
    Store,
)


@pytest.mark.integration
class TestSalesDailyChannelConstraint:
    async def test_default_channel_is_in_store(
        self,
        db_session: AsyncSession,
        sample_store: Store,
        sample_product: Product,
        sample_calendar: Calendar,
    ) -> None:
        # ``channel`` has a server default; not supplying it must still
        # produce a row with ``in_store``.
        sale = SalesDaily(
            date=sample_calendar.date,
            store_id=sample_store.id,
            product_id=sample_product.id,
            quantity=3,
            unit_price=Decimal("9.99"),
            total_amount=Decimal("29.97"),
        )
        db_session.add(sale)
        await db_session.commit()
        await db_session.refresh(sale)
        assert sale.channel == "in_store"

    @pytest.mark.parametrize("channel", ["in_store", "online", "click_collect", "wholesale"])
    async def test_allowed_channels(
        self,
        db_session: AsyncSession,
        sample_store: Store,
        sample_product: Product,
        sample_calendar: Calendar,
        channel: str,
    ) -> None:
        sale = SalesDaily(
            date=sample_calendar.date,
            store_id=sample_store.id,
            product_id=sample_product.id,
            quantity=1,
            unit_price=Decimal("1.00"),
            total_amount=Decimal("1.00"),
            channel=channel,
        )
        db_session.add(sale)
        await db_session.commit()
        await db_session.refresh(sale)
        assert sale.channel == channel

    async def test_disallowed_channel_rejected(
        self,
        db_session: AsyncSession,
        sample_store: Store,
        sample_product: Product,
        sample_calendar: Calendar,
    ) -> None:
        sale = SalesDaily(
            date=sample_calendar.date,
            store_id=sample_store.id,
            product_id=sample_product.id,
            quantity=1,
            unit_price=Decimal("1.00"),
            total_amount=Decimal("1.00"),
            channel="kiosk",  # not in the allow-list
        )
        db_session.add(sale)
        with pytest.raises(IntegrityError):
            await db_session.commit()


@pytest.mark.integration
class TestProductLifecycleConstraints:
    async def test_lifecycle_stage_nullable(self, db_session: AsyncSession) -> None:
        # Lifecycle disabled scenarios must continue inserting bare products
        # without supplying lifecycle fields.
        product = Product(sku="SKU-TEST-LCNULL", name="Lifecycle Null")
        db_session.add(product)
        await db_session.commit()
        await db_session.refresh(product)
        assert product.lifecycle_stage is None
        assert product.launch_date is None
        assert product.discontinue_date is None
        assert product.pack_size is None
        assert product.subcategory is None

    @pytest.mark.parametrize("stage", ["intro", "growth", "maturity", "decline", "discontinued"])
    async def test_lifecycle_stage_allowlist(self, db_session: AsyncSession, stage: str) -> None:
        product = Product(
            sku=f"SKU-TEST-LC-{stage}",
            name=f"Stage {stage}",
            lifecycle_stage=stage,
        )
        db_session.add(product)
        await db_session.commit()
        await db_session.refresh(product)
        assert product.lifecycle_stage == stage

    async def test_invalid_lifecycle_stage_rejected(self, db_session: AsyncSession) -> None:
        product = Product(
            sku="SKU-TEST-LCBAD",
            name="Bad Stage",
            lifecycle_stage="ramping_up",  # not in allow-list
        )
        db_session.add(product)
        with pytest.raises(IntegrityError):
            await db_session.commit()

    async def test_discontinue_before_launch_rejected(self, db_session: AsyncSession) -> None:
        product = Product(
            sku="SKU-TEST-LCDATE",
            name="Bad Dates",
            launch_date=date(2024, 6, 1),
            discontinue_date=date(2024, 5, 1),
        )
        db_session.add(product)
        with pytest.raises(IntegrityError):
            await db_session.commit()

    async def test_negative_pack_size_rejected(self, db_session: AsyncSession) -> None:
        product = Product(
            sku="SKU-TEST-PACK",
            name="Bad Pack",
            pack_size=0,
        )
        db_session.add(product)
        with pytest.raises(IntegrityError):
            await db_session.commit()


@pytest.mark.integration
class TestPromotionKindConstraints:
    async def test_default_kind_is_pct_off(
        self,
        db_session: AsyncSession,
        sample_product: Product,
    ) -> None:
        promo = Promotion(
            product_id=sample_product.id,
            name="Default kind",
            discount_pct=Decimal("0.10"),
            start_date=date(2024, 6, 1),
            end_date=date(2024, 6, 7),
        )
        db_session.add(promo)
        await db_session.commit()
        await db_session.refresh(promo)
        assert promo.kind == "pct_off"
        assert promo.bundle_member_product_ids is None

    @pytest.mark.parametrize("kind", ["pct_off", "markdown"])
    async def test_non_bundle_kinds_reject_member_ids(
        self,
        db_session: AsyncSession,
        sample_product: Product,
        kind: str,
    ) -> None:
        promo = Promotion(
            product_id=sample_product.id,
            name=f"{kind} with bundle members",
            kind=kind,
            discount_pct=Decimal("0.10"),
            start_date=date(2024, 6, 1),
            end_date=date(2024, 6, 7),
            bundle_member_product_ids=[1, 2],
        )
        db_session.add(promo)
        with pytest.raises(IntegrityError):
            await db_session.commit()

    @pytest.mark.parametrize("kind", ["bundle", "bogo"])
    async def test_bundle_kinds_require_member_ids(
        self,
        db_session: AsyncSession,
        sample_product: Product,
        kind: str,
    ) -> None:
        promo = Promotion(
            product_id=sample_product.id,
            name=f"{kind} without bundle members",
            kind=kind,
            discount_pct=Decimal("0.10"),
            start_date=date(2024, 6, 1),
            end_date=date(2024, 6, 7),
            bundle_member_product_ids=None,
        )
        db_session.add(promo)
        with pytest.raises(IntegrityError):
            await db_session.commit()

    async def test_bundle_kind_accepts_member_ids(
        self,
        db_session: AsyncSession,
        sample_product: Product,
    ) -> None:
        promo = Promotion(
            product_id=sample_product.id,
            name="Bundle accepted",
            kind="bundle",
            discount_pct=Decimal("0.15"),
            start_date=date(2024, 6, 1),
            end_date=date(2024, 6, 7),
            bundle_member_product_ids=[sample_product.id, 999],
        )
        db_session.add(promo)
        await db_session.commit()
        await db_session.refresh(promo)
        assert promo.kind == "bundle"
        assert promo.bundle_member_product_ids == [sample_product.id, 999]

    async def test_unknown_kind_rejected(
        self,
        db_session: AsyncSession,
        sample_product: Product,
    ) -> None:
        promo = Promotion(
            product_id=sample_product.id,
            name="Unknown kind",
            kind="loyalty",
            discount_pct=Decimal("0.10"),
            start_date=date(2024, 6, 1),
            end_date=date(2024, 6, 7),
        )
        db_session.add(promo)
        with pytest.raises(IntegrityError):
            await db_session.commit()


@pytest.mark.integration
class TestReplenishmentEventTable:
    async def test_insert_minimal_row(
        self,
        db_session: AsyncSession,
        sample_store: Store,
        sample_product: Product,
        sample_calendar: Calendar,
    ) -> None:
        event = ReplenishmentEvent(
            date=sample_calendar.date,
            store_id=sample_store.id,
            product_id=sample_product.id,
            lead_time_days=5,
            ordered_qty=100,
            received_qty=100,
        )
        db_session.add(event)
        await db_session.commit()
        await db_session.refresh(event)
        assert event.id is not None
        assert event.lead_time_days == 5

    async def test_received_exceeds_ordered_rejected(
        self,
        db_session: AsyncSession,
        sample_store: Store,
        sample_product: Product,
        sample_calendar: Calendar,
    ) -> None:
        event = ReplenishmentEvent(
            date=sample_calendar.date,
            store_id=sample_store.id,
            product_id=sample_product.id,
            lead_time_days=3,
            ordered_qty=50,
            received_qty=51,  # > ordered
        )
        db_session.add(event)
        with pytest.raises(IntegrityError):
            await db_session.commit()

    async def test_negative_lead_time_rejected(
        self,
        db_session: AsyncSession,
        sample_store: Store,
        sample_product: Product,
        sample_calendar: Calendar,
    ) -> None:
        event = ReplenishmentEvent(
            date=sample_calendar.date,
            store_id=sample_store.id,
            product_id=sample_product.id,
            lead_time_days=-1,
            ordered_qty=10,
            received_qty=10,
        )
        db_session.add(event)
        with pytest.raises(IntegrityError):
            await db_session.commit()
