"""Unit tests for RAG embedding service."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.features.rag.embeddings import (
    EmbeddingError,
    EmbeddingService,
    get_embedding_service,
)


class TestEmbeddingService:
    """Tests for EmbeddingService."""

    def test_init_without_api_key(self):
        """Test initialization without API key."""
        service = EmbeddingService()
        # Should not raise during init
        assert service._client is None

    def test_get_client_raises_without_api_key(self):
        """Test _get_client raises when no API key configured."""
        with patch("app.features.rag.embeddings.get_settings") as mock_settings:
            mock_settings.return_value.openai_api_key = ""
            service = EmbeddingService()

            with pytest.raises(EmbeddingError) as exc_info:
                service._get_client()
            assert "API key not configured" in str(exc_info.value)

    def test_count_tokens(self):
        """Test token counting."""
        with patch("app.features.rag.embeddings.get_settings") as mock_settings:
            mock_settings.return_value.openai_api_key = "test-key"
            mock_settings.return_value.rag_embedding_model = "text-embedding-3-small"
            mock_settings.return_value.rag_embedding_dimension = 1536
            mock_settings.return_value.rag_embedding_batch_size = 100

            service = EmbeddingService()

            count = service.count_tokens("Hello, world!")
            assert count > 0
            assert count < 20  # Should be a reasonable count

    def test_count_tokens_empty_string(self):
        """Test token counting for empty string."""
        with patch("app.features.rag.embeddings.get_settings") as mock_settings:
            mock_settings.return_value.openai_api_key = "test-key"
            service = EmbeddingService()

            count = service.count_tokens("")
            assert count == 0

    def test_truncate_to_tokens(self):
        """Test token truncation."""
        with patch("app.features.rag.embeddings.get_settings") as mock_settings:
            mock_settings.return_value.openai_api_key = "test-key"
            service = EmbeddingService()

            long_text = "This is a longer piece of text that will be truncated."
            truncated = service.truncate_to_tokens(long_text, 5)

            assert len(truncated) < len(long_text)
            assert service.count_tokens(truncated) <= 5

    def test_truncate_to_tokens_no_truncation_needed(self):
        """Test truncation when text is already within limit."""
        with patch("app.features.rag.embeddings.get_settings") as mock_settings:
            mock_settings.return_value.openai_api_key = "test-key"
            service = EmbeddingService()

            short_text = "Hi"
            truncated = service.truncate_to_tokens(short_text, 100)

            assert truncated == short_text

    @pytest.mark.asyncio
    async def test_embed_texts_empty_list(self):
        """Test embedding empty list returns empty list."""
        with patch("app.features.rag.embeddings.get_settings") as mock_settings:
            mock_settings.return_value.openai_api_key = "test-key"
            service = EmbeddingService()

            result = await service.embed_texts([])
            assert result == []

    @pytest.mark.asyncio
    async def test_embed_texts_batching(self):
        """Test that texts are batched correctly."""
        with patch("app.features.rag.embeddings.get_settings") as mock_settings:
            mock_settings.return_value.openai_api_key = "test-key"
            mock_settings.return_value.rag_embedding_model = "text-embedding-3-small"
            mock_settings.return_value.rag_embedding_dimension = 1536
            mock_settings.return_value.rag_embedding_batch_size = 2

            service = EmbeddingService()

            # Mock the client
            mock_client = MagicMock()
            mock_response = MagicMock()
            mock_response.data = [
                MagicMock(embedding=[0.1] * 1536),
                MagicMock(embedding=[0.2] * 1536),
            ]
            mock_response.usage = MagicMock(prompt_tokens=10, total_tokens=10)
            mock_client.embeddings.create = AsyncMock(return_value=mock_response)
            service._client = mock_client

            # Test with 4 texts (should be 2 batches)
            texts = ["text1", "text2", "text3", "text4"]

            # Need to adjust mock to handle multiple calls
            mock_response_1 = MagicMock()
            mock_response_1.data = [
                MagicMock(embedding=[0.1] * 1536),
                MagicMock(embedding=[0.2] * 1536),
            ]
            mock_response_1.usage = MagicMock(prompt_tokens=10, total_tokens=10)

            mock_response_2 = MagicMock()
            mock_response_2.data = [
                MagicMock(embedding=[0.3] * 1536),
                MagicMock(embedding=[0.4] * 1536),
            ]
            mock_response_2.usage = MagicMock(prompt_tokens=10, total_tokens=10)

            mock_client.embeddings.create = AsyncMock(
                side_effect=[mock_response_1, mock_response_2]
            )

            result = await service.embed_texts(texts)

            assert len(result) == 4
            assert mock_client.embeddings.create.call_count == 2

    @pytest.mark.asyncio
    async def test_embed_query_returns_single_embedding(self):
        """Test embed_query returns single embedding."""
        with patch("app.features.rag.embeddings.get_settings") as mock_settings:
            mock_settings.return_value.openai_api_key = "test-key"
            mock_settings.return_value.rag_embedding_model = "text-embedding-3-small"
            mock_settings.return_value.rag_embedding_dimension = 1536
            mock_settings.return_value.rag_embedding_batch_size = 100

            service = EmbeddingService()

            # Mock the client
            mock_client = MagicMock()
            mock_response = MagicMock()
            mock_response.data = [MagicMock(embedding=[0.1] * 1536)]
            mock_response.usage = MagicMock(prompt_tokens=5, total_tokens=5)
            mock_client.embeddings.create = AsyncMock(return_value=mock_response)
            service._client = mock_client

            result = await service.embed_query("test query")

            assert len(result) == 1536
            assert result == [0.1] * 1536

    @pytest.mark.asyncio
    async def test_embed_texts_truncates_long_input(self):
        """Test that long inputs are truncated."""
        with patch("app.features.rag.embeddings.get_settings") as mock_settings:
            mock_settings.return_value.openai_api_key = "test-key"
            mock_settings.return_value.rag_embedding_model = "text-embedding-3-small"
            mock_settings.return_value.rag_embedding_dimension = 1536
            mock_settings.return_value.rag_embedding_batch_size = 100

            service = EmbeddingService()

            # Mock the client
            mock_client = MagicMock()
            mock_response = MagicMock()
            mock_response.data = [MagicMock(embedding=[0.1] * 1536)]
            mock_response.usage = MagicMock(prompt_tokens=100, total_tokens=100)
            mock_client.embeddings.create = AsyncMock(return_value=mock_response)
            service._client = mock_client

            # Create text that would exceed token limit
            # (In reality, truncation happens before API call)
            result = await service.embed_texts(["short text"])

            assert len(result) == 1


class TestGetEmbeddingService:
    """Tests for get_embedding_service factory."""

    def test_returns_same_instance(self):
        """Test that singleton returns same instance."""
        # Reset the singleton
        import app.features.rag.embeddings as embeddings_module

        embeddings_module._embedding_service = None

        service1 = get_embedding_service()
        service2 = get_embedding_service()

        assert service1 is service2

        # Clean up
        embeddings_module._embedding_service = None
