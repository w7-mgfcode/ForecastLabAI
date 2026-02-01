"""Unit tests for feature engineering schemas."""

from datetime import date

import pytest
from pydantic import ValidationError

from app.features.featuresets.schemas import (
    CalendarConfig,
    ComputeFeaturesRequest,
    ExogenousConfig,
    FeatureSetConfig,
    ImputationConfig,
    LagConfig,
    RollingConfig,
)


class TestLagConfig:
    """Tests for LagConfig validation."""

    def test_valid_lags(self):
        """Valid positive lags should be accepted."""
        config = LagConfig(lags=(1, 7, 14, 28))
        assert config.lags == (1, 7, 14, 28)

    def test_rejects_negative_lags(self):
        """Negative lags should be rejected (prevents future leakage)."""
        with pytest.raises(ValidationError) as exc_info:
            LagConfig(lags=(-1, 7))

        assert "positive integers" in str(exc_info.value).lower()

    def test_rejects_zero_lag(self):
        """Zero lag should be rejected (current row is not a lag)."""
        with pytest.raises(ValidationError) as exc_info:
            LagConfig(lags=(0, 7))

        assert "positive integers" in str(exc_info.value).lower()

    def test_rejects_empty_lags(self):
        """Empty lags tuple should be rejected."""
        with pytest.raises(ValidationError) as exc_info:
            LagConfig(lags=())

        assert "at least one lag" in str(exc_info.value).lower()

    def test_default_values(self):
        """Default values should be set correctly."""
        config = LagConfig()
        assert config.lags == (1, 7, 14, 28)
        assert config.target_column == "quantity"
        assert config.fill_value is None
        assert config.schema_version == "1.0"


class TestRollingConfig:
    """Tests for RollingConfig validation."""

    def test_valid_windows(self):
        """Valid positive windows should be accepted."""
        config = RollingConfig(windows=(7, 14, 28))
        assert config.windows == (7, 14, 28)

    def test_rejects_negative_windows(self):
        """Negative windows should be rejected."""
        with pytest.raises(ValidationError) as exc_info:
            RollingConfig(windows=(-7, 14))

        assert "positive integers" in str(exc_info.value).lower()

    def test_rejects_empty_windows(self):
        """Empty windows tuple should be rejected."""
        with pytest.raises(ValidationError) as exc_info:
            RollingConfig(windows=())

        assert "at least one window" in str(exc_info.value).lower()

    def test_valid_aggregations(self):
        """Valid aggregation functions should be accepted."""
        config = RollingConfig(aggregations=("mean", "std", "min", "max", "sum"))
        assert len(config.aggregations) == 5


class TestCalendarConfig:
    """Tests for CalendarConfig validation."""

    def test_default_cyclical_encoding(self):
        """Cyclical encoding should be enabled by default."""
        config = CalendarConfig()
        assert config.use_cyclical_encoding is True

    def test_all_features_can_be_disabled(self):
        """All features should be individually disableable."""
        config = CalendarConfig(
            include_day_of_week=False,
            include_month=False,
            include_quarter=False,
            include_year=False,
            include_is_weekend=False,
            include_is_month_end=False,
            include_is_holiday=False,
        )
        assert config.include_day_of_week is False


class TestExogenousConfig:
    """Tests for ExogenousConfig validation."""

    def test_rejects_negative_price_lags(self):
        """Negative price lags should be rejected."""
        with pytest.raises(ValidationError) as exc_info:
            ExogenousConfig(price_lags=(-7, 14))

        assert "positive integers" in str(exc_info.value).lower()


class TestImputationConfig:
    """Tests for ImputationConfig validation."""

    def test_valid_strategies(self):
        """Valid imputation strategies should be accepted."""
        config = ImputationConfig(
            strategies={
                "quantity": "zero",
                "price": "ffill",
                "inventory": "bfill",
                "demand": "mean",
                "forecast": "expanding_mean",
                "optional": "drop",
            }
        )
        assert len(config.strategies) == 6

    def test_rejects_invalid_strategy(self):
        """Invalid strategy should be rejected."""
        with pytest.raises(ValidationError):
            ImputationConfig(strategies={"quantity": "invalid"})  # type: ignore[dict-item]


