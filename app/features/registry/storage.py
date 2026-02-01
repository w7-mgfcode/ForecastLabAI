"""Artifact storage providers for model registry.

Provides abstract interface and LocalFS implementation for storing
model artifacts with integrity verification via SHA-256 checksums.

CRITICAL: All paths are validated to prevent directory traversal attacks.
"""

from __future__ import annotations

import hashlib
import shutil
from abc import ABC, abstractmethod
from pathlib import Path

import structlog

from app.core.config import get_settings

logger = structlog.get_logger()


class StorageError(Exception):
    """Base exception for storage operations."""

    pass


class ArtifactNotFoundError(StorageError):
    """Artifact not found at specified URI."""

    pass


class ChecksumMismatchError(StorageError):
    """Artifact checksum does not match stored value."""

    pass


class AbstractStorageProvider(ABC):
    """Abstract base class for artifact storage.

    CRITICAL: All storage providers must implement these methods.
    This allows future S3/GCS implementations.
    """

    @abstractmethod
    def save(self, source_path: Path, artifact_uri: str) -> tuple[str, int]:
        """Save an artifact to storage.

        Args:
            source_path: Local path to artifact file.
            artifact_uri: Relative URI for storage.

        Returns:
            Tuple of (sha256_hash, size_bytes).

        Raises:
            StorageError: If save fails.
        """
        pass

    @abstractmethod
    def load(self, artifact_uri: str, expected_hash: str | None = None) -> Path:
        """Load an artifact from storage.

        Args:
            artifact_uri: Relative URI of artifact.
            expected_hash: If provided, verify checksum.

        Returns:
            Path to artifact (may be temp file for remote storage).

        Raises:
            ArtifactNotFoundError: If artifact doesn't exist.
            ChecksumMismatchError: If hash verification fails.
        """
        pass

    @abstractmethod
    def delete(self, artifact_uri: str) -> bool:
        """Delete an artifact from storage.

        Args:
            artifact_uri: Relative URI of artifact.

        Returns:
            True if deleted, False if not found.
        """
        pass

    @abstractmethod
    def exists(self, artifact_uri: str) -> bool:
        """Check if an artifact exists.

        Args:
            artifact_uri: Relative URI of artifact.

        Returns:
            True if exists, False otherwise.
        """
        pass

    @staticmethod
    def compute_hash(file_path: Path) -> str:
        """Compute SHA-256 hash of a file.

        Args:
            file_path: Path to file.

        Returns:
            Hexadecimal SHA-256 hash.
        """
        sha256 = hashlib.sha256()
        with file_path.open("rb") as f:
            for chunk in iter(lambda: f.read(8192), b""):
                sha256.update(chunk)
        return sha256.hexdigest()


class LocalFSProvider(AbstractStorageProvider):
    """Local filesystem storage provider.

    CRITICAL: Default provider for development and single-node deployments.
    """

    def __init__(self, root_dir: Path | str | None = None) -> None:
        """Initialize with root directory.

        Args:
            root_dir: Root directory for artifacts. Defaults to Settings value.
        """
        if root_dir is None:
            settings = get_settings()
            root_dir = Path(settings.registry_artifact_root)
        elif isinstance(root_dir, str):
            root_dir = Path(root_dir)
        self.root_dir = root_dir.resolve()
        self.root_dir.mkdir(parents=True, exist_ok=True)

    def _resolve_path(self, artifact_uri: str) -> Path:
        """Resolve artifact URI to full path.

        CRITICAL: Validates path is within root to prevent traversal.

        Args:
            artifact_uri: Relative URI of artifact.

        Returns:
            Resolved absolute path.

        Raises:
            StorageError: If path traversal attempt detected.
        """
        full_path = (self.root_dir / artifact_uri).resolve()
        # Security: ensure path is within root
        try:
            full_path.relative_to(self.root_dir)
        except ValueError:
            logger.warning(
                "registry.path_traversal_attempt",
                artifact_uri=artifact_uri,
                root_dir=str(self.root_dir),
            )
            raise StorageError(f"Path traversal attempt: {artifact_uri}") from None
        return full_path

    def save(self, source_path: Path, artifact_uri: str) -> tuple[str, int]:
        """Save artifact to local filesystem.

        Args:
            source_path: Local path to artifact file.
            artifact_uri: Relative URI for storage.

        Returns:
            Tuple of (sha256_hash, size_bytes).

        Raises:
            StorageError: If save fails.
        """
        dest_path = self._resolve_path(artifact_uri)
        dest_path.parent.mkdir(parents=True, exist_ok=True)

        # Copy file first
        shutil.copy2(source_path, dest_path)

        # Compute hash and size from the saved file
        file_hash = self.compute_hash(dest_path)
        file_size = dest_path.stat().st_size

        logger.info(
            "registry.artifact_saved",
            artifact_uri=artifact_uri,
            hash=file_hash,
            size_bytes=file_size,
        )

        return file_hash, file_size

    def load(self, artifact_uri: str, expected_hash: str | None = None) -> Path:
        """Load artifact from local filesystem.

        Args:
            artifact_uri: Relative URI of artifact.
            expected_hash: If provided, verify checksum.

        Returns:
            Path to artifact.

        Raises:
            ArtifactNotFoundError: If artifact doesn't exist.
            ChecksumMismatchError: If hash verification fails.
        """
        full_path = self._resolve_path(artifact_uri)

        if not full_path.exists():
            raise ArtifactNotFoundError(f"Artifact not found: {artifact_uri}")

        # Verify hash if provided
        if expected_hash is not None:
            actual_hash = self.compute_hash(full_path)
            if actual_hash != expected_hash:
                logger.warning(
                    "registry.checksum_mismatch",
                    artifact_uri=artifact_uri,
                    expected=expected_hash,
                    actual=actual_hash,
                )
                raise ChecksumMismatchError(
                    f"Checksum mismatch for {artifact_uri}: "
                    f"expected {expected_hash}, got {actual_hash}"
                )

        return full_path

    def delete(self, artifact_uri: str) -> bool:
        """Delete artifact from local filesystem.

        Args:
            artifact_uri: Relative URI of artifact.

        Returns:
            True if deleted, False if not found.
        """
        full_path = self._resolve_path(artifact_uri)

        if not full_path.exists():
            return False

        full_path.unlink()
        logger.info("registry.artifact_deleted", artifact_uri=artifact_uri)
        return True

    def exists(self, artifact_uri: str) -> bool:
        """Check if artifact exists on local filesystem.

        Args:
            artifact_uri: Relative URI of artifact.

        Returns:
            True if exists, False otherwise.
        """
        full_path = self._resolve_path(artifact_uri)
        return full_path.exists()
