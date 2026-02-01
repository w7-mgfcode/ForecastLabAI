"""Tests for time series splitter."""

from datetime import date, timedelta

import numpy as np
import pytest

from app.features.backtesting.schemas import SplitConfig
from app.features.backtesting.splitter import TimeSeriesSplitter


class TestTimeSeriesSplitterInit:
    """Tests for TimeSeriesSplitter initialization."""

    def test_init_with_expanding_strategy(self, sample_split_config_expanding: SplitConfig) -> None:
        """Test splitter initialization with expanding strategy."""
        splitter = TimeSeriesSplitter(sample_split_config_expanding)
        assert splitter.config.strategy == "expanding"

    def test_init_with_sliding_strategy(self, sample_split_config_sliding: SplitConfig) -> None:
        """Test splitter initialization with sliding strategy."""
        splitter = TimeSeriesSplitter(sample_split_config_sliding)
        assert splitter.config.strategy == "sliding"


class TestTimeSeriesSplitterExpanding:
    """Tests for expanding window strategy."""

    def test_expanding_generates_correct_number_of_splits(
        self,
        sample_dates_120: list[date],
        sample_values_120: np.ndarray,
        sample_split_config_expanding: SplitConfig,
    ) -> None:
        """Test expanding strategy generates requested number of splits."""
        splitter = TimeSeriesSplitter(sample_split_config_expanding)
        splits = list(splitter.split(sample_dates_120, sample_values_120))

        assert len(splits) == sample_split_config_expanding.n_splits

    def test_expanding_train_size_increases(
        self,
        sample_dates_120: list[date],
        sample_values_120: np.ndarray,
        sample_split_config_expanding: SplitConfig,
    ) -> None:
        """Test expanding strategy has increasing train sizes."""
        splitter = TimeSeriesSplitter(sample_split_config_expanding)
        splits = list(splitter.split(sample_dates_120, sample_values_120))

        train_sizes = [len(s.train_indices) for s in splits]
        for i in range(1, len(train_sizes)):
            assert train_sizes[i] > train_sizes[i - 1], (
                f"Train size should increase: fold {i - 1}={train_sizes[i - 1]}, "
                f"fold {i}={train_sizes[i]}"
            )

    def test_expanding_first_fold_has_min_train_size(
        self,
        sample_dates_120: list[date],
        sample_values_120: np.ndarray,
        sample_split_config_expanding: SplitConfig,
    ) -> None:
        """Test first fold has minimum train size."""
        splitter = TimeSeriesSplitter(sample_split_config_expanding)
        splits = list(splitter.split(sample_dates_120, sample_values_120))

        assert len(splits[0].train_indices) >= sample_split_config_expanding.min_train_size

    def test_expanding_test_size_equals_horizon(
        self,
        sample_dates_120: list[date],
        sample_values_120: np.ndarray,
        sample_split_config_expanding: SplitConfig,
    ) -> None:
        """Test all folds have test size equal to horizon."""
        splitter = TimeSeriesSplitter(sample_split_config_expanding)
        splits = list(splitter.split(sample_dates_120, sample_values_120))

        for split in splits:
            assert len(split.test_indices) == sample_split_config_expanding.horizon


class TestTimeSeriesSplitterSliding:
    """Tests for sliding window strategy."""

    def test_sliding_generates_correct_number_of_splits(
        self,
        sample_dates_120: list[date],
        sample_values_120: np.ndarray,
        sample_split_config_sliding: SplitConfig,
    ) -> None:
        """Test sliding strategy generates requested number of splits."""
        splitter = TimeSeriesSplitter(sample_split_config_sliding)
        splits = list(splitter.split(sample_dates_120, sample_values_120))

        assert len(splits) == sample_split_config_sliding.n_splits

    def test_sliding_train_size_constant(
        self,
        sample_dates_120: list[date],
        sample_values_120: np.ndarray,
        sample_split_config_sliding: SplitConfig,
    ) -> None:
        """Test sliding strategy has constant train sizes."""
        splitter = TimeSeriesSplitter(sample_split_config_sliding)
        splits = list(splitter.split(sample_dates_120, sample_values_120))

        train_sizes = [len(s.train_indices) for s in splits]
        # All train sizes should be equal
        assert len(set(train_sizes)) == 1, f"Train sizes should be constant: {train_sizes}"

    def test_sliding_window_moves_forward(
        self,
        sample_dates_120: list[date],
        sample_values_120: np.ndarray,
        sample_split_config_sliding: SplitConfig,
    ) -> None:
        """Test sliding window moves forward each fold."""
        splitter = TimeSeriesSplitter(sample_split_config_sliding)
        splits = list(splitter.split(sample_dates_120, sample_values_120))

        for i in range(1, len(splits)):
            assert splits[i].train_indices[0] > splits[i - 1].train_indices[0], (
                f"Sliding window should move forward: "
                f"fold {i - 1} start={splits[i - 1].train_indices[0]}, "
                f"fold {i} start={splits[i].train_indices[0]}"
            )


