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
    LifecycleConfig,
    PromotionConfig,
    ReplenishmentConfig,
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


class TestLifecycleConfig:
    """Tests for LifecycleConfig validation (PRP-3.1A)."""

    def test_default_values(self):
        """Default values should be set correctly."""
        config = LifecycleConfig()
        assert config.include_days_since_launch is True
        assert config.include_days_since_discontinue is True
        assert config.lag_days == 1
        assert config.schema_version == "1.0"

    def test_rejects_lag_days_zero(self):
        """lag_days=0 should be rejected (no leakage allowance)."""
        with pytest.raises(ValidationError):
            LifecycleConfig(lag_days=0)

    def test_rejects_lag_days_above_max(self):
        """lag_days above 30 should be rejected."""
        with pytest.raises(ValidationError):
            LifecycleConfig(lag_days=31)

    def test_frozen_after_construction(self):
        """Config should be immutable after construction."""
        config = LifecycleConfig()
        with pytest.raises(ValidationError):
            config.lag_days = 7  # type: ignore[misc]

    def test_rejects_extra_fields(self):
        """Unknown fields should be rejected."""
        with pytest.raises(ValidationError):
            LifecycleConfig(unknown_field="value")  # type: ignore[call-arg]


class TestReplenishmentConfig:
    """Tests for ReplenishmentConfig validation (PRP-3.1A)."""

    def test_default_values(self):
        """Default values should be set correctly."""
        config = ReplenishmentConfig()
        assert config.include_days_since_last is True
        assert config.include_count_window is True
        assert config.lag_days == 1
        assert config.count_window_days == 14
        assert config.schema_version == "1.0"

    def test_rejects_lag_days_out_of_bounds(self):
        """lag_days outside [1, 30] should be rejected."""
        with pytest.raises(ValidationError):
            ReplenishmentConfig(lag_days=0)
        with pytest.raises(ValidationError):
            ReplenishmentConfig(lag_days=31)

    def test_rejects_count_window_below_min(self):
        """count_window_days below 7 should be rejected."""
        with pytest.raises(ValidationError):
            ReplenishmentConfig(count_window_days=6)

    def test_rejects_count_window_above_max(self):
        """count_window_days above 60 should be rejected."""
        with pytest.raises(ValidationError):
            ReplenishmentConfig(count_window_days=61)

    def test_frozen_after_construction(self):
        """Config should be immutable after construction."""
        config = ReplenishmentConfig()
        with pytest.raises(ValidationError):
            config.lag_days = 7  # type: ignore[misc]


class TestPromotionConfig:
    """Tests for PromotionConfig validation (PRP-3.1A)."""

    def test_default_values(self):
        """Default values should be set correctly."""
        config = PromotionConfig()
        assert config.kinds_to_track == ("markdown",)
        assert config.include_active is True
        assert config.include_intensity is True
        assert config.lag_days == 1

    def test_accepts_all_kinds(self):
        """All four allow-listed kinds should be accepted together."""
        config = PromotionConfig(kinds_to_track=("pct_off", "bogo", "bundle", "markdown"))
        assert len(config.kinds_to_track) == 4

    def test_rejects_empty_kinds(self):
        """Empty kinds_to_track should be rejected."""
        with pytest.raises(ValidationError) as exc_info:
            PromotionConfig(kinds_to_track=())
        assert "at least one promotion kind" in str(exc_info.value).lower()

    def test_rejects_duplicate_kinds(self):
        """Duplicate kinds should be rejected."""
        with pytest.raises(ValidationError) as exc_info:
            PromotionConfig(kinds_to_track=("markdown", "markdown"))
        assert "duplicate" in str(exc_info.value).lower()

    def test_rejects_invalid_kind(self):
        """Allow-list violation handled by Pydantic Literal narrowing."""
        with pytest.raises(ValidationError):
            PromotionConfig(kinds_to_track=("invalid_kind",))  # type: ignore[arg-type]

    def test_rejects_lag_days_out_of_bounds(self):
        """lag_days outside [1, 30] should be rejected."""
        with pytest.raises(ValidationError):
            PromotionConfig(lag_days=0)
        with pytest.raises(ValidationError):
            PromotionConfig(lag_days=31)

    def test_frozen_after_construction(self):
        """Config should be immutable after construction."""
        config = PromotionConfig()
        with pytest.raises(ValidationError):
            config.lag_days = 7  # type: ignore[misc]


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

    def test_get_enabled_features_includes_phase2(self):
        """get_enabled_features should emit Phase 2 tokens when set (PRP-3.1A)."""
        config = FeatureSetConfig(
            name="test",
            lifecycle_config=LifecycleConfig(),
            replenishment_config=ReplenishmentConfig(),
            promotion_config=PromotionConfig(),
        )
        enabled = config.get_enabled_features()
        assert "lifecycle" in enabled
        assert "replenishment" in enabled
        assert "promotion" in enabled
        # Order: Phase 2 tokens appear AFTER the legacy tokens.
        assert enabled.index("lifecycle") > -1
        assert enabled.index("replenishment") > enabled.index("lifecycle")
        assert enabled.index("promotion") > enabled.index("replenishment")

    def test_get_enabled_features_omits_phase2_when_none(self):
        """Phase 2 tokens absent when their sub-configs are None."""
        config = FeatureSetConfig(name="test", lag_config=LagConfig())
        enabled = config.get_enabled_features()
        assert "lifecycle" not in enabled
        assert "replenishment" not in enabled
        assert "promotion" not in enabled

    def test_config_hash_unchanged_when_phase2_omitted(self):
        """Additive-contract regression guard (PRD §6, PRP-3.1A §15 Decision E).

        Pins the hash of a minimal FeatureSetConfig (no Phase 2 fields set).
        Adding new optional ``T | None = None`` sub-configs to FeatureSetConfig
        MUST NOT change this hash, because ``config_hash()`` excludes None
        values from its JSON dump. If this fails, either:
          1. The base ``config_hash()`` semantics changed (e.g. lost
             ``exclude_none=True``), OR
          2. A new field with a non-None default was added to FeatureSetConfig,
             OR
          3. An existing field's default was changed.
        """
        # Baseline captured locally after PRP-3.1A landed (exclude_none=True
        # in FeatureConfigBase.config_hash). DO NOT regenerate without
        # confirming the change is intentional and additive.
        expected_hash = "6c12b1a783eccdd4"
        actual_hash = FeatureSetConfig(name="x").config_hash()
        assert actual_hash == expected_hash, (
            f"config_hash for minimal FeatureSetConfig changed "
            f"(expected {expected_hash}, got {actual_hash}) — "
            f"the additive-contract invariant is broken."
        )


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
