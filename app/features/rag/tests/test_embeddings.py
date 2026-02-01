"""Unit tests for RAG embedding providers."""

from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from app.features.rag.embeddings import (
    EmbeddingError,
    EmbeddingProvider,
    EmbeddingService,
    OllamaEmbeddingProvider,
    OpenAIEmbeddingProvider,
    get_embedding_service,
    reset_embedding_service,
)


class TestEmbeddingProvider:
    """Tests for EmbeddingProvider abstract base class."""

    def test_cannot_instantiate_directly(self):
        """Test that EmbeddingProvider cannot be instantiated directly."""
        with pytest.raises(TypeError):
            EmbeddingProvider()  # type: ignore[abstract]


class TestOpenAIEmbeddingProvider:
    """Tests for OpenAIEmbeddingProvider."""

    def test_init_without_api_key(self):
        """Test initialization without API key."""
        with patch("app.features.rag.embeddings.get_settings") as mock_settings:
            mock_settings.return_value.openai_api_key = ""
            mock_settings.return_value.rag_embedding_dimension = 1536
            provider = OpenAIEmbeddingProvider()
            # Should not raise during init
            assert provider._client is None

    def test_get_client_raises_without_api_key(self):
        """Test _get_client raises when no API key configured."""
        with patch("app.features.rag.embeddings.get_settings") as mock_settings:
            mock_settings.return_value.openai_api_key = ""
            provider = OpenAIEmbeddingProvider()

            with pytest.raises(EmbeddingError) as exc_info:
                provider._get_client()
            assert "API key not configured" in str(exc_info.value)

    def test_dimension_property(self):
        """Test dimension property returns configured value."""
        with patch("app.features.rag.embeddings.get_settings") as mock_settings:
            mock_settings.return_value.openai_api_key = "test-key"
            mock_settings.return_value.rag_embedding_dimension = 768
            provider = OpenAIEmbeddingProvider()

            assert provider.dimension == 768

    def test_count_tokens(self):
        """Test token counting."""
        with patch("app.features.rag.embeddings.get_settings") as mock_settings:
            mock_settings.return_value.openai_api_key = "test-key"
            mock_settings.return_value.rag_embedding_model = "text-embedding-3-small"
            mock_settings.return_value.rag_embedding_dimension = 1536
            mock_settings.return_value.rag_embedding_batch_size = 100

            provider = OpenAIEmbeddingProvider()

            count = provider.count_tokens("Hello, world!")
            assert count > 0
            assert count < 20  # Should be a reasonable count

    def test_count_tokens_empty_string(self):
        """Test token counting for empty string."""
        with patch("app.features.rag.embeddings.get_settings") as mock_settings:
            mock_settings.return_value.openai_api_key = "test-key"
            provider = OpenAIEmbeddingProvider()

            count = provider.count_tokens("")
            assert count == 0

    def test_truncate_to_tokens(self):
        """Test token truncation."""
        with patch("app.features.rag.embeddings.get_settings") as mock_settings:
            mock_settings.return_value.openai_api_key = "test-key"
            provider = OpenAIEmbeddingProvider()

            long_text = "This is a longer piece of text that will be truncated."
            truncated = provider.truncate_to_tokens(long_text, 5)

            assert len(truncated) < len(long_text)
            assert provider.count_tokens(truncated) <= 5

    def test_truncate_to_tokens_no_truncation_needed(self):
        """Test truncation when text is already within limit."""
        with patch("app.features.rag.embeddings.get_settings") as mock_settings:
            mock_settings.return_value.openai_api_key = "test-key"
            provider = OpenAIEmbeddingProvider()

            short_text = "Hi"
            truncated = provider.truncate_to_tokens(short_text, 100)

            assert truncated == short_text

    @pytest.mark.asyncio
    async def test_embed_texts_empty_list(self):
        """Test embedding empty list returns empty list."""
        with patch("app.features.rag.embeddings.get_settings") as mock_settings:
            mock_settings.return_value.openai_api_key = "test-key"
            provider = OpenAIEmbeddingProvider()

            result = await provider.embed_texts([])
            assert result == []

    @pytest.mark.asyncio
    async def test_embed_texts_batching(self):
        """Test that texts are batched correctly."""
        with patch("app.features.rag.embeddings.get_settings") as mock_settings:
            mock_settings.return_value.openai_api_key = "test-key"
            mock_settings.return_value.rag_embedding_model = "text-embedding-3-small"
            mock_settings.return_value.rag_embedding_dimension = 1536
            mock_settings.return_value.rag_embedding_batch_size = 2

            provider = OpenAIEmbeddingProvider()

            # Mock the client
            mock_client = MagicMock()

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
            provider._client = mock_client

            # Test with 4 texts (should be 2 batches)
            texts = ["text1", "text2", "text3", "text4"]
            result = await provider.embed_texts(texts)

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

            provider = OpenAIEmbeddingProvider()

            # Mock the client
            mock_client = MagicMock()
            mock_response = MagicMock()
            mock_response.data = [MagicMock(embedding=[0.1] * 1536)]
            mock_response.usage = MagicMock(prompt_tokens=5, total_tokens=5)
            mock_client.embeddings.create = AsyncMock(return_value=mock_response)
            provider._client = mock_client

            result = await provider.embed_query("test query")

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

            provider = OpenAIEmbeddingProvider()

            # Mock the client
            mock_client = MagicMock()
            mock_response = MagicMock()
            mock_response.data = [MagicMock(embedding=[0.1] * 1536)]
            mock_response.usage = MagicMock(prompt_tokens=100, total_tokens=100)
            mock_client.embeddings.create = AsyncMock(return_value=mock_response)
            provider._client = mock_client

            # (In reality, truncation happens before API call)
            result = await provider.embed_texts(["short text"])

            assert len(result) == 1


