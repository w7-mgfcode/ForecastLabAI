"""V2 sidecar loaders for the forecasting slice (PRP-35).

The V2 builders (``app/shared/feature_frames/rows_v2.py``) consume a pure
``V2HistoricalSidecar`` / ``V2FutureSidecar`` data carrier. This module is the
DB-touching wrapper: every loader is a time-safe SELECT against the
``data_platform`` ORM, and the synchronous assembler helpers convert the
loader outputs into the sidecar dataclasses.

CROSS-SLICE: lives in the forecasting slice — ``app/shared/feature_frames/**``
remains leaf-level. The scenarios slice has its own (smaller) inline
data_platform reads when it needs lifecycle / discontinue date for V2 future
frames.

TIME-SAFETY: every ``where`` clause includes ``<= end_date`` (or the
equivalent ``< day`` event-time filter), so a horizon-day query never reads
beyond the forecast origin ``T``.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import date as date_type
from datetime import timedelta

import structlog
from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.features.data_platform.models import (
    ExogenousSignal,
    InventorySnapshotDaily,
    Product,
    Promotion,
    ReplenishmentEvent,
    SalesReturn,
)
from app.shared.feature_frames import V2FutureSidecar, V2HistoricalSidecar

logger = structlog.get_logger()


# ── Raw async DB loaders ─────────────────────────────────────────────────────


async def load_lifecycle_attrs(
    db: AsyncSession, product_id: int
) -> tuple[date_type | None, date_type | None, str | None]:
    """Return ``(launch_date, discontinue_date, lifecycle_stage)`` for a product.

    Both date fields may be ``None``. ``lifecycle_stage`` may be ``None`` when
    the seeder did not classify the product.
    """
    row = (
        await db.execute(
            select(Product.launch_date, Product.discontinue_date, Product.lifecycle_stage).where(
                Product.id == product_id
            )
        )
    ).first()
    if row is None:
        return None, None, None
    return row.launch_date, row.discontinue_date, row.lifecycle_stage


async def load_inventory_history(
    db: AsyncSession,
    store_id: int,
    product_id: int,
    start_date: date_type,
    end_date: date_type,
) -> dict[date_type, tuple[int, bool]]:
    """``{date: (on_hand_qty, is_stockout)}`` — time-safe filter ``<= end_date``."""
    rows = (
        await db.execute(
            select(
                InventorySnapshotDaily.date,
                InventorySnapshotDaily.on_hand_qty,
                InventorySnapshotDaily.is_stockout,
            ).where(
                and_(
                    InventorySnapshotDaily.store_id == store_id,
                    InventorySnapshotDaily.product_id == product_id,
                    InventorySnapshotDaily.date >= start_date,
                    InventorySnapshotDaily.date <= end_date,
                )
            )
        )
    ).all()
    out: dict[date_type, tuple[int, bool]] = {
        row.date: (row.on_hand_qty, row.is_stockout) for row in rows
    }
    logger.info(
        "forecasting.v2_loaders.inventory_loaded",
        store_id=store_id,
        product_id=product_id,
        n_rows=len(out),
    )
    return out


async def load_replenishment_history(
    db: AsyncSession,
    store_id: int,
    product_id: int,
    start_date: date_type,
    end_date: date_type,
) -> tuple[list[date_type], list[int]]:
    """``(event_dates, received_qty)`` sorted ascending — time-safe filter ``<= end_date``."""
    rows = (
        await db.execute(
            select(ReplenishmentEvent.date, ReplenishmentEvent.received_qty)
            .where(
                and_(
                    ReplenishmentEvent.store_id == store_id,
                    ReplenishmentEvent.product_id == product_id,
                    ReplenishmentEvent.date >= start_date,
                    ReplenishmentEvent.date <= end_date,
                )
            )
            .order_by(ReplenishmentEvent.date)
        )
    ).all()
    dates = [row.date for row in rows]
    qty = [int(row.received_qty) for row in rows]
    logger.info(
        "forecasting.v2_loaders.replenishment_loaded",
        store_id=store_id,
        product_id=product_id,
        n_events=len(dates),
    )
    return dates, qty


async def load_returns_history(
    db: AsyncSession,
    store_id: int,
    product_id: int,
    start_date: date_type,
    end_date: date_type,
) -> dict[date_type, int]:
    """``{date: total_return_quantity}`` — time-safe filter ``<= end_date``."""
    rows = (
        await db.execute(
            select(SalesReturn.date, SalesReturn.return_quantity).where(
                and_(
                    SalesReturn.store_id == store_id,
                    SalesReturn.product_id == product_id,
                    SalesReturn.date >= start_date,
                    SalesReturn.date <= end_date,
                )
            )
        )
    ).all()
    per_day: dict[date_type, int] = defaultdict(int)
    for row in rows:
        per_day[row.date] += int(row.return_quantity)
    logger.info(
        "forecasting.v2_loaders.returns_loaded",
        store_id=store_id,
        product_id=product_id,
        n_days_with_returns=len(per_day),
    )
    return dict(per_day)


async def load_promotion_history(
    db: AsyncSession,
    store_id: int,
    product_id: int,
    start_date: date_type,
    end_date: date_type,
) -> dict[date_type, tuple[frozenset[str], float]]:
    """``{date: (kinds, max_discount_pct)}`` — expanded per-day from promo spans.

    Each day in the training window is mapped to the set of active promo kinds
    that day plus the maximum discount_pct active that day. ``discount_pct``
    may be ``None`` in the DB (e.g. for ``bundle`` kind); treated as 0.0 for
    the per-day aggregation.
    """
    rows = (
        await db.execute(
            select(
                Promotion.start_date,
                Promotion.end_date,
                Promotion.kind,
                Promotion.discount_pct,
            ).where(
                and_(
                    Promotion.product_id == product_id,
                    or_(Promotion.store_id == store_id, Promotion.store_id.is_(None)),
                    Promotion.start_date <= end_date,
                    Promotion.end_date >= start_date,
                )
            )
        )
    ).all()
    per_day_kinds: dict[date_type, set[str]] = defaultdict(set)
    per_day_discount: dict[date_type, float] = {}
    for promo in rows:
        first_day = max(promo.start_date, start_date)
        last_day = min(promo.end_date, end_date)
        discount = float(promo.discount_pct) if promo.discount_pct is not None else 0.0
        day = first_day
        while day <= last_day:
            per_day_kinds[day].add(str(promo.kind))
            existing = per_day_discount.get(day, 0.0)
            if discount > existing:
                per_day_discount[day] = discount
            day += timedelta(days=1)
    out: dict[date_type, tuple[frozenset[str], float]] = {}
    for day, kinds in per_day_kinds.items():
        out[day] = (frozenset(kinds), per_day_discount.get(day, 0.0))
    logger.info(
        "forecasting.v2_loaders.promotion_loaded",
        store_id=store_id,
        product_id=product_id,
        n_promo_days=len(out),
    )
    return out


async def load_exogenous_history(
    db: AsyncSession,
    store_id: int,
    start_date: date_type,
    end_date: date_type,
    signal_names: list[str] | None = None,
) -> dict[date_type, dict[str, float]]:
    """``{date: {signal_name: value}}`` — per-store + global rows merged.

    Time-safe filter ``<= end_date``. Global rows (``is_global=True``) are
    included alongside the per-store rows. When ``signal_names`` is supplied,
    only those signals are returned.
    """
    stmt = select(ExogenousSignal.date, ExogenousSignal.signal_name, ExogenousSignal.value).where(
        and_(
            ExogenousSignal.date >= start_date,
            ExogenousSignal.date <= end_date,
            or_(ExogenousSignal.store_id == store_id, ExogenousSignal.is_global.is_(True)),
        )
    )
    if signal_names is not None:
        stmt = stmt.where(ExogenousSignal.signal_name.in_(signal_names))
    rows = (await db.execute(stmt)).all()
    out: dict[date_type, dict[str, float]] = defaultdict(dict)
    for row in rows:
        out[row.date][row.signal_name] = float(row.value)
    logger.info(
        "forecasting.v2_loaders.exogenous_loaded",
        store_id=store_id,
        n_days=len(out),
        n_signals_filter=len(signal_names) if signal_names is not None else None,
    )
    return dict(out)


# ── Pure sync assemblers (loader outputs → sidecar dataclasses) ─────────────


def assemble_v2_historical_sidecar(
    *,
    dates: list[date_type],
    promo_dates: set[date_type],
    holiday_dates: set[date_type],
    launch_date: date_type | None,
    discontinue_date: date_type | None,
    inventory_per_day: dict[date_type, tuple[int, bool]],
    replenishment_event_dates: list[date_type],
    replenishment_event_qty: list[int],
    returns_per_day: dict[date_type, int],
    promo_per_day: dict[date_type, tuple[frozenset[str], float]],
    weather_per_day: dict[date_type, dict[str, float]],
    macro_per_day: dict[date_type, dict[str, float]],
) -> V2HistoricalSidecar:
    """Build a :class:`V2HistoricalSidecar` from already-loaded DB inputs.

    Per-day arrays are aligned with ``dates``. Days with no entry in
    ``inventory_per_day`` / ``returns_per_day`` / ``promo_per_day`` get the
    safe default (None for on_hand_qty, False for is_stockout, 0 for returns,
    empty frozenset / 0.0 for promo).
    """
    on_hand: list[float | None] = []
    stockout: list[bool] = []
    for day in dates:
        if day in inventory_per_day:
            qty, flag = inventory_per_day[day]
            on_hand.append(float(qty))
            stockout.append(bool(flag))
        else:
            on_hand.append(None)
            stockout.append(False)
    returns_qty = [int(returns_per_day.get(day, 0)) for day in dates]
    promo_kinds_per_day = tuple(promo_per_day.get(day, (frozenset(), 0.0))[0] for day in dates)
    promo_discount = tuple(float(promo_per_day.get(day, (frozenset(), 0.0))[1]) for day in dates)
    return V2HistoricalSidecar(
        promo_dates=frozenset(promo_dates),
        holiday_dates=frozenset(holiday_dates),
        launch_date=launch_date,
        discontinue_date=discontinue_date,
        on_hand_qty=tuple(on_hand),
        is_stockout_per_day=tuple(stockout),
        replenishment_event_dates=tuple(replenishment_event_dates),
        replenishment_event_qty=tuple(replenishment_event_qty),
        returns_qty_per_day=tuple(returns_qty),
        promo_kinds_per_day=promo_kinds_per_day,
        promo_discount_pct_per_day=promo_discount,
        weather_per_day=dict(weather_per_day),
        macro_per_day=dict(macro_per_day),
    )


def assemble_v2_future_sidecar(
    *,
    holiday_dates: set[date_type],
    launch_date: date_type | None,
    discontinue_date: date_type | None,
    price_factor_per_day: list[float | None] | None = None,
    promo_active_per_day: list[bool] | None = None,
    promo_kinds_per_day: list[frozenset[str]] | None = None,
    promo_discount_pct_per_day: list[float] | None = None,
    inventory_on_hand_per_day: list[float | None] | None = None,
    weather_per_day: dict[date_type, dict[str, float]] | None = None,
    macro_per_day: dict[date_type, dict[str, float]] | None = None,
) -> V2FutureSidecar:
    """Build a :class:`V2FutureSidecar` from already-resolved future inputs."""
    return V2FutureSidecar(
        holiday_dates=frozenset(holiday_dates),
        launch_date=launch_date,
        discontinue_date=discontinue_date,
        price_factor_per_day=tuple(price_factor_per_day or ()),
        promo_active_per_day=tuple(promo_active_per_day or ()),
        promo_kinds_per_day=tuple(promo_kinds_per_day or ()),
        promo_discount_pct_per_day=tuple(promo_discount_pct_per_day or ()),
        inventory_on_hand_per_day=tuple(inventory_on_hand_per_day or ()),
        weather_per_day=dict(weather_per_day or {}),
        macro_per_day=dict(macro_per_day or {}),
    )


__all__ = [
    "assemble_v2_future_sidecar",
    "assemble_v2_historical_sidecar",
    "load_exogenous_history",
    "load_inventory_history",
    "load_lifecycle_attrs",
    "load_promotion_history",
    "load_replenishment_history",
    "load_returns_history",
]
