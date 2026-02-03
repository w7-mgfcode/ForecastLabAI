"""Unit tests for seeder service layer."""

from datetime import date
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.features.seeder import schemas, service


class TestListScenarios:
    """Tests for list_scenarios function."""

    def test_returns_all_scenarios(self):
        """Test that all scenario presets are returned."""
        scenarios = service.list_scenarios()

        assert len(scenarios) == 6

        names = [s.name for s in scenarios]
        assert "retail_standard" in names
        assert "holiday_rush" in names
        assert "high_variance" in names
        assert "stockout_heavy" in names
        assert "new_launches" in names
        assert "sparse" in names

    def test_scenario_info_structure(self):
        """Test that scenarios have required fields."""
        scenarios = service.list_scenarios()

        for scenario in scenarios:
            assert isinstance(scenario.name, str)
            assert isinstance(scenario.description, str)
            assert isinstance(scenario.stores, int)
            assert isinstance(scenario.products, int)
            assert isinstance(scenario.start_date, date)
            assert isinstance(scenario.end_date, date)

    def test_new_launches_has_more_products(self):
        """Test that new_launches scenario has 100 products."""
        scenarios = service.list_scenarios()

        new_launches = next(s for s in scenarios if s.name == "new_launches")
        assert new_launches.products == 100

    def test_holiday_rush_date_range(self):
        """Test that holiday_rush has Q4 date range."""
        scenarios = service.list_scenarios()

        holiday = next(s for s in scenarios if s.name == "holiday_rush")
        assert holiday.start_date == date(2024, 10, 1)
        assert holiday.end_date == date(2024, 12, 31)


class TestGetScenarioPreset:
    """Tests for _get_scenario_preset helper."""

    def test_valid_scenarios(self):
        """Test valid scenario names return presets."""
        valid_names = [
            "retail_standard",
            "holiday_rush",
            "high_variance",
            "stockout_heavy",
            "new_launches",
            "sparse",
        ]

        for name in valid_names:
            preset = service._get_scenario_preset(name)
            assert preset is not None
            assert preset.value == name

    def test_invalid_scenario(self):
        """Test invalid scenario name returns None."""
        preset = service._get_scenario_preset("invalid_scenario")
        assert preset is None

    def test_empty_string(self):
        """Test empty string returns None."""
        preset = service._get_scenario_preset("")
        assert preset is None


class TestBuildConfigFromParams:
    """Tests for _build_config_from_params helper."""

    def test_default_params(self):
        """Test config built from default params."""
        params = schemas.GenerateParams()
        config = service._build_config_from_params(params)

        assert config.seed == 42
        assert config.dimensions.stores == 10
        assert config.dimensions.products == 50

    def test_custom_scenario(self):
        """Test config built from custom scenario."""
        params = schemas.GenerateParams(
            scenario="holiday_rush",
            seed=123,
            stores=20,
            products=100,
        )
        config = service._build_config_from_params(params)

        assert config.seed == 123
        assert config.dimensions.stores == 20
        assert config.dimensions.products == 100
        # Holiday rush has exponential trend
        assert config.time_series.trend == "exponential"

    def test_unknown_scenario_uses_defaults(self):
        """Test unknown scenario uses default config."""
        params = schemas.GenerateParams(
            scenario="unknown_scenario",
            seed=999,
        )
        config = service._build_config_from_params(params)

        assert config.seed == 999
        # Default config has no trend
        assert config.time_series.trend == "none"

    def test_sparsity_config(self):
        """Test sparsity config is applied."""
        params = schemas.GenerateParams(sparsity=0.5)
        config = service._build_config_from_params(params)

        assert config.sparsity.missing_combinations_pct == 0.5

    def test_date_range_override(self):
        """Test date range is overridden."""
        params = schemas.GenerateParams(
            start_date=date(2025, 1, 1),
            end_date=date(2025, 6, 30),
        )
        config = service._build_config_from_params(params)

        assert config.start_date == date(2025, 1, 1)
        assert config.end_date == date(2025, 6, 30)


class TestGetStatus:
    """Tests for get_status function."""

    @pytest.mark.asyncio
    async def test_returns_status(self):
        """Test status is returned with counts."""
        mock_db = AsyncMock()

        # Mock the count queries - return different values for each table
        mock_results = [10, 50, 365, 182500, 182500, 1500, 500]
        mock_db.execute.side_effect = [
            # Counts for each table
            *[MagicMock(scalar=MagicMock(return_value=count)) for count in mock_results],
            # Date range query
            MagicMock(fetchone=MagicMock(return_value=(date(2024, 1, 1), date(2024, 12, 31)))),
            # Updated_at query
            MagicMock(scalar=MagicMock(return_value=None)),
        ]

        status = await service.get_status(mock_db)

        assert status.stores == 10
        assert status.products == 50
        assert status.calendar == 365
        assert status.sales == 182500

    @pytest.mark.asyncio
    async def test_empty_database(self):
        """Test status for empty database."""
        mock_db = AsyncMock()

        # Mock empty counts
        mock_db.execute.side_effect = [
            *[MagicMock(scalar=MagicMock(return_value=0)) for _ in range(7)],
        ]

        status = await service.get_status(mock_db)

        assert status.stores == 0
        assert status.products == 0
        assert status.sales == 0
        assert status.date_range_start is None
        assert status.date_range_end is None


