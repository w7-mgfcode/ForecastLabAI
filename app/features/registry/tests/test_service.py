"""Unit tests for registry service."""

from datetime import date

import pytest

from app.features.registry.schemas import (
    VALID_TRANSITIONS,
    RunCreate,
    RunStatus,
)
from app.features.registry.service import (
    DuplicateRunError,
    InvalidTransitionError,
    RegistryService,
)


class TestRegistryServiceStatusTransition:
    """Tests for status transition validation."""

    def test_is_valid_transition_pending_to_running(self) -> None:
        """PENDING -> RUNNING should be valid."""
        service = RegistryService()
        assert service._is_valid_transition(RunStatus.PENDING, RunStatus.RUNNING) is True

    def test_is_valid_transition_pending_to_archived(self) -> None:
        """PENDING -> ARCHIVED should be valid."""
        service = RegistryService()
        assert service._is_valid_transition(RunStatus.PENDING, RunStatus.ARCHIVED) is True

    def test_is_valid_transition_running_to_success(self) -> None:
        """RUNNING -> SUCCESS should be valid."""
        service = RegistryService()
        assert service._is_valid_transition(RunStatus.RUNNING, RunStatus.SUCCESS) is True

    def test_is_valid_transition_running_to_failed(self) -> None:
        """RUNNING -> FAILED should be valid."""
        service = RegistryService()
        assert service._is_valid_transition(RunStatus.RUNNING, RunStatus.FAILED) is True

    def test_is_valid_transition_success_to_archived(self) -> None:
        """SUCCESS -> ARCHIVED should be valid."""
        service = RegistryService()
        assert service._is_valid_transition(RunStatus.SUCCESS, RunStatus.ARCHIVED) is True

    def test_is_valid_transition_failed_to_archived(self) -> None:
        """FAILED -> ARCHIVED should be valid."""
        service = RegistryService()
        assert service._is_valid_transition(RunStatus.FAILED, RunStatus.ARCHIVED) is True

    def test_is_invalid_transition_pending_to_success(self) -> None:
        """PENDING -> SUCCESS should be invalid (must go through RUNNING)."""
        service = RegistryService()
        assert service._is_valid_transition(RunStatus.PENDING, RunStatus.SUCCESS) is False

    def test_is_invalid_transition_pending_to_failed(self) -> None:
        """PENDING -> FAILED should be invalid (must go through RUNNING)."""
        service = RegistryService()
        assert service._is_valid_transition(RunStatus.PENDING, RunStatus.FAILED) is False

    def test_is_invalid_transition_success_to_running(self) -> None:
        """SUCCESS -> RUNNING should be invalid (can't go backwards)."""
        service = RegistryService()
        assert service._is_valid_transition(RunStatus.SUCCESS, RunStatus.RUNNING) is False

    def test_is_invalid_transition_archived_to_any(self) -> None:
        """ARCHIVED -> any state should be invalid (terminal state)."""
        service = RegistryService()
        for target in RunStatus:
            if target != RunStatus.ARCHIVED:
                assert service._is_valid_transition(RunStatus.ARCHIVED, target) is False


class TestRegistryServiceRuntimeInfo:
    """Tests for runtime info capture."""

    def test_capture_runtime_info_has_python_version(self) -> None:
        """Should capture Python version."""
        service = RegistryService()
        info = service._capture_runtime_info()
        assert "python_version" in info
        assert info["python_version"].startswith("3.")

    def test_capture_runtime_info_has_package_versions(self) -> None:
        """Should capture installed package versions."""
        service = RegistryService()
        info = service._capture_runtime_info()

        # These should be installed in the test environment
        assert "numpy_version" in info
        assert "pandas_version" in info


class TestRegistryServiceConfigHashDuplicate:
    """Tests for config hash and duplicate detection."""

    def test_compute_config_hash_deterministic(self) -> None:
        """Config hash should be deterministic for same config."""
        run_data = RunCreate(
            model_type="naive",
            model_config_data={"a": 1, "b": 2},
            data_window_start=date(2024, 1, 1),
            data_window_end=date(2024, 1, 31),
            store_id=1,
            product_id=1,
        )
        hash1 = run_data.compute_config_hash()
        hash2 = run_data.compute_config_hash()
        assert hash1 == hash2

    def test_compute_config_hash_order_independent(self) -> None:
        """Config hash should be same regardless of key order."""
        run1 = RunCreate(
            model_type="naive",
            model_config_data={"a": 1, "b": 2, "c": 3},
            data_window_start=date(2024, 1, 1),
            data_window_end=date(2024, 1, 31),
            store_id=1,
            product_id=1,
        )
        run2 = RunCreate(
            model_type="naive",
            model_config_data={"c": 3, "a": 1, "b": 2},
            data_window_start=date(2024, 1, 1),
            data_window_end=date(2024, 1, 31),
            store_id=1,
            product_id=1,
        )
        assert run1.compute_config_hash() == run2.compute_config_hash()


