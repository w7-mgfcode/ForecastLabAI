"""Unit tests for registry schemas."""

from datetime import date

import pytest
from pydantic import ValidationError

from app.features.registry.schemas import (
    VALID_TRANSITIONS,
    AgentContext,
    AliasCreate,
    RunCreate,
    RunStatus,
    RuntimeInfo,
    RunUpdate,
)


class TestRunStatus:
    """Tests for RunStatus enum."""

    def test_all_statuses_defined(self) -> None:
        """All expected statuses should be defined."""
        assert RunStatus.PENDING.value == "pending"
        assert RunStatus.RUNNING.value == "running"
        assert RunStatus.SUCCESS.value == "success"
        assert RunStatus.FAILED.value == "failed"
        assert RunStatus.ARCHIVED.value == "archived"

    def test_status_count(self) -> None:
        """Should have exactly 5 statuses."""
        assert len(RunStatus) == 5


class TestValidTransitions:
    """Tests for state transition validation."""

    def test_pending_transitions(self) -> None:
        """PENDING can transition to RUNNING or ARCHIVED."""
        assert VALID_TRANSITIONS[RunStatus.PENDING] == {
            RunStatus.RUNNING,
            RunStatus.ARCHIVED,
        }

    def test_running_transitions(self) -> None:
        """RUNNING can transition to SUCCESS, FAILED, or ARCHIVED."""
        assert VALID_TRANSITIONS[RunStatus.RUNNING] == {
            RunStatus.SUCCESS,
            RunStatus.FAILED,
            RunStatus.ARCHIVED,
        }

    def test_success_transitions(self) -> None:
        """SUCCESS can only transition to ARCHIVED."""
        assert VALID_TRANSITIONS[RunStatus.SUCCESS] == {RunStatus.ARCHIVED}

    def test_failed_transitions(self) -> None:
        """FAILED can only transition to ARCHIVED."""
        assert VALID_TRANSITIONS[RunStatus.FAILED] == {RunStatus.ARCHIVED}

    def test_archived_is_terminal(self) -> None:
        """ARCHIVED is a terminal state with no transitions."""
        assert VALID_TRANSITIONS[RunStatus.ARCHIVED] == set()


class TestRuntimeInfo:
    """Tests for RuntimeInfo schema."""

    def test_create_with_all_fields(self) -> None:
        """Should create with all version fields."""
        info = RuntimeInfo(
            python_version="3.12.0",
            sklearn_version="1.4.0",
            numpy_version="1.26.0",
            pandas_version="2.1.0",
            joblib_version="1.3.0",
        )
        assert info.python_version == "3.12.0"
        assert info.sklearn_version == "1.4.0"

    def test_create_minimal(self) -> None:
        """Should create with only required fields."""
        info = RuntimeInfo(python_version="3.12.0")
        assert info.python_version == "3.12.0"
        assert info.sklearn_version is None
        assert info.numpy_version is None

    def test_is_frozen(self) -> None:
        """RuntimeInfo should be immutable."""
        info = RuntimeInfo(python_version="3.12.0")
        with pytest.raises(ValidationError):
            info.python_version = "3.11.0"  # type: ignore[misc]


class TestAgentContext:
    """Tests for AgentContext schema."""

    def test_create_with_all_fields(self) -> None:
        """Should create with all fields."""
        ctx = AgentContext(agent_id="agent-123", session_id="session-456")
        assert ctx.agent_id == "agent-123"
        assert ctx.session_id == "session-456"

    def test_create_empty(self) -> None:
        """Should create with no fields (all optional)."""
        ctx = AgentContext()
        assert ctx.agent_id is None
        assert ctx.session_id is None

    def test_is_frozen(self) -> None:
        """AgentContext should be immutable."""
        ctx = AgentContext(agent_id="agent-123")
        with pytest.raises(ValidationError):
            ctx.agent_id = "agent-456"  # type: ignore[misc]


