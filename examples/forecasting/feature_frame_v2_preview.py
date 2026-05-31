"""V1 vs V2 feature-frame preview (PRP-35).

Read-only diagnostic — dumps the V1 and V2 feature-column lists side by side
plus the first three rows of each matrix for a given ``(store_id, product_id,
cutoff_date)``. Also prints per-group NaN counts in the V2 matrix so a
developer can spot when a smaller seeded DB lacks the source data for a
specific opt-in group.

Local-development only — no network egress, no DB writes. Requires
``docker compose up -d`` for the local Postgres.

Usage:
  uv run python examples/forecasting/feature_frame_v2_preview.py \\
      --store-id 15 --product-id 52 --cutoff-date 2025-12-31 \\
      [--groups target_history,calendar,rolling]
"""

from __future__ import annotations

import argparse
import asyncio
import math
from datetime import date as date_type

from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.config import get_settings
from app.features.forecasting.service import (
    ForecastingService,
    _resolve_feature_groups,
)
from app.shared.feature_frames import FeatureGroup


async def _run(args: argparse.Namespace) -> None:
    settings = get_settings()
    engine = create_async_engine(settings.database_url, echo=False)
    session_maker = async_sessionmaker(engine, expire_on_commit=False)

    service = ForecastingService()
    start_date = date_type.fromisoformat(args.start_date)
    end_date = date_type.fromisoformat(args.cutoff_date)

    groups_input = args.groups.split(",") if args.groups else None
    resolved_groups: tuple[FeatureGroup, ...] = (
        _resolve_feature_groups(groups_input) if groups_input is not None else ()
    )

    async with session_maker() as session:
        try:
            v1 = await service._build_regression_features(
                db=session,
                store_id=args.store_id,
                product_id=args.product_id,
                start_date=start_date,
                end_date=end_date,
            )
            print(f"V1 — {len(v1.feature_columns)} columns:")
            print("  " + ", ".join(v1.feature_columns))
            print("V1 — first 3 rows:")
            for row in v1.X[:3]:
                print("  " + ", ".join(f"{v:.3f}" if not math.isnan(v) else "nan" for v in row))
            print()
        except ValueError as exc:
            print(f"V1 build skipped: {exc}")

        try:
            v2 = await service._build_regression_features_v2(
                db=session,
                store_id=args.store_id,
                product_id=args.product_id,
                start_date=start_date,
                end_date=end_date,
                groups=resolved_groups if resolved_groups else (FeatureGroup.TARGET_HISTORY,),
            )
            print(f"V2 — {len(v2.feature_columns)} columns:")
            print("  " + ", ".join(v2.feature_columns))
            print("V2 — first 3 rows:")
            for row in v2.X[:3]:
                print("  " + ", ".join(f"{v:.3f}" if not math.isnan(v) else "nan" for v in row))
            print()
            # Per-group NaN counts
            print("V2 — NaN counts per column:")
            for i, name in enumerate(v2.feature_columns):
                nan_count = int(sum(1 for row in v2.X if math.isnan(row[i])))
                if nan_count:
                    print(f"  {name}: {nan_count}/{len(v2.X)}")
        except ValueError as exc:
            print(f"V2 build skipped: {exc}")

    await engine.dispose()


def main() -> None:
    parser = argparse.ArgumentParser(description="V1 vs V2 feature-frame preview")
    parser.add_argument("--store-id", type=int, required=True)
    parser.add_argument("--product-id", type=int, required=True)
    parser.add_argument("--start-date", type=str, default="2025-01-01")
    parser.add_argument("--cutoff-date", type=str, required=True)
    parser.add_argument(
        "--groups",
        type=str,
        default=None,
        help="Comma-separated FeatureGroup names; default → DEFAULT_V2_GROUPS",
    )
    args = parser.parse_args()
    asyncio.run(_run(args))


if __name__ == "__main__":
    main()
