"""Tests for backtesting schemas."""

import pytest
from pydantic import ValidationError

from app.features.backtesting.schemas import (
    BacktestConfig,
    BacktestRequest,
    FoldResult,
    ModelBacktestResult,
    SplitBoundary,
    SplitConfig,
)
from app.features.forecasting.schemas import NaiveModelConfig


class TestSplitConfig:
    """Tests for SplitConfig schema."""

    def test_default_values(self):
        """Test SplitConfig has correct default values."""
        config = SplitConfig()

        assert config.strategy == "expanding"
        assert config.n_splits == 5
        assert config.min_train_size == 30
        assert config.gap == 0
        assert config.horizon == 14

    def test_expanding_strategy(self):
        """Test expanding strategy is valid."""
        config = SplitConfig(strategy="expanding")
        assert config.strategy == "expanding"

    def test_sliding_strategy(self):
        """Test sliding strategy is valid."""
        config = SplitConfig(strategy="sliding")
        assert config.strategy == "sliding"

    def test_invalid_strategy_raises(self):
        """Test invalid strategy raises validation error."""
        with pytest.raises(ValidationError):
            SplitConfig(strategy="random")  # type: ignore

    def test_n_splits_minimum(self):
        """Test n_splits must be at least 2."""
        with pytest.raises(ValidationError):
            SplitConfig(n_splits=1)

    def test_n_splits_maximum(self):
        """Test n_splits must be at most 20."""
        with pytest.raises(ValidationError):
            SplitConfig(n_splits=21)

    def test_min_train_size_minimum(self):
        """Test min_train_size must be at least 7."""
        with pytest.raises(ValidationError):
            SplitConfig(min_train_size=6)

    def test_gap_minimum(self):
        """Test gap must be non-negative."""
        with pytest.raises(ValidationError):
            SplitConfig(gap=-1)

    def test_gap_maximum(self):
        """Test gap must be at most 30."""
        with pytest.raises(ValidationError):
            SplitConfig(gap=31)

    def test_horizon_minimum(self):
        """Test horizon must be at least 1."""
        with pytest.raises(ValidationError):
            SplitConfig(horizon=0)

    def test_horizon_maximum(self):
        """Test horizon must be at most 90."""
        with pytest.raises(ValidationError):
            SplitConfig(horizon=91)

    def test_horizon_must_be_greater_than_gap(self):
        """Test horizon must be greater than gap."""
        with pytest.raises(ValidationError) as exc_info:
            SplitConfig(horizon=5, gap=5)
        assert "horizon (5) must be greater than gap (5)" in str(exc_info.value)

    def test_horizon_greater_than_gap_valid(self):
        """Test horizon > gap is valid."""
        config = SplitConfig(horizon=10, gap=5)
        assert config.horizon == 10
        assert config.gap == 5

    def test_frozen_config(self):
        """Test SplitConfig is immutable."""
        config = SplitConfig()
        with pytest.raises(ValidationError):
            config.n_splits = 10  # type: ignore[misc]


class TestBacktestConfig:
    """Tests for BacktestConfig schema."""

    def test_default_values(self):
        """Test BacktestConfig has correct default values."""
        config = BacktestConfig(model_config_main=NaiveModelConfig())

        assert config.schema_version == "1.0"
        assert config.include_baselines is True
        assert config.store_fold_details is True

    def test_config_hash_determinism(self):
        """Test config_hash is deterministic."""
        config1 = BacktestConfig(model_config_main=NaiveModelConfig())
        config2 = BacktestConfig(model_config_main=NaiveModelConfig())

        assert config1.config_hash() == config2.config_hash()

    def test_config_hash_changes_with_config(self):
        """Test config_hash changes when config changes."""
        config1 = BacktestConfig(
            model_config_main=NaiveModelConfig(),
            include_baselines=True,
        )
        config2 = BacktestConfig(
            model_config_main=NaiveModelConfig(),
            include_baselines=False,
        )

        assert config1.config_hash() != config2.config_hash()

    def test_config_hash_length(self):
        """Test config_hash has correct length."""
        config = BacktestConfig(model_config_main=NaiveModelConfig())
        assert len(config.config_hash()) == 16

    def test_frozen_config(self):
        """Test BacktestConfig is immutable."""
        config = BacktestConfig(model_config_main=NaiveModelConfig())
        with pytest.raises(ValidationError):
            config.include_baselines = False  # type: ignore[misc]

    def test_invalid_schema_version(self):
        """Test invalid schema_version raises error."""
        with pytest.raises(ValidationError):
            BacktestConfig(
                model_config_main=NaiveModelConfig(),
                schema_version="invalid",
            )

    def test_valid_schema_versions(self):
        """Test various valid schema versions."""
        for version in ["1.0", "2.1", "10.20.30"]:
            config = BacktestConfig(
                model_config_main=NaiveModelConfig(),
                schema_version=version,
            )
            assert config.schema_version == version