class TestFeatureSetConfig:
    """Tests for FeatureSetConfig."""

    def test_valid_minimal_config(self):
        """Minimal valid config should be accepted."""
        config = FeatureSetConfig(name="test")
        assert config.name == "test"
        assert config.lag_config is None
        assert config.rolling_config is None

    def test_valid_full_config(self):
        """Full config with all sub-configs should be accepted."""
        config = FeatureSetConfig(
            name="full_test",
            lag_config=LagConfig(),
            rolling_config=RollingConfig(),
            calendar_config=CalendarConfig(),
            exogenous_config=ExogenousConfig(),
            imputation_config=ImputationConfig(),
        )
        assert config.lag_config is not None
        assert config.rolling_config is not None

    def test_get_enabled_features(self):
        """get_enabled_features should return correct list."""
        config = FeatureSetConfig(
            name="test",
            lag_config=LagConfig(),
            calendar_config=CalendarConfig(),
        )
        enabled = config.get_enabled_features()
        assert "lag" in enabled
        assert "calendar" in enabled
        assert "rolling" not in enabled
        assert "exogenous" not in enabled

    def test_config_hash_deterministic(self):
        """config_hash should be deterministic for same config."""
        config1 = FeatureSetConfig(
            name="test",
            lag_config=LagConfig(lags=(1, 7)),
        )
        config2 = FeatureSetConfig(
            name="test",
            lag_config=LagConfig(lags=(1, 7)),
        )
        assert config1.config_hash() == config2.config_hash()

    def test_config_hash_differs_for_different_config(self):
        """config_hash should differ for different configs."""
        config1 = FeatureSetConfig(
            name="test",
            lag_config=LagConfig(lags=(1, 7)),
        )
        config2 = FeatureSetConfig(
            name="test",
            lag_config=LagConfig(lags=(1, 14)),
        )
        assert config1.config_hash() != config2.config_hash()

    def test_config_is_frozen(self):
        """Config should be immutable (frozen)."""
        config = FeatureSetConfig(name="test")
        with pytest.raises(ValidationError):
            config.name = "modified"  # type: ignore[misc]

    def test_rejects_empty_name(self):
        """Empty name should be rejected."""
        with pytest.raises(ValidationError):
            FeatureSetConfig(name="")

    def test_rejects_extra_fields(self):
        """Extra fields should be rejected."""
        with pytest.raises(ValidationError):
            FeatureSetConfig(name="test", unknown_field="value")  # type: ignore[call-arg]


class TestComputeFeaturesRequest:
    """Tests for ComputeFeaturesRequest validation."""

    def test_valid_request(self):
        """Valid request should be accepted."""
        request = ComputeFeaturesRequest(
            store_id=1,
            product_id=1,
            cutoff_date=date(2024, 1, 31),
            lookback_days=365,
            config=FeatureSetConfig(name="test"),
        )
        assert request.store_id == 1
        assert request.cutoff_date == date(2024, 1, 31)

    def test_rejects_zero_store_id(self):
        """Zero store_id should be rejected."""
        with pytest.raises(ValidationError):
            ComputeFeaturesRequest(
                store_id=0,
                product_id=1,
                cutoff_date=date(2024, 1, 31),
                config=FeatureSetConfig(name="test"),
            )

    def test_rejects_lookback_too_large(self):
        """Lookback > 1095 should be rejected."""
        with pytest.raises(ValidationError):
            ComputeFeaturesRequest(
                store_id=1,
                product_id=1,
                cutoff_date=date(2024, 1, 31),
                lookback_days=2000,
                config=FeatureSetConfig(name="test"),
            )

    def test_default_lookback(self):
        """Default lookback should be 365."""
        request = ComputeFeaturesRequest(
            store_id=1,
            product_id=1,
            cutoff_date=date(2024, 1, 31),
            config=FeatureSetConfig(name="test"),
        )
        assert request.lookback_days == 365