class TestTimeSeriesSplitterWithGap:
    """Tests for splitter with gap parameter."""

    def test_gap_creates_separation(
        self,
        sample_dates_120: list[date],
        sample_values_120: np.ndarray,
        sample_split_config_with_gap: SplitConfig,
    ) -> None:
        """Test gap creates separation between train and test."""
        splitter = TimeSeriesSplitter(sample_split_config_with_gap)
        splits = list(splitter.split(sample_dates_120, sample_values_120))

        gap = sample_split_config_with_gap.gap
        for split in splits:
            train_end = split.train_indices[-1]
            test_start = split.test_indices[0]
            actual_gap = test_start - train_end - 1
            assert actual_gap == gap, (
                f"Gap should be {gap} but got {actual_gap}: "
                f"train_end={train_end}, test_start={test_start}"
            )

    def test_gap_dates_have_correct_separation(
        self,
        sample_dates_120: list[date],
        sample_values_120: np.ndarray,
        sample_split_config_with_gap: SplitConfig,
    ) -> None:
        """Test gap dates have correct temporal separation."""
        splitter = TimeSeriesSplitter(sample_split_config_with_gap)
        splits = list(splitter.split(sample_dates_120, sample_values_120))

        gap = sample_split_config_with_gap.gap
        for split in splits:
            train_end_date = split.train_dates[-1]
            test_start_date = split.test_dates[0]
            date_diff = (test_start_date - train_end_date).days
            expected_diff = gap + 1
            assert date_diff == expected_diff, (
                f"Date gap should be {expected_diff} days but got {date_diff}: "
                f"train_end={train_end_date}, test_start={test_start_date}"
            )


class TestTimeSeriesSplitterBoundaries:
    """Tests for split boundaries."""

    def test_get_boundaries_returns_all_folds(
        self,
        sample_dates_120: list[date],
        sample_values_120: np.ndarray,
        sample_split_config_expanding: SplitConfig,
    ) -> None:
        """Test get_boundaries returns boundaries for all folds."""
        splitter = TimeSeriesSplitter(sample_split_config_expanding)
        boundaries = splitter.get_boundaries(sample_dates_120, sample_values_120)

        assert len(boundaries) == sample_split_config_expanding.n_splits

    def test_boundaries_have_correct_dates(
        self,
        sample_dates_120: list[date],
        sample_values_120: np.ndarray,
        sample_split_config_expanding: SplitConfig,
    ) -> None:
        """Test boundaries have correct date ranges."""
        splitter = TimeSeriesSplitter(sample_split_config_expanding)
        boundaries = splitter.get_boundaries(sample_dates_120, sample_values_120)

        for boundary in boundaries:
            assert boundary.train_start <= boundary.train_end
            assert boundary.test_start <= boundary.test_end
            assert boundary.train_end < boundary.test_start

    def test_boundaries_have_correct_sizes(
        self,
        sample_dates_120: list[date],
        sample_values_120: np.ndarray,
        sample_split_config_expanding: SplitConfig,
    ) -> None:
        """Test boundaries have correct train and test sizes."""
        splitter = TimeSeriesSplitter(sample_split_config_expanding)
        splits = list(splitter.split(sample_dates_120, sample_values_120))
        boundaries = splitter.get_boundaries(sample_dates_120, sample_values_120)

        for split, boundary in zip(splits, boundaries, strict=True):
            assert boundary.train_size == len(split.train_indices)
            assert boundary.test_size == len(split.test_indices)


