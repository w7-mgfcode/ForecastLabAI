"""Unit tests for registry schemas."""

from datetime import UTC, date, datetime
from typing import ClassVar

import pytest
from pydantic import ValidationError

from app.features.forecasting.schemas import ModelFamily
from app.features.registry.schemas import (
    VALID_TRANSITIONS,
    AgentContext,
    AliasCreate,
    RunCreate,
    RunResponse,
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
            model_config_data={"strategy": "last_value"},
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
            model_config_data={"season_length": 7},
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
                model_config_data={},
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
                model_config_data={},
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
                model_config_data={},
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
                model_config_data={},
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
                model_config_data={},
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
            model_config_data={},
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
            model_config_data={"a": 1, "b": 2},
            data_window_start=date(2024, 1, 1),
            data_window_end=date(2024, 1, 31),
            store_id=1,
            product_id=1,
        )
        run2 = RunCreate(
            model_type="naive",
            model_config_data={"b": 2, "a": 1},  # Same config, different order
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
            model_config_data={"a": 1},
            data_window_start=date(2024, 1, 1),
            data_window_end=date(2024, 1, 31),
            store_id=1,
            product_id=1,
        )
        run2 = RunCreate(
            model_type="naive",
            model_config_data={"a": 2},
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
            model_config_data={"test": True},
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


class TestRunResponseModelFamily:
    """Tests for the computed ``model_family`` field on ``RunResponse``.

    MLZOO-D / PRP-31: ``model_family`` is derived from ``model_type`` at
    serialization time via a Pydantic ``@computed_field``. No DB column, no
    migration, no backfill. Unknown types degrade to ``BASELINE`` and log a
    warning (forward-compat).
    """

    _BASE_FIELDS: ClassVar[dict[str, object]] = {
        "run_id": "abc123",
        "status": RunStatus.SUCCESS,
        "model_config_data": {"model_type": "naive"},
        "config_hash": "deadbeefdeadbeef",
        "data_window_start": date(2024, 1, 1),
        "data_window_end": date(2024, 1, 31),
        "store_id": 1,
        "product_id": 1,
        "created_at": datetime(2024, 1, 1, 0, 0, 0, tzinfo=UTC),
        "updated_at": datetime(2024, 1, 2, 0, 0, 0, tzinfo=UTC),
    }

    def _make_response(self, model_type: str) -> RunResponse:
        fields = {**self._BASE_FIELDS, "model_type": model_type}
        return RunResponse.model_validate(fields)

    @pytest.mark.parametrize(
        ("model_type", "expected"),
        [
            ("naive", ModelFamily.BASELINE),
            ("seasonal_naive", ModelFamily.BASELINE),
            ("moving_average", ModelFamily.BASELINE),
            ("regression", ModelFamily.TREE),
            ("lightgbm", ModelFamily.TREE),
            ("xgboost", ModelFamily.TREE),
            ("prophet_like", ModelFamily.ADDITIVE),
        ],
    )
    def test_model_family_computed_for_every_known_type(
        self, model_type: str, expected: ModelFamily
    ) -> None:
        """All seven canonical model_types map to the expected ModelFamily."""
        response = self._make_response(model_type)
        assert response.model_family == expected

    def test_model_family_unknown_type_falls_back_to_baseline(self) -> None:
        """An unknown model_type degrades to BASELINE (logs a warning).

        Forward-compat: a model_type added to ``forecasting/models.py`` before
        the family map is updated should not crash the registry — it just
        shows up in the dashboard as a baseline until the map catches up.
        """
        response = self._make_response("future_arima_v9")
        assert response.model_family == ModelFamily.BASELINE

    def test_model_family_serializes_alongside_model_config_alias(self) -> None:
        """Both ``model_config`` (aliased) and ``model_family`` are top-level
        keys on the serialized dict — no collision with the alias."""
        response = self._make_response("lightgbm")
        dumped = response.model_dump(by_alias=True)
        assert dumped["model_config"] == {"model_type": "naive"}
        assert dumped["model_family"] == ModelFamily.TREE
        # Both alias and computed field present:
        assert "model_config" in dumped
        assert "model_family" in dumped

    def test_model_family_propagates_to_serialized_json(self) -> None:
        """model_family round-trips through model_dump_json with the str value."""
        response = self._make_response("prophet_like")
        json_str = response.model_dump_json(by_alias=True)
        assert '"model_family":"additive"' in json_str


class TestRunResponseFeatureFrameVersion:
    """PRP-36 — feature_frame_version + feature_groups computed fields on RunResponse.

    Both fields are computed from ``runtime_info`` JSONB at serialization
    time — no DB column, no migration. Mirrors the model_family precedent.
    """

    _BASE_FIELDS: ClassVar[dict[str, object]] = {
        "run_id": "abc123",
        "status": RunStatus.SUCCESS,
        "model_type": "regression",
        "model_config_data": {"model_type": "regression"},
        "config_hash": "deadbeefdeadbeef",
        "data_window_start": date(2024, 1, 1),
        "data_window_end": date(2024, 1, 31),
        "store_id": 1,
        "product_id": 1,
        "created_at": datetime(2024, 1, 1, 0, 0, 0, tzinfo=UTC),
        "updated_at": datetime(2024, 1, 2, 0, 0, 0, tzinfo=UTC),
    }

    def _make_response(self, runtime_info: dict[str, object] | None) -> RunResponse:
        fields = {**self._BASE_FIELDS, "runtime_info": runtime_info}
        return RunResponse.model_validate(fields)

    def test_feature_frame_version_none_when_runtime_info_missing(self) -> None:
        """A V1-era run with no runtime_info column resolves to None."""
        response = self._make_response(None)
        assert response.feature_frame_version is None
        assert response.feature_groups is None

    def test_feature_frame_version_none_when_key_absent(self) -> None:
        """An existing runtime_info dict without the V key resolves to None."""
        response = self._make_response({"python_version": "3.12"})
        assert response.feature_frame_version is None
        assert response.feature_groups is None

    def test_feature_frame_version_v2_extracted(self) -> None:
        """A V2 run surfaces feature_frame_version=2 and feature_groups dict."""
        response = self._make_response(
            {
                "feature_frame_version": 2,
                "feature_groups": {
                    "target_history": ["lag_1", "lag_7"],
                    "calendar": ["dow_sin", "dow_cos"],
                },
            }
        )
        assert response.feature_frame_version == 2
        assert response.feature_groups == {
            "target_history": ["lag_1", "lag_7"],
            "calendar": ["dow_sin", "dow_cos"],
        }

    def test_feature_frame_version_v1_extracted(self) -> None:
        """A V1 run with explicit feature_frame_version=1 round-trips; feature_groups None."""
        response = self._make_response({"feature_frame_version": 1})
        assert response.feature_frame_version == 1
        assert response.feature_groups is None

    def test_feature_frame_version_invalid_value_resolves_to_none(self) -> None:
        """A non-int feature_frame_version value resolves to None (defensive)."""
        response = self._make_response({"feature_frame_version": "two"})
        assert response.feature_frame_version is None

    def test_feature_groups_invalid_type_resolves_to_none(self) -> None:
        """A non-dict feature_groups value resolves to None (defensive)."""
        response = self._make_response({"feature_frame_version": 2, "feature_groups": ["lag_1"]})
        assert response.feature_groups is None