class TestSplitBoundary:
    """Tests for SplitBoundary schema."""

    def test_split_boundary_creation(self):
        """Test SplitBoundary creation."""
        from datetime import date

        boundary = SplitBoundary(
            fold_index=0,
            train_start=date(2024, 1, 1),
            train_end=date(2024, 1, 30),
            test_start=date(2024, 1, 31),
            test_end=date(2024, 2, 13),
            train_size=30,
            test_size=14,
        )

        assert boundary.fold_index == 0
        assert boundary.train_size == 30
        assert boundary.test_size == 14


class TestFoldResult:
    """Tests for FoldResult schema."""

    def test_fold_result_creation(self):
        """Test FoldResult creation."""
        from datetime import date

        boundary = SplitBoundary(
            fold_index=0,
            train_start=date(2024, 1, 1),
            train_end=date(2024, 1, 30),
            test_start=date(2024, 1, 31),
            test_end=date(2024, 2, 13),
            train_size=30,
            test_size=14,
        )

        result = FoldResult(
            fold_index=0,
            split=boundary,
            dates=[date(2024, 1, 31), date(2024, 2, 1)],
            actuals=[10.0, 20.0],
            predictions=[12.0, 18.0],
            metrics={"mae": 2.0, "smape": 10.0},
        )

        assert result.fold_index == 0
        assert len(result.dates) == 2
        assert result.metrics["mae"] == 2.0


class TestModelBacktestResult:
    """Tests for ModelBacktestResult schema."""

    def test_model_backtest_result_creation(self):
        """Test ModelBacktestResult creation."""
        result = ModelBacktestResult(
            model_type="naive",
            config_hash="abc123",
            fold_results=[],
            aggregated_metrics={"mae": 5.0},
            metric_std={"mae_stability": 10.0},
        )

        assert result.model_type == "naive"
        assert result.aggregated_metrics["mae"] == 5.0


class TestBacktestRequest:
    """Tests for BacktestRequest schema."""

    def test_valid_request(self):
        """Test valid BacktestRequest."""
        from datetime import date

        request = BacktestRequest(
            store_id=1,
            product_id=1,
            start_date=date(2024, 1, 1),
            end_date=date(2024, 6, 30),
            config=BacktestConfig(model_config_main=NaiveModelConfig()),
        )

        assert request.store_id == 1
        assert request.product_id == 1

    def test_end_date_must_be_after_start_date(self):
        """Test end_date must be after start_date."""
        from datetime import date

        with pytest.raises(ValidationError) as exc_info:
            BacktestRequest(
                store_id=1,
                product_id=1,
                start_date=date(2024, 6, 30),
                end_date=date(2024, 1, 1),
                config=BacktestConfig(model_config_main=NaiveModelConfig()),
            )
        assert "end_date must be after start_date" in str(exc_info.value)

    def test_store_id_must_be_positive(self):
        """Test store_id must be positive."""
        from datetime import date

        with pytest.raises(ValidationError):
            BacktestRequest(
                store_id=0,
                product_id=1,
                start_date=date(2024, 1, 1),
                end_date=date(2024, 6, 30),
                config=BacktestConfig(model_config_main=NaiveModelConfig()),
            )

    def test_product_id_must_be_positive(self):
        """Test product_id must be positive."""
        from datetime import date

        with pytest.raises(ValidationError):
            BacktestRequest(
                store_id=1,
                product_id=0,
                start_date=date(2024, 1, 1),
                end_date=date(2024, 6, 30),
                config=BacktestConfig(model_config_main=NaiveModelConfig()),
            )
