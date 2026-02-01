"""Model persistence layer using joblib serialization.

Provides ModelBundle container for storing model + config + metadata,
and save/load functions with version compatibility warnings.

CRITICAL: Models saved with one Python/sklearn version may not load in another.
"""

from __future__ import annotations

import hashlib
import json
import sys
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING

import joblib  # type: ignore[import-untyped]
import sklearn  # type: ignore[import-untyped]
import structlog

if TYPE_CHECKING:
    from app.features.forecasting.models import BaseForecaster
    from app.features.forecasting.schemas import ModelConfig

logger = structlog.get_logger()


@dataclass
class ModelBundle:
    """Bundle containing model, config, and metadata for persistence.

    CRITICAL: Includes version info for compatibility checking.

    Attributes:
        model: The fitted forecaster model.
        config: Model configuration used for training.
        metadata: Additional metadata (e.g., store_id, product_id, dates).
        created_at: Timestamp when bundle was created.
        python_version: Python version used when saving.
        sklearn_version: Scikit-learn version used when saving.
        bundle_hash: Deterministic hash of bundle contents.
    """

    model: BaseForecaster
    config: ModelConfig
    metadata: dict[str, object] = field(default_factory=lambda: {})

    # Auto-populated on save
    created_at: datetime | None = None
    python_version: str | None = None
    sklearn_version: str | None = None
    bundle_hash: str | None = None

    def compute_hash(self) -> str:
        """Compute deterministic hash of bundle contents.

        Returns:
            16-character hex string hash.
        """
        content = {
            "config_hash": self.config.config_hash(),
            "model_params": self.model.get_params(),
            "metadata": self.metadata,
        }
        return hashlib.sha256(
            json.dumps(content, sort_keys=True, default=str).encode()
        ).hexdigest()[:16]


def save_model_bundle(bundle: ModelBundle, path: str | Path) -> Path:
    """Save model bundle to disk using joblib.

    CRITICAL: Records Python and sklearn versions for compatibility warnings.

    Args:
        bundle: ModelBundle to save.
        path: File path (will add .joblib extension if missing).

    Returns:
        Path to saved file.

    Raises:
        OSError: If unable to create directory or write file.
    """
    path = Path(path)
    if not path.suffix:
        path = path.with_suffix(".joblib")

    # Ensure directory exists
    path.parent.mkdir(parents=True, exist_ok=True)

    # Populate metadata
    bundle.created_at = datetime.now(UTC)
    bundle.python_version = sys.version
    bundle.sklearn_version = sklearn.__version__
    bundle.bundle_hash = bundle.compute_hash()

    # Save with compression
    joblib.dump(bundle, path, compress=3)  # pyright: ignore[reportUnknownMemberType]

    logger.info(
        "forecasting.model_bundle_saved",
        path=str(path),
        bundle_hash=bundle.bundle_hash,
        python_version=bundle.python_version,
        sklearn_version=bundle.sklearn_version,
    )

    return path


def load_model_bundle(path: str | Path, base_dir: str | Path | None = None) -> ModelBundle:
    """Load model bundle from disk.

    CRITICAL: Logs warning if versions don't match.
    SECURITY: Validates path is within allowed base directory to prevent path traversal.

    Args:
        path: Path to saved bundle.
        base_dir: Optional base directory for path validation. If provided,
            the resolved path must be within this directory.

    Returns:
        Loaded ModelBundle.

    Raises:
        FileNotFoundError: If path doesn't exist.
        ValueError: If path is outside the allowed base directory.
    """
    path = Path(path).resolve()

    # Security: validate path is within allowed base directory
    if base_dir is not None:
        base_path = Path(base_dir).resolve()
        try:
            path.relative_to(base_path)
        except ValueError:
            logger.warning(
                "forecasting.model_load_rejected",
                path=str(path),
                base_dir=str(base_path),
                reason="path_outside_allowed_directory",
            )
            raise ValueError(
                f"Model path '{path}' is outside the allowed artifacts directory '{base_path}'. "
                "Only model artifacts within the configured directory can be loaded."
            ) from None

    if not path.exists():
        raise FileNotFoundError(f"Model bundle not found: {path}")

    bundle: ModelBundle = joblib.load(path)  # pyright: ignore[reportUnknownMemberType]

    # Version compatibility warnings
    current_python_major_minor = f"{sys.version_info.major}.{sys.version_info.minor}"
    if bundle.python_version:
        saved_python_major_minor = bundle.python_version.split()[0].rsplit(".", 1)[0]
        if saved_python_major_minor != current_python_major_minor:
            logger.warning(
                "forecasting.python_version_mismatch",
                saved_python=bundle.python_version,
                current_python=sys.version,
            )

    if bundle.sklearn_version and bundle.sklearn_version != sklearn.__version__:
        logger.warning(
            "forecasting.sklearn_version_mismatch",
            saved_sklearn=bundle.sklearn_version,
            current_sklearn=sklearn.__version__,
        )

    logger.info(
        "forecasting.model_bundle_loaded",
        path=str(path),
        bundle_hash=bundle.bundle_hash,
        model_type=bundle.config.model_type,
    )

    return bundle
