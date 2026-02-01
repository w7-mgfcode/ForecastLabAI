"""Unit tests for registry storage providers."""

import hashlib
from pathlib import Path

import pytest

from app.features.registry.storage import (
    ArtifactNotFoundError,
    ChecksumMismatchError,
    LocalFSProvider,
    StorageError,
)


class TestLocalFSProviderInit:
    """Tests for LocalFSProvider initialization."""

    def test_init_creates_root_dir(self, temp_artifact_dir: Path) -> None:
        """Should create root directory if it doesn't exist."""
        new_root = temp_artifact_dir / "new_subdir"
        assert not new_root.exists()
        provider = LocalFSProvider(root_dir=new_root)
        assert provider.root_dir.exists()

    def test_init_with_string_path(self, temp_artifact_dir: Path) -> None:
        """Should accept string path."""
        provider = LocalFSProvider(root_dir=str(temp_artifact_dir))
        assert provider.root_dir == temp_artifact_dir

    def test_init_resolves_path(self, temp_artifact_dir: Path) -> None:
        """Should resolve path to absolute."""
        relative_path = temp_artifact_dir / "subdir" / ".." / "resolved"
        provider = LocalFSProvider(root_dir=relative_path)
        assert provider.root_dir.is_absolute()
        assert ".." not in str(provider.root_dir)


class TestLocalFSProviderSave:
    """Tests for LocalFSProvider.save method."""

    def test_save_copies_file(
        self,
        storage_provider: LocalFSProvider,
        sample_artifact_file: Path,
        sample_artifact_content: bytes,
    ) -> None:
        """Should copy file to destination."""
        artifact_uri = "models/test.pkl"
        storage_provider.save(sample_artifact_file, artifact_uri)

        dest_path = storage_provider.root_dir / artifact_uri
        assert dest_path.exists()
        assert dest_path.read_bytes() == sample_artifact_content

    def test_save_returns_hash_and_size(
        self,
        storage_provider: LocalFSProvider,
        sample_artifact_file: Path,
        sample_artifact_content: bytes,
    ) -> None:
        """Should return SHA-256 hash and file size."""
        artifact_uri = "models/test.pkl"
        file_hash, file_size = storage_provider.save(sample_artifact_file, artifact_uri)

        expected_hash = hashlib.sha256(sample_artifact_content).hexdigest()
        expected_size = len(sample_artifact_content)

        assert file_hash == expected_hash
        assert file_size == expected_size

    def test_save_creates_parent_directories(
        self,
        storage_provider: LocalFSProvider,
        sample_artifact_file: Path,
    ) -> None:
        """Should create parent directories if they don't exist."""
        artifact_uri = "deep/nested/path/model.pkl"
        storage_provider.save(sample_artifact_file, artifact_uri)

        dest_path = storage_provider.root_dir / artifact_uri
        assert dest_path.exists()

    def test_save_overwrites_existing(
        self,
        storage_provider: LocalFSProvider,
        sample_artifact_file: Path,
    ) -> None:
        """Should overwrite existing file."""
        artifact_uri = "models/test.pkl"

        # Create existing file
        dest_path = storage_provider.root_dir / artifact_uri
        dest_path.parent.mkdir(parents=True, exist_ok=True)
        dest_path.write_text("old content")

        # Save new file
        storage_provider.save(sample_artifact_file, artifact_uri)

        # Should have new content
        assert dest_path.read_bytes() == sample_artifact_file.read_bytes()


class TestLocalFSProviderLoad:
    """Tests for LocalFSProvider.load method."""

    def test_load_returns_path(
        self,
        storage_provider: LocalFSProvider,
        sample_artifact_file: Path,
    ) -> None:
        """Should return path to artifact."""
        artifact_uri = "models/test.pkl"
        storage_provider.save(sample_artifact_file, artifact_uri)

        loaded_path = storage_provider.load(artifact_uri)
        assert loaded_path == storage_provider.root_dir / artifact_uri

    def test_load_raises_not_found(self, storage_provider: LocalFSProvider) -> None:
        """Should raise ArtifactNotFoundError if file doesn't exist."""
        with pytest.raises(ArtifactNotFoundError) as exc_info:
            storage_provider.load("nonexistent/model.pkl")
        assert "not found" in str(exc_info.value).lower()

    def test_load_with_hash_verification(
        self,
        storage_provider: LocalFSProvider,
        sample_artifact_file: Path,
        sample_artifact_content: bytes,
    ) -> None:
        """Should verify hash when provided."""
        artifact_uri = "models/test.pkl"
        expected_hash = hashlib.sha256(sample_artifact_content).hexdigest()

        storage_provider.save(sample_artifact_file, artifact_uri)
        loaded_path = storage_provider.load(artifact_uri, expected_hash=expected_hash)

        assert loaded_path.exists()

    def test_load_raises_checksum_mismatch(
        self,
        storage_provider: LocalFSProvider,
        sample_artifact_file: Path,
    ) -> None:
        """Should raise ChecksumMismatchError if hash doesn't match."""
        artifact_uri = "models/test.pkl"
        wrong_hash = "0" * 64

        storage_provider.save(sample_artifact_file, artifact_uri)

        with pytest.raises(ChecksumMismatchError) as exc_info:
            storage_provider.load(artifact_uri, expected_hash=wrong_hash)
        assert "mismatch" in str(exc_info.value).lower()