class TestRunCreate:
    """Tests for RunCreate schema."""

    def test_create_minimal(self) -> None:
        """Should create with only required fields."""
        run = RunCreate(
            model_type="naive",
            model_config={"strategy": "last_value"},
            data_window_start=date(2024, 1, 1),
            data_window_end=date(2024, 3, 31),
            store_id=1,
            product_id=1,
        )
        assert run.model_type == "naive"
        assert run.model_config_data == {"strategy": "last_value"}
        assert run.feature_config is None
        assert run.agent_context is None
        assert run.git_sha is None

    def test_create_with_all_fields(self) -> None:
        """Should create with all fields."""
        run = RunCreate(
            model_type="seasonal_naive",
            model_config={"season_length": 7},
            feature_config={"lags": [1, 7, 14]},
            data_window_start=date(2024, 1, 1),
            data_window_end=date(2024, 6, 30),
            store_id=5,
            product_id=10,
            agent_context=AgentContext(agent_id="test"),
            git_sha="abc123def456789",
        )
        assert run.model_type == "seasonal_naive"
        assert run.feature_config == {"lags": [1, 7, 14]}
        assert run.store_id == 5
        assert run.product_id == 10

    def test_validate_model_type_min_length(self) -> None:
        """model_type should have minimum length of 1."""
        with pytest.raises(ValidationError) as exc_info:
            RunCreate(
                model_type="",
                model_config={},
                data_window_start=date(2024, 1, 1),
                data_window_end=date(2024, 1, 31),
                store_id=1,
                product_id=1,
            )
        assert "model_type" in str(exc_info.value)

    def test_validate_model_type_max_length(self) -> None:
        """model_type should have maximum length of 50."""
        with pytest.raises(ValidationError) as exc_info:
            RunCreate(
                model_type="a" * 51,
                model_config={},
                data_window_start=date(2024, 1, 1),
                data_window_end=date(2024, 1, 31),
                store_id=1,
                product_id=1,
            )
        assert "model_type" in str(exc_info.value)

    def test_validate_store_id_positive(self) -> None:
        """store_id must be >= 1."""
        with pytest.raises(ValidationError) as exc_info:
            RunCreate(
                model_type="naive",
                model_config={},
                data_window_start=date(2024, 1, 1),
                data_window_end=date(2024, 1, 31),
                store_id=0,
                product_id=1,
            )
        assert "store_id" in str(exc_info.value)

    def test_validate_product_id_positive(self) -> None:
        """product_id must be >= 1."""
        with pytest.raises(ValidationError) as exc_info:
            RunCreate(
                model_type="naive",
                model_config={},
                data_window_start=date(2024, 1, 1),
                data_window_end=date(2024, 1, 31),
                store_id=1,
                product_id=0,
            )
        assert "product_id" in str(exc_info.value)

    def test_validate_data_window_end_after_start(self) -> None:
        """data_window_end must be >= data_window_start."""
        with pytest.raises(ValidationError) as exc_info:
            RunCreate(
                model_type="naive",
                model_config={},
                data_window_start=date(2024, 3, 1),
                data_window_end=date(2024, 1, 1),
                store_id=1,
                product_id=1,
            )
        assert "data_window_end" in str(exc_info.value)

    def test_data_window_same_day_valid(self) -> None:
        """data_window_end == data_window_start should be valid."""
        run = RunCreate(
            model_type="naive",
            model_config={},
            data_window_start=date(2024, 1, 1),
            data_window_end=date(2024, 1, 1),
            store_id=1,
            product_id=1,
        )
        assert run.data_window_start == run.data_window_end

    def test_compute_config_hash(self) -> None:
        """config_hash should be deterministic for same config."""
        run1 = RunCreate(
            model_type="naive",
            model_config={"a": 1, "b": 2},
            data_window_start=date(2024, 1, 1),
            data_window_end=date(2024, 1, 31),
            store_id=1,
            product_id=1,
        )
        run2 = RunCreate(
            model_type="naive",
            model_config={"b": 2, "a": 1},  # Same config, different order
            data_window_start=date(2024, 1, 1),
            data_window_end=date(2024, 1, 31),
            store_id=1,
            product_id=1,
        )
        assert run1.compute_config_hash() == run2.compute_config_hash()

    def test_compute_config_hash_different(self) -> None:
        """config_hash should differ for different configs."""
        run1 = RunCreate(
            model_type="naive",
            model_config={"a": 1},
            data_window_start=date(2024, 1, 1),
            data_window_end=date(2024, 1, 31),
            store_id=1,
            product_id=1,
        )
        run2 = RunCreate(
            model_type="naive",
            model_config={"a": 2},
            data_window_start=date(2024, 1, 1),
            data_window_end=date(2024, 1, 31),
            store_id=1,
            product_id=1,
        )
        assert run1.compute_config_hash() != run2.compute_config_hash()

    def test_config_hash_length(self) -> None:
        """config_hash should be 16 characters."""
        run = RunCreate(
            model_type="naive",
            model_config={"test": True},
            data_window_start=date(2024, 1, 1),
            data_window_end=date(2024, 1, 31),
            store_id=1,
            product_id=1,
        )
        assert len(run.compute_config_hash()) == 16


