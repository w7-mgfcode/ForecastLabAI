"""Phase 2 retail-data enrichment — additive only.

Runs only the Phase 2 generators (replenishment, exogenous, returns, lifecycle)
against the EXISTING seeded dimensions and calendar. Does NOT touch Phase 1
fact rows (sales_daily, price_history, promotion, inventory_snapshot_daily).

Skipped Phase 2 generators: bundles + markdowns. Both require coordinated
writes to promotion/price_history/inventory in lock-step with Phase 1 facts,
which falls outside the additive scope.

Usage:
    uv run python scripts/seed_phase2_only.py --seed 42

Refuses to run unless DATABASE_URL points at localhost / 127.0.0.1.
"""

from __future__ import annotations

import argparse
import asyncio
import random
import sys
from collections.abc import Iterable, Iterator
from datetime import date as date_type
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import get_settings
from app.features.data_platform.models import (
    Calendar,
    ExogenousSignal,
    Product,
    ReplenishmentEvent,
    SalesDaily,
    SalesReturn,
    Store,
)
from app.shared.seeder.config import (
    ExogenousSignalConfig,
    LeadTimeConfig,
    LifecycleConfig,
    ReturnsConfig,
)
from app.shared.seeder.generators.exogenous import ExogenousSignalGenerator
from app.shared.seeder.generators.lifecycle import LifecycleGenerator
from app.shared.seeder.generators.replenishment import ReplenishmentGenerator
from app.shared.seeder.generators.returns import ReturnsGenerator

if TYPE_CHECKING:
    pass


def chunked[U](items: list[U], size: int) -> Iterator[list[U]]:
    for i in range(0, len(items), size):
        yield items[i : i + size]


def _assign_lifecycle(
    rng: random.Random,
    product_ids: list[int],
    seed_start: date_type,
    seed_end: date_type,
    discontinue_probability: float,
) -> dict[int, tuple[date_type, date_type | None, str]]:
    """Assign launch_date / discontinue_date / lifecycle_stage per product.

    launch_date is drawn uniformly across the first ~70% of the seeded range
    so most products have plenty of post-launch sales history. A small
    fraction get a discontinue_date in the last 20% of the range.
    """
    span_days = (seed_end - seed_start).days
    if span_days <= 0:
        raise SystemExit("Seeded calendar must span at least 1 day.")
    launch_window_days = max(1, int(span_days * 0.7))
    out: dict[int, tuple[date_type, date_type | None, str]] = {}
    lc_cfg = LifecycleConfig(enable=True)  # default ramps suit a 877-day range
    lc_gen = LifecycleGenerator(lc_cfg)
    for pid in product_ids:
        offset = rng.randint(0, launch_window_days)
        launch = seed_start.fromordinal(seed_start.toordinal() + offset)
        disc: date_type | None = None
        if rng.random() < discontinue_probability:
            disc_offset = rng.randint(int(span_days * 0.8), span_days)
            disc_candidate = seed_start.fromordinal(seed_start.toordinal() + disc_offset)
            if disc_candidate > launch:
                disc = disc_candidate
        stage = lc_gen.stage_for(seed_end, launch, disc)
        out[pid] = (launch, disc, stage)
    return out