class TestLocalFSProviderDelete:
    """Tests for LocalFSProvider.delete method."""

    def test_delete_removes_file(
        self,
        storage_provider: LocalFSProvider,
        sample_artifact_file: Path,
    ) -> None:
        """Should delete existing file and return True."""
        artifact_uri = "models/test.pkl"
        storage_provider.save(sample_artifact_file, artifact_uri)

        dest_path = storage_provider.root_dir / artifact_uri
        assert dest_path.exists()

        result = storage_provider.delete(artifact_uri)
        assert result is True
        assert not dest_path.exists()

    def test_delete_returns_false_if_not_found(self, storage_provider: LocalFSProvider) -> None:
        """Should return False if file doesn't exist."""
        result = storage_provider.delete("nonexistent/model.pkl")
        assert result is False


class TestLocalFSProviderExists:
    """Tests for LocalFSProvider.exists method."""

    def test_exists_returns_true(
        self,
        storage_provider: LocalFSProvider,
        sample_artifact_file: Path,
    ) -> None:
        """Should return True if file exists."""
        artifact_uri = "models/test.pkl"
        storage_provider.save(sample_artifact_file, artifact_uri)

        assert storage_provider.exists(artifact_uri) is True

    def test_exists_returns_false(self, storage_provider: LocalFSProvider) -> None:
        """Should return False if file doesn't exist."""
        assert storage_provider.exists("nonexistent/model.pkl") is False


class TestLocalFSProviderComputeHash:
    """Tests for LocalFSProvider.compute_hash static method."""

    def test_compute_hash_sha256(
        self, sample_artifact_file: Path, sample_artifact_content: bytes
    ) -> None:
        """Should compute correct SHA-256 hash."""
        expected_hash = hashlib.sha256(sample_artifact_content).hexdigest()
        actual_hash = LocalFSProvider.compute_hash(sample_artifact_file)
        assert actual_hash == expected_hash

    def test_compute_hash_is_deterministic(self, sample_artifact_file: Path) -> None:
        """Should return same hash for same file."""
        hash1 = LocalFSProvider.compute_hash(sample_artifact_file)
        hash2 = LocalFSProvider.compute_hash(sample_artifact_file)
        assert hash1 == hash2


class TestLocalFSProviderPathTraversal:
    """Tests for path traversal prevention."""

    def test_reject_parent_directory_traversal(self, storage_provider: LocalFSProvider) -> None:
        """Should reject ../.. traversal attempts."""
        with pytest.raises(StorageError) as exc_info:
            storage_provider._resolve_path("../../../etc/passwd")
        assert "traversal" in str(exc_info.value).lower()

    def test_reject_absolute_path(self, storage_provider: LocalFSProvider) -> None:
        """Should reject absolute paths that escape root."""
        with pytest.raises(StorageError) as exc_info:
            storage_provider._resolve_path("/etc/passwd")
        assert "traversal" in str(exc_info.value).lower()

    def test_allow_nested_paths(self, storage_provider: LocalFSProvider) -> None:
        """Should allow valid nested paths."""
        path = storage_provider._resolve_path("models/2024/01/run123.pkl")
        assert path.is_relative_to(storage_provider.root_dir)

    def test_allow_paths_with_dots_in_name(self, storage_provider: LocalFSProvider) -> None:
        """Should allow dots in filenames (not traversal)."""
        path = storage_provider._resolve_path("models/model.v1.0.pkl")
        assert path.is_relative_to(storage_provider.root_dir)