class TestRunUpdate:
    """Tests for RunUpdate schema."""

    def test_create_empty(self) -> None:
        """Should allow empty update (all fields optional)."""
        update = RunUpdate()
        assert update.status is None
        assert update.metrics is None
        assert update.artifact_uri is None

    def test_update_status(self) -> None:
        """Should update status."""
        update = RunUpdate(status=RunStatus.RUNNING)
        assert update.status == RunStatus.RUNNING

    def test_update_metrics(self) -> None:
        """Should update metrics."""
        update = RunUpdate(metrics={"mae": 1.5, "smape": 10.2})
        assert update.metrics == {"mae": 1.5, "smape": 10.2}

    def test_update_artifact_info(self) -> None:
        """Should update artifact information."""
        update = RunUpdate(
            artifact_uri="models/run123.pkl",
            artifact_hash="abc123def456",
            artifact_size_bytes=1024,
        )
        assert update.artifact_uri == "models/run123.pkl"
        assert update.artifact_hash == "abc123def456"
        assert update.artifact_size_bytes == 1024

    def test_validate_artifact_size_bytes_non_negative(self) -> None:
        """artifact_size_bytes must be >= 0."""
        with pytest.raises(ValidationError) as exc_info:
            RunUpdate(artifact_size_bytes=-1)
        assert "artifact_size_bytes" in str(exc_info.value)

    def test_validate_error_message_max_length(self) -> None:
        """error_message should have maximum length of 2000."""
        with pytest.raises(ValidationError) as exc_info:
            RunUpdate(error_message="x" * 2001)
        assert "error_message" in str(exc_info.value)


class TestAliasCreate:
    """Tests for AliasCreate schema."""

    def test_create_minimal(self) -> None:
        """Should create with required fields only."""
        alias = AliasCreate(alias_name="production", run_id="abc123")
        assert alias.alias_name == "production"
        assert alias.run_id == "abc123"
        assert alias.description is None

    def test_create_with_description(self) -> None:
        """Should create with description."""
        alias = AliasCreate(
            alias_name="staging-v2",
            run_id="def456",
            description="Staging environment model",
        )
        assert alias.description == "Staging environment model"

    def test_validate_alias_name_pattern_lowercase(self) -> None:
        """alias_name must match pattern (lowercase letters, numbers, hyphens, underscores)."""
        # Valid names
        AliasCreate(alias_name="production", run_id="x")
        AliasCreate(alias_name="staging-v2", run_id="x")
        AliasCreate(alias_name="prod_us_east", run_id="x")
        AliasCreate(alias_name="1-test", run_id="x")

    def test_validate_alias_name_pattern_invalid_uppercase(self) -> None:
        """alias_name should reject uppercase letters."""
        with pytest.raises(ValidationError) as exc_info:
            AliasCreate(alias_name="Production", run_id="x")
        assert "alias_name" in str(exc_info.value)

    def test_validate_alias_name_pattern_invalid_special(self) -> None:
        """alias_name should reject special characters."""
        with pytest.raises(ValidationError) as exc_info:
            AliasCreate(alias_name="prod@v1", run_id="x")
        assert "alias_name" in str(exc_info.value)

    def test_validate_alias_name_pattern_invalid_start(self) -> None:
        """alias_name must start with letter or number."""
        with pytest.raises(ValidationError) as exc_info:
            AliasCreate(alias_name="-production", run_id="x")
        assert "alias_name" in str(exc_info.value)

    def test_validate_alias_name_max_length(self) -> None:
        """alias_name should have maximum length of 100."""
        with pytest.raises(ValidationError) as exc_info:
            AliasCreate(alias_name="a" * 101, run_id="x")
        assert "alias_name" in str(exc_info.value)

    def test_validate_description_max_length(self) -> None:
        """description should have maximum length of 500."""
        with pytest.raises(ValidationError) as exc_info:
            AliasCreate(alias_name="test", run_id="x", description="x" * 501)
        assert "description" in str(exc_info.value)