class TestTimeSeriesSplitterLeakageValidation:
    """Tests for leakage validation."""

    def test_validate_no_leakage_passes_for_valid_splits(
        self,
        sample_dates_120: list[date],
        sample_values_120: np.ndarray,
        sample_split_config_expanding: SplitConfig,
    ) -> None:
        """Test leakage validation passes for valid splits."""
        splitter = TimeSeriesSplitter(sample_split_config_expanding)
        # Generate splits to populate boundaries
        list(splitter.split(sample_dates_120, sample_values_120))

        result = splitter.validate_no_leakage(sample_dates_120, sample_values_120)
        assert result is True

    def test_train_test_indices_do_not_overlap(
        self,
        sample_dates_120: list[date],
        sample_values_120: np.ndarray,
        sample_split_config_expanding: SplitConfig,
    ) -> None:
        """Test train and test indices never overlap."""
        splitter = TimeSeriesSplitter(sample_split_config_expanding)
        splits = list(splitter.split(sample_dates_120, sample_values_120))

        for split in splits:
            train_set = set(split.train_indices)
            test_set = set(split.test_indices)
            overlap = train_set & test_set
            assert len(overlap) == 0, f"Overlap found in fold {split.fold_index}: {overlap}"

    def test_test_indices_always_after_train(
        self,
        sample_dates_120: list[date],
        sample_values_120: np.ndarray,
        sample_split_config_expanding: SplitConfig,
    ) -> None:
        """Test test indices are always after train indices."""
        splitter = TimeSeriesSplitter(sample_split_config_expanding)
        splits = list(splitter.split(sample_dates_120, sample_values_120))

        for split in splits:
            max_train = max(split.train_indices)
            min_test = min(split.test_indices)
            assert min_test > max_train, (
                f"Test should be after train in fold {split.fold_index}: "
                f"max_train={max_train}, min_test={min_test}"
            )


class TestTimeSeriesSplitterEdgeCases:
    """Tests for edge cases."""

    def test_minimum_data_for_single_split(self) -> None:
        """Test minimum data required for a single split."""
        config = SplitConfig(
            strategy="expanding",
            n_splits=2,
            min_train_size=7,
            gap=0,
            horizon=7,
        )
        splitter = TimeSeriesSplitter(config)

        # Need: min_train_size + horizon * n_splits + step * (n_splits - 1)
        # Minimum: 7 + 7*2 = 21 for 2 splits with no step
        start = date(2024, 1, 1)
        dates = [start + timedelta(days=i) for i in range(30)]
        values = np.arange(30, dtype=np.float64)

        splits = list(splitter.split(dates, values))
        assert len(splits) == 2

    def test_insufficient_data_raises(self) -> None:
        """Test insufficient data raises ValueError."""
        config = SplitConfig(
            strategy="expanding",
            n_splits=5,
            min_train_size=30,
            gap=0,
            horizon=14,
        )
        splitter = TimeSeriesSplitter(config)

        # Too little data
        start = date(2024, 1, 1)
        dates = [start + timedelta(days=i) for i in range(20)]
        values = np.arange(20, dtype=np.float64)

        with pytest.raises(ValueError, match="Need at least"):
            list(splitter.split(dates, values))

    def test_consecutive_dates_preserved(
        self,
        sample_dates_120: list[date],
        sample_values_120: np.ndarray,
        sample_split_config_expanding: SplitConfig,
    ) -> None:
        """Test dates in splits are consecutive."""
        splitter = TimeSeriesSplitter(sample_split_config_expanding)
        splits = list(splitter.split(sample_dates_120, sample_values_120))

        for split in splits:
            # Check train dates are consecutive
            for i in range(1, len(split.train_dates)):
                diff = (split.train_dates[i] - split.train_dates[i - 1]).days
                assert diff == 1, f"Train dates not consecutive in fold {split.fold_index}"

            # Check test dates are consecutive
            for i in range(1, len(split.test_dates)):
                diff = (split.test_dates[i] - split.test_dates[i - 1]).days
                assert diff == 1, f"Test dates not consecutive in fold {split.fold_index}"

    def test_fold_index_is_sequential(
        self,
        sample_dates_120: list[date],
        sample_values_120: np.ndarray,
        sample_split_config_expanding: SplitConfig,
    ) -> None:
        """Test fold indices are sequential starting from 0."""
        splitter = TimeSeriesSplitter(sample_split_config_expanding)
        splits = list(splitter.split(sample_dates_120, sample_values_120))

        for i, split in enumerate(splits):
            assert split.fold_index == i