class TestGenerateData:
    """Tests for generate_data function."""

    @pytest.mark.asyncio
    async def test_dry_run_returns_preview(self):
        """Test dry_run returns preview without executing."""
        mock_db = AsyncMock()
        params = schemas.GenerateParams(
            scenario="retail_standard",
            dry_run=True,
        )

        with patch.object(service, "get_settings") as mock_settings:
            mock_settings.return_value.seeder_allow_production = True
            mock_settings.return_value.app_env = "development"

            result = await service.generate_data(mock_db, params)

        assert result.success is True
        assert result.duration_seconds == 0.0
        assert "Dry run" in result.message
        # Verify no database operations occurred
        mock_db.execute.assert_not_called()

    @pytest.mark.asyncio
    async def test_production_guard_blocks(self):
        """Test production guard blocks operations."""
        mock_db = AsyncMock()
        params = schemas.GenerateParams()

        with patch.object(service, "get_settings") as mock_settings:
            mock_settings.return_value.seeder_allow_production = False
            mock_settings.return_value.app_env = "production"

            with pytest.raises(ValueError, match="production"):
                await service.generate_data(mock_db, params)


class TestDeleteData:
    """Tests for delete_data function."""

    @pytest.mark.asyncio
    async def test_dry_run_returns_preview(self):
        """Test dry_run returns preview without deleting."""
        mock_db = AsyncMock()
        params = schemas.DeleteParams(scope="all", dry_run=True)

        with patch.object(service, "get_settings") as mock_settings:
            mock_settings.return_value.seeder_allow_production = True
            mock_settings.return_value.app_env = "development"
            mock_settings.return_value.seeder_batch_size = 1000

            # Mock DataSeeder.delete_data to return counts
            with patch("app.features.seeder.service.DataSeeder") as MockSeeder:
                mock_seeder = MockSeeder.return_value
                mock_seeder.delete_data = AsyncMock(return_value={"sales_daily": 1000, "store": 10})

                result = await service.delete_data(mock_db, params)

        assert result.success is True
        assert result.dry_run is True
        assert "Dry run" in result.message

    @pytest.mark.asyncio
    async def test_production_guard_blocks(self):
        """Test production guard blocks delete operations."""
        mock_db = AsyncMock()
        params = schemas.DeleteParams(scope="all")

        with patch.object(service, "get_settings") as mock_settings:
            mock_settings.return_value.seeder_allow_production = False
            mock_settings.return_value.app_env = "production"

            with pytest.raises(ValueError, match="production"):
                await service.delete_data(mock_db, params)


class TestVerifyData:
    """Tests for verify_data function."""

    @pytest.mark.asyncio
    async def test_returns_checks(self):
        """Test verify returns check results."""
        mock_db = AsyncMock()

        with patch.object(service, "get_settings") as mock_settings:
            mock_settings.return_value.seeder_batch_size = 1000

            # Mock DataSeeder.verify_data_integrity
            with patch("app.features.seeder.service.DataSeeder") as MockSeeder:
                mock_seeder = MockSeeder.return_value
                mock_seeder.verify_data_integrity = AsyncMock(return_value=[])

                # Mock get_status
                with patch.object(service, "get_status") as mock_status:
                    mock_status.return_value = schemas.SeederStatus(
                        stores=10,
                        products=50,
                        calendar=365,
                        sales=182500,
                        inventory=182500,
                        price_history=1500,
                        promotions=500,
                    )

                    result = await service.verify_data(mock_db)

        assert result.total_checks == 5
        assert result.passed is True

    @pytest.mark.asyncio
    async def test_detects_failures(self):
        """Test verify detects integrity failures."""
        mock_db = AsyncMock()

        with patch.object(service, "get_settings") as mock_settings:
            mock_settings.return_value.seeder_batch_size = 1000

            # Mock DataSeeder.verify_data_integrity with errors
            with patch("app.features.seeder.service.DataSeeder") as MockSeeder:
                mock_seeder = MockSeeder.return_value
                mock_seeder.verify_data_integrity = AsyncMock(
                    return_value=["Found 5 sales with invalid foreign keys"]
                )

                # Mock get_status
                with patch.object(service, "get_status") as mock_status:
                    mock_status.return_value = schemas.SeederStatus(
                        stores=10,
                        products=50,
                        calendar=365,
                        sales=182500,
                        inventory=182500,
                        price_history=1500,
                        promotions=500,
                    )

                    result = await service.verify_data(mock_db)

        assert result.passed is False
        assert result.failed_count > 0