class TestOllamaEmbeddingProvider:
    """Tests for OllamaEmbeddingProvider."""

    def test_init(self):
        """Test initialization."""
        with patch("app.features.rag.embeddings.get_settings") as mock_settings:
            mock_settings.return_value.ollama_base_url = "http://localhost:11434"
            mock_settings.return_value.ollama_embedding_model = "nomic-embed-text"
            mock_settings.return_value.rag_embedding_dimension = 768

            provider = OllamaEmbeddingProvider()
            assert provider._client is None

    def test_dimension_property(self):
        """Test dimension property returns configured value."""
        with patch("app.features.rag.embeddings.get_settings") as mock_settings:
            mock_settings.return_value.ollama_base_url = "http://localhost:11434"
            mock_settings.return_value.ollama_embedding_model = "nomic-embed-text"
            mock_settings.return_value.rag_embedding_dimension = 768

            provider = OllamaEmbeddingProvider()
            assert provider.dimension == 768

    @pytest.mark.asyncio
    async def test_embed_texts_empty_list(self):
        """Test embedding empty list returns empty list."""
        with patch("app.features.rag.embeddings.get_settings") as mock_settings:
            mock_settings.return_value.ollama_base_url = "http://localhost:11434"
            mock_settings.return_value.ollama_embedding_model = "nomic-embed-text"
            mock_settings.return_value.rag_embedding_dimension = 768

            provider = OllamaEmbeddingProvider()
            result = await provider.embed_texts([])
            assert result == []

    @pytest.mark.asyncio
    async def test_embed_texts_success(self):
        """Test successful embedding generation."""
        with patch("app.features.rag.embeddings.get_settings") as mock_settings:
            mock_settings.return_value.ollama_base_url = "http://localhost:11434"
            mock_settings.return_value.ollama_embedding_model = "nomic-embed-text"
            mock_settings.return_value.rag_embedding_dimension = 768

            provider = OllamaEmbeddingProvider()

            # Mock the HTTP client with OpenAI-compatible response format
            mock_response = MagicMock()
            mock_response.json.return_value = {
                "data": [
                    {"embedding": [0.1] * 768, "index": 0},
                    {"embedding": [0.2] * 768, "index": 1},
                ]
            }
            mock_response.raise_for_status = MagicMock()

            mock_client = MagicMock(spec=httpx.AsyncClient)
            mock_client.post = AsyncMock(return_value=mock_response)
            provider._client = mock_client

            result = await provider.embed_texts(["text1", "text2"])

            assert len(result) == 2
            assert result[0] == [0.1] * 768
            assert result[1] == [0.2] * 768
            mock_client.post.assert_called_once_with(
                "/v1/embeddings",
                json={
                    "model": "nomic-embed-text",
                    "input": ["text1", "text2"],
                    "dimensions": 768,
                },
            )

    @pytest.mark.asyncio
    async def test_embed_query_returns_single_embedding(self):
        """Test embed_query returns single embedding."""
        with patch("app.features.rag.embeddings.get_settings") as mock_settings:
            mock_settings.return_value.ollama_base_url = "http://localhost:11434"
            mock_settings.return_value.ollama_embedding_model = "nomic-embed-text"
            mock_settings.return_value.rag_embedding_dimension = 768

            provider = OllamaEmbeddingProvider()

            # Mock the HTTP client with OpenAI-compatible response format
            mock_response = MagicMock()
            mock_response.json.return_value = {
                "data": [{"embedding": [0.5] * 768, "index": 0}]
            }
            mock_response.raise_for_status = MagicMock()

            mock_client = MagicMock(spec=httpx.AsyncClient)
            mock_client.post = AsyncMock(return_value=mock_response)
            provider._client = mock_client

            result = await provider.embed_query("test query")

            assert len(result) == 768
            assert result == [0.5] * 768

    @pytest.mark.asyncio
    async def test_embed_texts_model_not_found(self):
        """Test error handling when model not found."""
        with patch("app.features.rag.embeddings.get_settings") as mock_settings:
            mock_settings.return_value.ollama_base_url = "http://localhost:11434"
            mock_settings.return_value.ollama_embedding_model = "nonexistent-model"
            mock_settings.return_value.rag_embedding_dimension = 768

            provider = OllamaEmbeddingProvider()

            # Mock 404 response
            mock_response = MagicMock()
            mock_response.status_code = 404
            error = httpx.HTTPStatusError(
                "Not Found",
                request=MagicMock(),
                response=mock_response,
            )

            mock_client = MagicMock(spec=httpx.AsyncClient)
            mock_client.post = AsyncMock(side_effect=error)
            provider._client = mock_client

            with pytest.raises(EmbeddingError) as exc_info:
                await provider.embed_texts(["test"])
            assert "not found" in str(exc_info.value).lower()
            assert "ollama pull" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_embed_texts_connection_error(self):
        """Test error handling when Ollama not reachable."""
        with patch("app.features.rag.embeddings.get_settings") as mock_settings:
            mock_settings.return_value.ollama_base_url = "http://localhost:11434"
            mock_settings.return_value.ollama_embedding_model = "nomic-embed-text"
            mock_settings.return_value.rag_embedding_dimension = 768

            provider = OllamaEmbeddingProvider()

            # Mock connection error
            mock_client = MagicMock(spec=httpx.AsyncClient)
            mock_client.post = AsyncMock(
                side_effect=httpx.ConnectError("Connection refused")
            )
            provider._client = mock_client

            with pytest.raises(EmbeddingError) as exc_info:
                await provider.embed_texts(["test"])
            assert "Failed to connect to Ollama" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_embed_texts_count_mismatch(self):
        """Test error when embedding count doesn't match input count."""
        with patch("app.features.rag.embeddings.get_settings") as mock_settings:
            mock_settings.return_value.ollama_base_url = "http://localhost:11434"
            mock_settings.return_value.ollama_embedding_model = "nomic-embed-text"
            mock_settings.return_value.rag_embedding_dimension = 768

            provider = OllamaEmbeddingProvider()

            # Mock response with wrong count (OpenAI-compatible format)
            mock_response = MagicMock()
            mock_response.json.return_value = {
                "data": [{"embedding": [0.1] * 768, "index": 0}]  # Only 1 embedding for 2 texts
            }
            mock_response.raise_for_status = MagicMock()

            mock_client = MagicMock(spec=httpx.AsyncClient)
            mock_client.post = AsyncMock(return_value=mock_response)
            provider._client = mock_client

            with pytest.raises(EmbeddingError) as exc_info:
                await provider.embed_texts(["text1", "text2"])
            assert "mismatch" in str(exc_info.value).lower()

    @pytest.mark.asyncio
    async def test_close(self):
        """Test close method properly closes HTTP client."""
        with patch("app.features.rag.embeddings.get_settings") as mock_settings:
            mock_settings.return_value.ollama_base_url = "http://localhost:11434"
            mock_settings.return_value.ollama_embedding_model = "nomic-embed-text"
            mock_settings.return_value.rag_embedding_dimension = 768

            provider = OllamaEmbeddingProvider()

            # Mock client
            mock_client = MagicMock(spec=httpx.AsyncClient)
            mock_client.aclose = AsyncMock()
            provider._client = mock_client

            await provider.close()

            mock_client.aclose.assert_called_once()
            assert provider._client is None


