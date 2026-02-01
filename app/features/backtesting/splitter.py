"""Time-series splitter for backtesting cross-validation.

CRITICAL: Respects temporal order - no future data in training.

Supports two strategies:
- Expanding: Training window grows with each fold (start stays at 0)
- Sliding: Training window slides forward (both start and end move)

Gap parameter simulates operational data latency.
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass
from datetime import date as date_type
from typing import TYPE_CHECKING, Any

import numpy as np

from app.features.backtesting.schemas import SplitBoundary, SplitConfig

if TYPE_CHECKING:
    pass


@dataclass
class TimeSeriesSplit:
    """A single train/test split with indices and dates.

    Attributes:
        fold_index: Index of the fold (0-based).
        train_indices: Numpy array of training indices.
        test_indices: Numpy array of test indices.
        train_dates: List of training dates.
        test_dates: List of test dates.
    """

    fold_index: int
    train_indices: np.ndarray[Any, np.dtype[np.intp]]
    test_indices: np.ndarray[Any, np.dtype[np.intp]]
    train_dates: list[date_type]
    test_dates: list[date_type]


class TimeSeriesSplitter:
    """Generate time-based CV splits with expanding or sliding window.

    CRITICAL: Respects temporal order - no future data in training.

    Expanding Window Example (n_splits=3, min_train=30, horizon=14):
        Fold 0: [0..30] train, [30..44] test
        Fold 1: [0..44] train, [44..58] test  (training grows)
        Fold 2: [0..58] train, [58..72] test

    Sliding Window Example (n_splits=3, min_train=30, horizon=14):
        Fold 0: [0..30] train, [30..44] test
        Fold 1: [14..44] train, [44..58] test  (training slides)
        Fold 2: [28..58] train, [58..72] test

    Gap Parameter:
        gap=1 inserts 1 sample between train_end and test_start
        This simulates operational data latency

    Attributes:
        config: Split configuration.
    """

    def __init__(self, config: SplitConfig) -> None:
        """Initialize the splitter.

        Args:
            config: Split configuration.
        """
        self.config = config

    def split(
        self,
        dates: list[date_type],
        y: np.ndarray[Any, np.dtype[np.floating[Any]]],
    ) -> Iterator[TimeSeriesSplit]:
        """Generate train/test splits.

        Args:
            dates: Sorted list of dates (must match y length).
            y: Target values array.

        Yields:
            TimeSeriesSplit objects for each fold.

        Raises:
            ValueError: If data is insufficient for requested splits.
        """
        n_samples = len(dates)
        min_required = self.config.min_train_size + self.config.gap + self.config.horizon

        if n_samples < min_required:
            raise ValueError(
                f"Need at least {min_required} samples, got {n_samples}. "
                f"(min_train={self.config.min_train_size}, gap={self.config.gap}, "
                f"horizon={self.config.horizon})"
            )

        if len(y) != n_samples:
            raise ValueError(f"dates and y must have same length: {n_samples} vs {len(y)}")

        test_size = self.config.horizon
        n_splits = self.config.n_splits
        gap = self.config.gap

        # Calculate available space for test sets
        # We need: min_train_size + gap + (n_splits * test_size)
        total_needed = self.config.min_train_size + gap + (n_splits * test_size)

        if n_samples < total_needed:
            # Reduce number of splits if not enough data
            available_for_tests = n_samples - self.config.min_train_size - gap
            actual_splits = max(1, available_for_tests // test_size)
            n_splits = min(n_splits, actual_splits)

        # Calculate step size between folds
        # For expanding: step moves the test window forward
        # For sliding: step moves both train and test windows forward
        if n_splits > 1:
            # Total space available for test windows after first fold
            available_space = n_samples - self.config.min_train_size - gap - test_size
            step = max(1, available_space // (n_splits - 1))
        else:
            step = test_size

        for fold_idx in range(n_splits):
            if self.config.strategy == "expanding":
                # Expanding: training always starts at 0
                train_start_idx = 0
                train_end_idx = self.config.min_train_size + (fold_idx * step)
            else:
                # Sliding: training window moves forward
                train_start_idx = fold_idx * step
                train_end_idx = train_start_idx + self.config.min_train_size

            # Test starts after gap from train end
            test_start_idx = train_end_idx + gap
            test_end_idx = test_start_idx + test_size

            # Bounds check
            if test_end_idx > n_samples:
                break

            if train_end_idx > n_samples:
                break

            yield TimeSeriesSplit(
                fold_index=fold_idx,
                train_indices=np.arange(train_start_idx, train_end_idx),
                test_indices=np.arange(test_start_idx, test_end_idx),
                train_dates=dates[train_start_idx:train_end_idx],
                test_dates=dates[test_start_idx:test_end_idx],
            )

    def get_boundaries(
        self,
        dates: list[date_type],
        y: np.ndarray[Any, np.dtype[np.floating[Any]]],
    ) -> list[SplitBoundary]:
        """Get split boundaries without full split objects.

        Args:
            dates: Sorted list of dates.
            y: Target values array.

        Returns:
            List of SplitBoundary objects.
        """
        boundaries: list[SplitBoundary] = []
        for split in self.split(dates, y):
            boundaries.append(
                SplitBoundary(
                    fold_index=split.fold_index,
                    train_start=split.train_dates[0],
                    train_end=split.train_dates[-1],
                    test_start=split.test_dates[0],
                    test_end=split.test_dates[-1],
                    train_size=len(split.train_indices),
                    test_size=len(split.test_indices),
                )
            )
        return boundaries

    def validate_no_leakage(
        self,
        dates: list[date_type],
        y: np.ndarray[Any, np.dtype[np.floating[Any]]],
    ) -> bool:
        """Validate that no future data leaks into training.

        Checks that for all folds:
        1. train_end < test_start
        2. Gap is respected
        3. No overlap between train and test indices

        Args:
            dates: Sorted list of dates.
            y: Target values array.

        Returns:
            True if no leakage detected, False otherwise.
        """
        for split in self.split(dates, y):
            # Check train_end < test_start
            if split.train_dates[-1] >= split.test_dates[0]:
                return False

            # Check gap is respected
            train_end_idx = split.train_indices[-1]
            test_start_idx = split.test_indices[0]
            actual_gap = test_start_idx - train_end_idx - 1
            if actual_gap < self.config.gap:
                return False

            # Check no overlap
            train_set = set(split.train_indices.tolist())
            test_set = set(split.test_indices.tolist())
            if train_set & test_set:
                return False

        return True
