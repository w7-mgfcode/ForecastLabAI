"""Example: Inspecting time-series CV splits.

Demonstrates how the TimeSeriesSplitter generates splits for
both expanding and sliding window strategies.

Usage:
    python examples/backtest/inspect_splits.py
"""

from datetime import date, timedelta

import numpy as np

from app.features.backtesting.schemas import SplitConfig
from app.features.backtesting.splitter import TimeSeriesSplitter


def print_splits(title: str, config: SplitConfig, dates: list[date], values: np.ndarray) -> None:
    """Print split details for visualization."""
    print("=" * 70)
    print(f"{title}")
    print("=" * 70)
    print(f"Strategy: {config.strategy}")
    print(f"N Splits: {config.n_splits}")
    print(f"Min Train Size: {config.min_train_size}")
    print(f"Gap: {config.gap}")
    print(f"Horizon: {config.horizon}")
    print(f"Total Data: {len(dates)} observations ({dates[0]} to {dates[-1]})")
    print()

    splitter = TimeSeriesSplitter(config)

    for split in splitter.split(dates, values):
        print(f"--- Fold {split.fold_index} ---")
        print(f"  Train: indices [{split.train_indices[0]}:{split.train_indices[-1]+1}]")
        print(f"         dates  {split.train_dates[0]} to {split.train_dates[-1]}")
        print(f"         size   {len(split.train_indices)} observations")

        if config.gap > 0:
            gap_start = split.train_dates[-1] + timedelta(days=1)
            gap_end = split.test_dates[0] - timedelta(days=1)
            print(f"  Gap:   {gap_start} to {gap_end} ({config.gap} days)")

        print(f"  Test:  indices [{split.test_indices[0]}:{split.test_indices[-1]+1}]")
        print(f"         dates  {split.test_dates[0]} to {split.test_dates[-1]}")
        print(f"         size   {len(split.test_indices)} observations")
        print()

    # Print boundaries summary
    print("Boundaries Summary:")
    boundaries = splitter.get_boundaries(dates, values)
    for b in boundaries:
        print(
            f"  Fold {b.fold_index}: "
            f"train[{b.train_size}] → gap[{config.gap}] → test[{b.test_size}]"
        )


def main():
    # Create sample data (90 days)
    start_date = date(2024, 1, 1)
    n_days = 90
    dates = [start_date + timedelta(days=i) for i in range(n_days)]
    values = np.sin(np.linspace(0, 4 * np.pi, n_days)) * 50 + 100

    # Example 1: Expanding Window
    expanding_config = SplitConfig(
        strategy="expanding",
        n_splits=4,
        min_train_size=20,
        gap=0,
        horizon=10,
    )
    print_splits("EXPANDING WINDOW STRATEGY", expanding_config, dates, values)

    print("\n" + "=" * 70 + "\n")

    # Example 2: Sliding Window
    sliding_config = SplitConfig(
        strategy="sliding",
        n_splits=4,
        min_train_size=30,
        gap=0,
        horizon=10,
    )
    print_splits("SLIDING WINDOW STRATEGY", sliding_config, dates, values)

    print("\n" + "=" * 70 + "\n")

    # Example 3: With Gap
    gap_config = SplitConfig(
        strategy="expanding",
        n_splits=3,
        min_train_size=20,
        gap=7,
        horizon=10,
    )
    print_splits("EXPANDING WITH 7-DAY GAP", gap_config, dates, values)

    print("\n" + "=" * 70 + "\n")

    # Visual representation
    print("VISUAL REPRESENTATION (Expanding)")
    print("=" * 70)
    print("Each row represents a fold. 'T' = train, 'G' = gap, 'E' = test\n")

    # Use smaller dataset for visualization
    dates_small = dates[:50]
    values_small = values[:50]
    config_small = SplitConfig(
        strategy="expanding",
        n_splits=3,
        min_train_size=10,
        gap=3,
        horizon=5,
    )
    splitter = TimeSeriesSplitter(config_small)

    for split in splitter.split(dates_small, values_small):
        row = ["."] * len(dates_small)

        for i in split.train_indices:
            row[i] = "T"

        gap_start_idx = split.train_indices[-1] + 1
        gap_end_idx = split.test_indices[0]
        for i in range(gap_start_idx, gap_end_idx):
            row[i] = "G"

        for i in split.test_indices:
            row[i] = "E"

        print(f"Fold {split.fold_index}: {''.join(row)}")

    print("\nLegend: T=Train, G=Gap, E=Test (Evaluation), .=Unused")


if __name__ == "__main__":
    main()
