"""Tests for forecasting persistence layer."""

from pathlib import Path
from tempfile import TemporaryDirectory

import numpy as np
import pytest

from app.features.forecasting.models import NaiveForecaster, SeasonalNaiveForecaster
from app.features.forecasting.persistence import (
    ModelBundle,
    load_model_bundle,
    save_model_bundle,
)


class TestModelBundle:
    """Tests for ModelBundle dataclass."""

    def test_bundle_creation(self, sample_naive_config, sample_time_series):
        """Test creating a model bundle."""
        model = NaiveForecaster()
        model.fit(sample_time_series)

        bundle = ModelBundle(
            model=model,
            config=sample_naive_config,
            metadata={"store_id": 1, "product_id": 2},
        )

        assert bundle.model is model
        assert bundle.config is sample_naive_config
        assert bundle.metadata["store_id"] == 1
        assert bundle.created_at is None  # Set on save

    def test_compute_hash_determinism(self, sample_naive_config, sample_time_series):
        """Test that compute_hash is deterministic."""
        model = NaiveForecaster()
        model.fit(sample_time_series)

        bundle1 = ModelBundle(
            model=model,
            config=sample_naive_config,
            metadata={"store_id": 1},
        )

        bundle2 = ModelBundle(
            model=model,
            config=sample_naive_config,
            metadata={"store_id": 1},
        )

        assert bundle1.compute_hash() == bundle2.compute_hash()

    def test_compute_hash_changes_with_metadata(self, sample_naive_config, sample_time_series):
        """Test that compute_hash changes when metadata differs."""
        model = NaiveForecaster()
        model.fit(sample_time_series)

        bundle1 = ModelBundle(
            model=model,
            config=sample_naive_config,
            metadata={"store_id": 1},
        )

        bundle2 = ModelBundle(
            model=model,
            config=sample_naive_config,
            metadata={"store_id": 2},
        )

        assert bundle1.compute_hash() != bundle2.compute_hash()


class TestSaveLoadBundle:
    """Tests for save_model_bundle and load_model_bundle functions."""

    def test_save_load_roundtrip(self, sample_naive_config, sample_time_series, tmp_model_path):
        """Test saving and loading preserves model predictions."""
        # Create and fit model
        model = NaiveForecaster()
        model.fit(sample_time_series)
        original_predictions = model.predict(horizon=7)

        # Create bundle and save
        bundle = ModelBundle(
            model=model,
            config=sample_naive_config,
            metadata={"store_id": 1, "product_id": 2},
        )

        saved_path = save_model_bundle(bundle, tmp_model_path)

        assert saved_path.exists()
        assert saved_path.suffix == ".joblib"

        # Load and verify
        loaded_bundle = load_model_bundle(saved_path)

        loaded_predictions = loaded_bundle.model.predict(horizon=7)
        np.testing.assert_array_equal(original_predictions, loaded_predictions)

    def test_save_adds_metadata(self, sample_naive_config, sample_time_series, tmp_model_path):
        """Test that save adds version metadata."""
        model = NaiveForecaster()
        model.fit(sample_time_series)

        bundle = ModelBundle(
            model=model,
            config=sample_naive_config,
            metadata={},
        )

        save_model_bundle(bundle, tmp_model_path)

        assert bundle.created_at is not None
        assert bundle.python_version is not None
        assert bundle.sklearn_version is not None
        assert bundle.bundle_hash is not None

    def test_save_creates_directory(self, sample_naive_config, sample_time_series):
        """Test that save creates parent directories if needed."""
        with TemporaryDirectory() as tmpdir:
            deep_path = Path(tmpdir) / "a" / "b" / "c" / "model"

            model = NaiveForecaster()
            model.fit(sample_time_series)

            bundle = ModelBundle(
                model=model,
                config=sample_naive_config,
            )

            saved_path = save_model_bundle(bundle, deep_path)

            assert saved_path.exists()

    def test_save_adds_joblib_extension(
        self, sample_naive_config, sample_time_series, tmp_model_path
    ):
        """Test that save adds .joblib extension if missing."""
        model = NaiveForecaster()
        model.fit(sample_time_series)

        bundle = ModelBundle(
            model=model,
            config=sample_naive_config,
        )

        saved_path = save_model_bundle(bundle, tmp_model_path)

        assert saved_path.suffix == ".joblib"

    def test_load_nonexistent_raises(self):
        """Test that loading nonexistent file raises FileNotFoundError."""
        with pytest.raises(FileNotFoundError, match="not found"):
            load_model_bundle("/nonexistent/path/model.joblib")

    def test_config_preserved(self, sample_seasonal_config, sample_seasonal_series, tmp_model_path):
        """Test that config is preserved after save/load."""
        model = SeasonalNaiveForecaster(season_length=7)
        model.fit(sample_seasonal_series)

        bundle = ModelBundle(
            model=model,
            config=sample_seasonal_config,
            metadata={"key": "value"},
        )

        save_model_bundle(bundle, tmp_model_path)
        loaded_bundle = load_model_bundle(tmp_model_path + ".joblib")

        assert loaded_bundle.config.model_type == "seasonal_naive"
        assert loaded_bundle.config.season_length == 7
        assert loaded_bundle.config.config_hash() == sample_seasonal_config.config_hash()

    def test_metadata_preserved(self, sample_naive_config, sample_time_series, tmp_model_path):
        """Test that metadata is preserved after save/load."""
        model = NaiveForecaster()
        model.fit(sample_time_series)

        metadata = {
            "store_id": 42,
            "product_id": 99,
            "train_start_date": "2024-01-01",
            "train_end_date": "2024-01-31",
        }

        bundle = ModelBundle(
            model=model,
            config=sample_naive_config,
            metadata=metadata,
        )

        save_model_bundle(bundle, tmp_model_path)
        loaded_bundle = load_model_bundle(tmp_model_path + ".joblib")

        assert loaded_bundle.metadata["store_id"] == 42
        assert loaded_bundle.metadata["product_id"] == 99
        assert loaded_bundle.metadata["train_start_date"] == "2024-01-01"

    def test_bundle_hash_preserved(self, sample_naive_config, sample_time_series, tmp_model_path):
        """Test that bundle_hash is preserved after save/load."""
        model = NaiveForecaster()
        model.fit(sample_time_series)

        bundle = ModelBundle(
            model=model,
            config=sample_naive_config,
        )

        save_model_bundle(bundle, tmp_model_path)
        original_hash = bundle.bundle_hash

        loaded_bundle = load_model_bundle(tmp_model_path + ".joblib")

        assert loaded_bundle.bundle_hash == original_hash