async def main(seed: int, returns_probability: float) -> int:
    settings = get_settings()
    db_url = settings.database_url
    if not any(token in db_url for token in ("localhost", "127.0.0.1")):
        print(f"REFUSING: database_url does not look local: {db_url}", file=sys.stderr)
        return 2

    engine = create_async_engine(db_url)
    Session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    rng = random.Random(seed)

    async with Session() as db:
        store_ids = sorted(r[0] for r in (await db.execute(select(Store.id))).fetchall())
        product_ids = sorted(r[0] for r in (await db.execute(select(Product.id))).fetchall())
        cal_rows = (await db.execute(select(Calendar.date).order_by(Calendar.date))).fetchall()
        dates = [r[0] for r in cal_rows]
        if not store_ids or not product_ids or not dates:
            print("REFUSING: empty dimensions/calendar. Run seed_random.py first.", file=sys.stderr)
            return 3
        start_date, end_date = dates[0], dates[-1]
        print(f"Phase 2 enrichment (seed={seed})")
        print(
            f"  scope: {len(store_ids)} stores x {len(product_ids)} products x "
            f"{len(dates)} days ({start_date} → {end_date})"
        )

        # ---- 1) Lifecycle: UPDATE product.launch_date / discontinue_date / lifecycle_stage
        lifecycle_map = _assign_lifecycle(
            rng, product_ids, start_date, end_date, discontinue_probability=0.10
        )
        update_count = 0
        for pid, (launch, disc, stage) in lifecycle_map.items():
            await db.execute(
                update(Product)
                .where(Product.id == pid)
                .values(launch_date=launch, discontinue_date=disc, lifecycle_stage=stage)
            )
            update_count += 1
        await db.commit()
        print(f"  ✅ product (lifecycle UPDATE): {update_count:,} rows")

        # ---- 2) Replenishment events
        lt_cfg = LeadTimeConfig(
            enable=True,
            mean_lead_time_days=7,
            lead_time_sigma_days=1.5,
            safety_stock_days=3,
            order_frequency_days=14,
            fill_rate_mean=0.97,
            fill_rate_sigma=0.05,
        )
        rep_gen = ReplenishmentGenerator(rng, lt_cfg)
        rep_records = rep_gen.generate(store_ids, product_ids, dates, base_demand=100)
        for chunk in chunked(rep_records, 2000):
            await db.execute(ReplenishmentEvent.__table__.insert(), chunk)
        await db.commit()
        print(f"  ✅ replenishment_event INSERT: {len(rep_records):,} rows")

        # ---- 3) Exogenous signals (weather + macro)
        ex_cfg = ExogenousSignalConfig(
            enable_weather=True,
            enable_macro=True,
            enable_events=False,
            weather_climatology_mean_c=15.0,
            weather_amplitude_c=12.0,
            weather_noise_sigma_c=2.0,
            macro_initial_value=100.0,
            macro_step_sigma=0.5,
        )
        ex_gen = ExogenousSignalGenerator(rng, ex_cfg)
        ex_records = ex_gen.generate(dates, store_ids)
        for chunk in chunked(ex_records, 2000):
            await db.execute(ExogenousSignal.__table__.insert(), chunk)
        await db.commit()
        print(f"  ✅ exogenous_signal INSERT: {len(ex_records):,} rows")

        # ---- 4) Sales returns (sampled from existing sales_daily)
        ret_cfg = ReturnsConfig(
            enable=True,
            return_probability=returns_probability,
            return_lag_days_min=1,
            return_lag_days_max=14,
            return_quantity_fraction=0.5,
        )
        ret_gen = ReturnsGenerator(rng, ret_cfg)
        sales_rows = (
            await db.execute(
                select(
                    SalesDaily.date,
                    SalesDaily.store_id,
                    SalesDaily.product_id,
                    SalesDaily.quantity,
                ).where(SalesDaily.quantity > 0)
            )
        ).fetchall()
        sales_records: list[dict[str, date_type | int | Decimal]] = [
            {
                "date": r[0],
                "store_id": r[1],
                "product_id": r[2],
                "quantity": int(r[3]),
            }
            for r in sales_rows
        ]
        ret_records = ret_gen.generate(sales_records, end_date)
        for chunk in chunked(ret_records, 2000):
            await db.execute(SalesReturn.__table__.insert(), chunk)
        await db.commit()
        print(
            f"  ✅ sales_returns INSERT: {len(ret_records):,} rows "
            f"(sampled from {len(sales_records):,} positive-qty sales)"
        )

    await engine.dispose()
    print("Done.")
    return 0


def _parse_args(argv: Iterable[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Phase 2 additive seeder (local only).")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument(
        "--returns-probability",
        type=float,
        default=0.02,
        help="Per-sale return probability (default 0.02 → ~2%% of sales).",
    )
    return parser.parse_args(list(argv) if argv is not None else None)


if __name__ == "__main__":
    args = _parse_args()
    sys.exit(asyncio.run(main(args.seed, args.returns_probability)))