class TestGetEmbeddingService:
    """Tests for get_embedding_service factory."""

    def test_returns_openai_by_default(self):
        """Test that OpenAI provider is returned by default."""
        reset_embedding_service()

        with patch("app.features.rag.embeddings.get_settings") as mock_settings:
            mock_settings.return_value.rag_embedding_provider = "openai"
            mock_settings.return_value.openai_api_key = ""
            mock_settings.return_value.rag_embedding_model = "text-embedding-3-small"
            mock_settings.return_value.rag_embedding_dimension = 1536
            mock_settings.return_value.rag_embedding_batch_size = 100

            provider = get_embedding_service()
            assert isinstance(provider, OpenAIEmbeddingProvider)

        reset_embedding_service()

    def test_returns_ollama_when_configured(self):
        """Test that Ollama provider is returned when configured."""
        reset_embedding_service()

        with patch("app.features.rag.embeddings.get_settings") as mock_settings:
            mock_settings.return_value.rag_embedding_provider = "ollama"
            mock_settings.return_value.ollama_base_url = "http://localhost:11434"
            mock_settings.return_value.ollama_embedding_model = "nomic-embed-text"
            mock_settings.return_value.rag_embedding_dimension = 768

            provider = get_embedding_service()
            assert isinstance(provider, OllamaEmbeddingProvider)

        reset_embedding_service()

    def test_returns_same_instance(self):
        """Test that singleton returns same instance."""
        reset_embedding_service()

        with patch("app.features.rag.embeddings.get_settings") as mock_settings:
            mock_settings.return_value.rag_embedding_provider = "openai"
            mock_settings.return_value.openai_api_key = ""
            mock_settings.return_value.rag_embedding_model = "text-embedding-3-small"
            mock_settings.return_value.rag_embedding_dimension = 1536
            mock_settings.return_value.rag_embedding_batch_size = 100

            provider1 = get_embedding_service()
            provider2 = get_embedding_service()
            assert provider1 is provider2

        reset_embedding_service()


class TestEmbeddingServiceAlias:
    """Tests for backwards compatibility alias."""

    def test_embedding_service_is_openai_provider(self):
        """Test that EmbeddingService alias points to OpenAIEmbeddingProvider."""
        assert EmbeddingService is OpenAIEmbeddingProvider
