"""Unit tests for seeder schemas."""

from datetime import date

import pytest

from app.features.seeder import schemas


class TestGenerateParams:
    """Tests for GenerateParams schema."""

    def test_default_values(self):
        """Test default parameter values."""
        params = schemas.GenerateParams()

        assert params.scenario == "retail_standard"
        assert params.seed == 42
        assert params.stores == 10
        assert params.products == 50
        assert params.sparsity == 0.0
        assert params.dry_run is False

    def test_custom_values(self):
        """Test custom parameter values."""
        params = schemas.GenerateParams(
            scenario="holiday_rush",
            seed=123,
            stores=20,
            products=100,
            start_date=date(2025, 1, 1),
            end_date=date(2025, 6, 30),
            sparsity=0.3,
            dry_run=True,
        )

        assert params.scenario == "holiday_rush"
        assert params.seed == 123
        assert params.stores == 20
        assert params.products == 100
        assert params.start_date == date(2025, 1, 1)
        assert params.end_date == date(2025, 6, 30)
        assert params.sparsity == 0.3
        assert params.dry_run is True

    def test_stores_validation_min(self):
        """Test stores minimum validation."""
        with pytest.raises(ValueError):
            schemas.GenerateParams(stores=0)

    def test_stores_validation_max(self):
        """Test stores maximum validation."""
        with pytest.raises(ValueError):
            schemas.GenerateParams(stores=101)

    def test_products_validation_min(self):
        """Test products minimum validation."""
        with pytest.raises(ValueError):
            schemas.GenerateParams(products=0)

    def test_products_validation_max(self):
        """Test products maximum validation."""
        with pytest.raises(ValueError):
            schemas.GenerateParams(products=501)

    def test_sparsity_validation_min(self):
        """Test sparsity minimum validation."""
        with pytest.raises(ValueError):
            schemas.GenerateParams(sparsity=-0.1)

    def test_sparsity_validation_max(self):
        """Test sparsity maximum validation."""
        with pytest.raises(ValueError):
            schemas.GenerateParams(sparsity=1.1)

    def test_seed_validation(self):
        """Test seed must be non-negative."""
        with pytest.raises(ValueError):
            schemas.GenerateParams(seed=-1)


class TestAppendParams:
    """Tests for AppendParams schema."""

    def test_required_dates(self):
        """Test that dates are required."""
        params = schemas.AppendParams(
            start_date=date(2025, 1, 1),
            end_date=date(2025, 3, 31),
        )

        assert params.start_date == date(2025, 1, 1)
        assert params.end_date == date(2025, 3, 31)
        assert params.seed == 43  # default

    def test_custom_seed(self):
        """Test custom seed value."""
        params = schemas.AppendParams(
            start_date=date(2025, 1, 1),
            end_date=date(2025, 3, 31),
            seed=999,
        )

        assert params.seed == 999


class TestDeleteParams:
    """Tests for DeleteParams schema."""

    def test_default_scope(self):
        """Test default scope is 'all'."""
        params = schemas.DeleteParams()

        assert params.scope == "all"
        assert params.dry_run is False

    def test_valid_scopes(self):
        """Test valid scope values."""
        # Test each valid scope individually to satisfy type checker
        params_all = schemas.DeleteParams(scope="all")
        assert params_all.scope == "all"

        params_facts = schemas.DeleteParams(scope="facts")
        assert params_facts.scope == "facts"

        params_dimensions = schemas.DeleteParams(scope="dimensions")
        assert params_dimensions.scope == "dimensions"

    def test_dry_run_flag(self):
        """Test dry_run flag."""
        params = schemas.DeleteParams(scope="facts", dry_run=True)

        assert params.scope == "facts"
        assert params.dry_run is True


class TestSeederStatus:
    """Tests for SeederStatus schema."""

    def test_all_fields(self):
        """Test all status fields."""
        status = schemas.SeederStatus(
            stores=10,
            products=50,
            calendar=365,
            sales=182500,
            inventory=182500,
            price_history=1500,
            promotions=500,
            date_range_start=date(2024, 1, 1),
            date_range_end=date(2024, 12, 31),
        )

        assert status.stores == 10
        assert status.products == 50
        assert status.calendar == 365
        assert status.sales == 182500
        assert status.inventory == 182500
        assert status.price_history == 1500
        assert status.promotions == 500
        assert status.date_range_start == date(2024, 1, 1)
        assert status.date_range_end == date(2024, 12, 31)

    def test_optional_dates(self):
        """Test optional date fields can be None."""
        status = schemas.SeederStatus(
            stores=0,
            products=0,
            calendar=0,
            sales=0,
            inventory=0,
            price_history=0,
            promotions=0,
        )

        assert status.date_range_start is None
        assert status.date_range_end is None
        assert status.last_updated is None


class TestScenarioInfo:
    """Tests for ScenarioInfo schema."""

    def test_scenario_fields(self):
        """Test scenario info fields."""
        scenario = schemas.ScenarioInfo(
            name="holiday_rush",
            description="Q4 surge with peaks",
            stores=10,
            products=50,
            start_date=date(2024, 10, 1),
            end_date=date(2024, 12, 31),
        )

        assert scenario.name == "holiday_rush"
        assert scenario.description == "Q4 surge with peaks"
        assert scenario.stores == 10
        assert scenario.products == 50
        assert scenario.start_date == date(2024, 10, 1)
        assert scenario.end_date == date(2024, 12, 31)


class TestGenerateResult:
    """Tests for GenerateResult schema."""

    def test_result_fields(self):
        """Test generate result fields."""
        result = schemas.GenerateResult(
            success=True,
            records_created={
                "stores": 10,
                "products": 50,
                "sales": 182500,
            },
            duration_seconds=45.5,
            message="Successfully generated data",
            seed=42,
        )

        assert result.success is True
        assert result.records_created["stores"] == 10
        assert result.duration_seconds == 45.5
        assert result.seed == 42


class TestDeleteResult:
    """Tests for DeleteResult schema."""

    def test_delete_result_fields(self):
        """Test delete result fields."""
        result = schemas.DeleteResult(
            success=True,
            records_deleted={"sales": 1000, "inventory": 500},
            message="Deleted 1500 records",
            dry_run=False,
        )

        assert result.success is True
        assert result.records_deleted["sales"] == 1000
        assert result.dry_run is False


class TestVerifyResult:
    """Tests for VerifyResult schema."""

    def test_verify_result_fields(self):
        """Test verify result fields."""
        checks = [
            schemas.VerifyCheck(
                name="FK Integrity",
                status="passed",
                message="All FKs valid",
            ),
            schemas.VerifyCheck(
                name="Data Gaps",
                status="warning",
                message="2 gaps found",
                details=["Gap 1", "Gap 2"],
            ),
        ]

        result = schemas.VerifyResult(
            passed=True,
            checks=checks,
            total_checks=2,
            passed_count=1,
            warning_count=1,
            failed_count=0,
        )

        assert result.passed is True
        assert len(result.checks) == 2
        assert result.total_checks == 2
        assert result.passed_count == 1
        assert result.warning_count == 1
        assert result.failed_count == 0