class TestRegistryServiceConfigDiff:
    """Tests for configuration diffing."""

    def test_compute_config_diff_identical(self) -> None:
        """Identical configs should have empty diff."""
        service = RegistryService()
        config_a = {"strategy": "last_value", "horizon": 14}
        config_b = {"strategy": "last_value", "horizon": 14}
        diff = service._compute_config_diff(config_a, config_b)
        assert diff == {}

    def test_compute_config_diff_different_values(self) -> None:
        """Different values should be captured in diff."""
        service = RegistryService()
        config_a = {"strategy": "last_value", "horizon": 14}
        config_b = {"strategy": "mean", "horizon": 7}
        diff = service._compute_config_diff(config_a, config_b)
        assert diff == {
            "strategy": {"a": "last_value", "b": "mean"},
            "horizon": {"a": 14, "b": 7},
        }

    def test_compute_config_diff_missing_keys(self) -> None:
        """Missing keys should show None."""
        service = RegistryService()
        config_a = {"strategy": "last_value", "extra_param": 100}
        config_b = {"strategy": "last_value"}
        diff = service._compute_config_diff(config_a, config_b)
        assert diff == {"extra_param": {"a": 100, "b": None}}


class TestRegistryServiceMetricsDiff:
    """Tests for metrics diffing."""

    def test_compute_metrics_diff_both_none(self) -> None:
        """Both None should return empty diff."""
        service = RegistryService()
        diff = service._compute_metrics_diff(None, None)
        assert diff == {}

    def test_compute_metrics_diff_one_none(self) -> None:
        """One None should show values from the other."""
        service = RegistryService()
        metrics_a = {"mae": 1.5, "smape": 10.0}
        diff = service._compute_metrics_diff(metrics_a, None)
        assert diff == {
            "mae": {"a": 1.5, "b": None, "diff": None},
            "smape": {"a": 10.0, "b": None, "diff": None},
        }

    def test_compute_metrics_diff_numeric_diff(self) -> None:
        """Should compute numeric difference (b - a)."""
        service = RegistryService()
        metrics_a = {"mae": 1.5, "smape": 10.0}
        metrics_b = {"mae": 2.0, "smape": 8.0}
        diff = service._compute_metrics_diff(metrics_a, metrics_b)
        assert diff["mae"]["a"] == 1.5
        assert diff["mae"]["b"] == 2.0
        assert diff["mae"]["diff"] == pytest.approx(0.5)  # b - a = 2.0 - 1.5 = 0.5
        assert diff["smape"]["diff"] == pytest.approx(-2.0)  # b - a = 8.0 - 10.0 = -2.0

    def test_compute_metrics_diff_non_numeric(self) -> None:
        """Non-numeric values should have None diff."""
        service = RegistryService()
        metrics_a = {"model_name": "naive", "mae": 1.5}
        metrics_b = {"model_name": "seasonal", "mae": 2.0}
        diff = service._compute_metrics_diff(metrics_a, metrics_b)
        assert diff["model_name"]["diff"] is None
        assert diff["mae"]["diff"] == pytest.approx(0.5)  # b - a = 2.0 - 1.5 = 0.5


class TestInvalidTransitionError:
    """Tests for InvalidTransitionError."""

    def test_error_message(self) -> None:
        """Should format error message correctly."""
        error = InvalidTransitionError(RunStatus.PENDING, RunStatus.SUCCESS)
        assert "pending" in str(error).lower()
        assert "success" in str(error).lower()


class TestDuplicateRunError:
    """Tests for DuplicateRunError."""

    def test_error_message(self) -> None:
        """Should format error message correctly."""
        error = DuplicateRunError("existing-run-id", "abc123")
        assert "existing-run-id" in str(error)
        assert "abc123" in str(error)


class TestAllTransitionsExhaustive:
    """Exhaustive tests for all state transitions."""

    @pytest.mark.parametrize(
        "current_status,target_status",
        [
            (RunStatus.PENDING, RunStatus.RUNNING),
            (RunStatus.PENDING, RunStatus.ARCHIVED),
            (RunStatus.RUNNING, RunStatus.SUCCESS),
            (RunStatus.RUNNING, RunStatus.FAILED),
            (RunStatus.RUNNING, RunStatus.ARCHIVED),
            (RunStatus.SUCCESS, RunStatus.ARCHIVED),
            (RunStatus.FAILED, RunStatus.ARCHIVED),
        ],
    )
    def test_valid_transitions(self, current_status: RunStatus, target_status: RunStatus) -> None:
        """All valid transitions should be allowed."""
        service = RegistryService()
        assert service._is_valid_transition(current_status, target_status) is True

    @pytest.mark.parametrize(
        "current_status,target_status",
        [
            (RunStatus.PENDING, RunStatus.SUCCESS),
            (RunStatus.PENDING, RunStatus.FAILED),
            (RunStatus.RUNNING, RunStatus.PENDING),
            (RunStatus.SUCCESS, RunStatus.PENDING),
            (RunStatus.SUCCESS, RunStatus.RUNNING),
            (RunStatus.SUCCESS, RunStatus.FAILED),
            (RunStatus.FAILED, RunStatus.PENDING),
            (RunStatus.FAILED, RunStatus.RUNNING),
            (RunStatus.FAILED, RunStatus.SUCCESS),
            (RunStatus.ARCHIVED, RunStatus.PENDING),
            (RunStatus.ARCHIVED, RunStatus.RUNNING),
            (RunStatus.ARCHIVED, RunStatus.SUCCESS),
            (RunStatus.ARCHIVED, RunStatus.FAILED),
        ],
    )
    def test_invalid_transitions(self, current_status: RunStatus, target_status: RunStatus) -> None:
        """All invalid transitions should be rejected."""
        service = RegistryService()
        assert service._is_valid_transition(current_status, target_status) is False

    def test_all_statuses_have_transition_rules(self) -> None:
        """All statuses should be defined in VALID_TRANSITIONS."""
        for status in RunStatus:
            assert status in VALID_TRANSITIONS
