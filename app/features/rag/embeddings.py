"""Embedding providers for RAG knowledge base.

Provides async embedding generation with multiple backends:
- OpenAI API (default): Batch processing with rate limit handling
- Ollama: Local/LAN embedding generation via HTTP API

CRITICAL: Provider selection via RAG_EMBEDDING_PROVIDER config.
"""

from __future__ import annotations

import asyncio
from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

import httpx
import structlog
import tiktoken
from openai import AsyncOpenAI, RateLimitError

from app.core.config import get_settings

if TYPE_CHECKING:
    pass

logger = structlog.get_logger()


class EmbeddingError(Exception):
    """Error during embedding generation."""

    pass


class EmbeddingProvider(ABC):
    """Abstract base class for embedding providers.

    Defines the interface for generating text embeddings.
    All providers must implement embed_texts, embed_query, and dimension.
    """

    @abstractmethod
    async def embed_texts(self, texts: list[str]) -> list[list[float]]:
        """Generate embeddings for multiple texts.

        Args:
            texts: List of texts to embed.

        Returns:
            List of embedding vectors in same order as input texts.

        Raises:
            EmbeddingError: If embedding generation fails.
        """
        ...

    @abstractmethod
    async def embed_query(self, query: str) -> list[float]:
        """Generate embedding for a single query.

        Args:
            query: Query text to embed.

        Returns:
            Embedding vector.

        Raises:
            EmbeddingError: If embedding generation fails.
        """
        ...

    @property
    @abstractmethod
    def dimension(self) -> int:
        """Return the embedding dimension for this provider.

        Returns:
            Embedding dimension (e.g., 1536 for OpenAI, 768 for nomic-embed-text).
        """
        ...


class OpenAIEmbeddingProvider(EmbeddingProvider):
    """Embedding provider using OpenAI API.

    Handles:
    - Async batch embedding generation
    - Rate limit handling with exponential backoff
    - Token counting and validation
    - Cost tracking via logging

    CRITICAL: OpenAI embedding input limit is 8192 tokens per text.
    """

    MAX_TOKENS_PER_INPUT = 8191  # OpenAI limit
    MAX_INPUTS_PER_BATCH = 2048  # OpenAI batch limit

    def __init__(self) -> None:
        """Initialize OpenAI embedding provider."""
        self.settings = get_settings()
        self._encoder = tiktoken.get_encoding("cl100k_base")
        self._client: AsyncOpenAI | None = None

    def _get_client(self) -> AsyncOpenAI:
        """Get or create the async OpenAI client.

        Returns:
            AsyncOpenAI client instance.

        Raises:
            EmbeddingError: If OpenAI API key is not configured.
        """
        if self._client is None:
            if not self.settings.openai_api_key:
                raise EmbeddingError(
                    "OpenAI API key not configured. Set OPENAI_API_KEY environment variable."
                )
            self._client = AsyncOpenAI(api_key=self.settings.openai_api_key)
        return self._client

    @property
    def dimension(self) -> int:
        """Return configured embedding dimension.

        Returns:
            Embedding dimension from settings.
        """
        return self.settings.rag_embedding_dimension

    def count_tokens(self, text: str) -> int:
        """Count tokens in text using tiktoken.

        Args:
            text: Text to count tokens for.

        Returns:
            Number of tokens.
        """
        return len(self._encoder.encode(text))

    def truncate_to_tokens(self, text: str, max_tokens: int) -> str:
        """Truncate text to a maximum number of tokens.

        Args:
            text: Text to truncate.
            max_tokens: Maximum number of tokens.

        Returns:
            Truncated text.
        """
        tokens = self._encoder.encode(text)
        if len(tokens) <= max_tokens:
            return text
        return self._encoder.decode(tokens[:max_tokens])

    async def embed_texts(
        self,
        texts: list[str],
        max_retries: int = 3,
        retry_delay: float = 1.0,
    ) -> list[list[float]]:
        """Generate embeddings for multiple texts.

        Processes texts in batches according to settings and OpenAI limits.
        Handles rate limits with exponential backoff.

        Args:
            texts: List of texts to embed.
            max_retries: Maximum retry attempts per batch.
            retry_delay: Initial delay between retries (doubles each retry).

        Returns:
            List of embeddings in same order as input texts.

        Raises:
            EmbeddingError: If embedding generation fails after retries.
        """
        if not texts:
            return []

        client = self._get_client()
        batch_size = min(self.settings.rag_embedding_batch_size, self.MAX_INPUTS_PER_BATCH)

        # Validate and truncate texts if needed
        validated_texts: list[str] = []
        total_tokens = 0

        for text in texts:
            original_token_count = self.count_tokens(text)
            if original_token_count > self.MAX_TOKENS_PER_INPUT:
                text = self.truncate_to_tokens(text, self.MAX_TOKENS_PER_INPUT)
                token_count = self.count_tokens(text)
                logger.warning(
                    "rag.embedding_text_truncated",
                    original_tokens=original_token_count,
                    truncated_to=self.MAX_TOKENS_PER_INPUT,
                )
            else:
                token_count = original_token_count
            validated_texts.append(text)
            total_tokens += token_count

        embeddings: list[list[float]] = []

        # Process in batches
        for i in range(0, len(validated_texts), batch_size):
            batch = validated_texts[i : i + batch_size]
            batch_embeddings = await self._embed_batch(client, batch, max_retries, retry_delay)
            embeddings.extend(batch_embeddings)

        logger.info(
            "rag.embeddings_generated",
            text_count=len(texts),
            total_tokens=total_tokens,
            model=self.settings.rag_embedding_model,
            provider="openai",
        )

        return embeddings

    async def embed_query(self, query: str) -> list[float]:
        """Generate embedding for a single query.

        Optimized for single query embedding (no batching overhead).

        Args:
            query: Query text to embed.

        Returns:
            Embedding vector.

        Raises:
            EmbeddingError: If embedding generation fails.
        """
        embeddings = await self.embed_texts([query])
        return embeddings[0]

    async def _embed_batch(
        self,
        client: AsyncOpenAI,
        texts: list[str],
        max_retries: int,
        retry_delay: float,
    ) -> list[list[float]]:
        """Embed a single batch of texts with retry logic.

        Args:
            client: OpenAI async client.
            texts: Batch of texts to embed.
            max_retries: Maximum retry attempts.
            retry_delay: Initial delay between retries.

        Returns:
            List of embeddings.

        Raises:
            EmbeddingError: If all retries fail.
        """
        last_error: Exception | None = None

        for attempt in range(max_retries + 1):
            try:
                response = await client.embeddings.create(
                    model=self.settings.rag_embedding_model,
                    input=texts,
                    dimensions=self.settings.rag_embedding_dimension,
                )

                # Extract embeddings in order
                embeddings = [item.embedding for item in response.data]

                # Log token usage
                if response.usage:
                    logger.debug(
                        "rag.embedding_batch_completed",
                        batch_size=len(texts),
                        prompt_tokens=response.usage.prompt_tokens,
                        total_tokens=response.usage.total_tokens,
                    )

                return embeddings

            except RateLimitError as e:
                last_error = e
                if attempt < max_retries:
                    wait_time = retry_delay * (2**attempt)
                    logger.warning(
                        "rag.embedding_rate_limit",
                        attempt=attempt + 1,
                        max_retries=max_retries,
                        wait_seconds=wait_time,
                    )
                    await asyncio.sleep(wait_time)
                continue

            except Exception as e:
                last_error = e
                logger.error(
                    "rag.embedding_error",
                    error=str(e),
                    error_type=type(e).__name__,
                    batch_size=len(texts),
                )
                raise EmbeddingError(f"Failed to generate embeddings: {e}") from e

        raise EmbeddingError(
            f"Failed to generate embeddings after {max_retries} retries: {last_error}"
        )


class OllamaEmbeddingProvider(EmbeddingProvider):
    """Embedding provider using Ollama's OpenAI-compatible API.

    Provides local/LAN-based embedding generation without OpenAI dependency.
    Uses the /v1/embeddings endpoint (OpenAI-compatible) which supports
    the `dimensions` parameter for output dimension control.

    CRITICAL: Requires Ollama server running with an embedding model pulled.
    """

    def __init__(self) -> None:
        """Initialize Ollama embedding provider."""
        self.settings = get_settings()
        self._client: httpx.AsyncClient | None = None

    def _get_client(self) -> httpx.AsyncClient:
        """Get or create the async HTTP client.

        Returns:
            httpx AsyncClient instance.
        """
        if self._client is None:
            self._client = httpx.AsyncClient(
                base_url=self.settings.ollama_base_url,
                timeout=httpx.Timeout(60.0, connect=10.0),
            )
        return self._client

    @property
    def dimension(self) -> int:
        """Return configured embedding dimension.

        Returns:
            Embedding dimension from settings.
        """
        return self.settings.rag_embedding_dimension

    async def embed_texts(
        self,
        texts: list[str],
        max_retries: int = 3,
        retry_delay: float = 1.0,
    ) -> list[list[float]]:
        """Generate embeddings for multiple texts via Ollama's OpenAI-compatible API.

        Uses /v1/embeddings endpoint which supports the `dimensions` parameter
        to control output embedding size.

        Args:
            texts: List of texts to embed.
            max_retries: Maximum retry attempts.
            retry_delay: Initial delay between retries (doubles each retry).

        Returns:
            List of embeddings in same order as input texts.

        Raises:
            EmbeddingError: If embedding generation fails.
        """
        if not texts:
            return []

        client = self._get_client()
        last_error: Exception | None = None

        for attempt in range(max_retries + 1):
            try:
                # Use OpenAI-compatible endpoint with dimensions parameter
                response = await client.post(
                    "/v1/embeddings",
                    json={
                        "model": self.settings.ollama_embedding_model,
                        "input": texts,
                        "dimensions": self.settings.rag_embedding_dimension,
                    },
                )
                response.raise_for_status()

                data = response.json()

                # OpenAI-compatible response format: {"data": [{"embedding": [...], "index": 0}, ...]}
                embedding_data = data.get("data", [])

                if len(embedding_data) != len(texts):
                    raise EmbeddingError(
                        f"Embedding count mismatch: expected {len(texts)}, got {len(embedding_data)}"
                    )

                # Sort by index to ensure correct order and extract embeddings
                sorted_data = sorted(embedding_data, key=lambda x: x.get("index", 0))
                embeddings: list[list[float]] = [item["embedding"] for item in sorted_data]

                logger.info(
                    "rag.embeddings_generated",
                    text_count=len(texts),
                    model=self.settings.ollama_embedding_model,
                    dimension=self.settings.rag_embedding_dimension,
                    provider="ollama",
                )

                return embeddings

            except httpx.HTTPStatusError as e:
                last_error = e
                if e.response.status_code == 404:
                    # Model not found - don't retry
                    raise EmbeddingError(
                        f"Ollama model '{self.settings.ollama_embedding_model}' not found. "
                        f"Run: ollama pull {self.settings.ollama_embedding_model}"
                    ) from e
                if e.response.status_code >= 500 and attempt < max_retries:
                    # Server error - retry
                    wait_time = retry_delay * (2**attempt)
                    logger.warning(
                        "rag.ollama_server_error",
                        attempt=attempt + 1,
                        max_retries=max_retries,
                        wait_seconds=wait_time,
                        status_code=e.response.status_code,
                    )
                    await asyncio.sleep(wait_time)
                    continue
                logger.error(
                    "rag.embedding_error",
                    error=str(e),
                    error_type=type(e).__name__,
                    status_code=e.response.status_code,
                )
                raise EmbeddingError(f"Ollama API error: {e}") from e

            except httpx.ConnectError as e:
                last_error = e
                logger.error(
                    "rag.ollama_connection_error",
                    error=str(e),
                    base_url=self.settings.ollama_base_url,
                )
                raise EmbeddingError(
                    f"Failed to connect to Ollama at {self.settings.ollama_base_url}. "
                    "Ensure Ollama is running."
                ) from e

            except Exception as e:
                last_error = e
                logger.error(
                    "rag.embedding_error",
                    error=str(e),
                    error_type=type(e).__name__,
                )
                raise EmbeddingError(f"Failed to generate embeddings: {e}") from e

        raise EmbeddingError(
            f"Failed to generate embeddings after {max_retries} retries: {last_error}"
        )

    async def embed_query(self, query: str) -> list[float]:
        """Generate embedding for a single query.

        Args:
            query: Query text to embed.

        Returns:
            Embedding vector.

        Raises:
            EmbeddingError: If embedding generation fails.
        """
        embeddings = await self.embed_texts([query])
        return embeddings[0]

    async def close(self) -> None:
        """Close the HTTP client.

        Should be called when done using the provider.
        """
        if self._client is not None:
            await self._client.aclose()
            self._client = None


# Legacy alias for backwards compatibility
EmbeddingService = OpenAIEmbeddingProvider


# Singleton instances for dependency injection
_embedding_provider: EmbeddingProvider | None = None


def get_embedding_service() -> EmbeddingProvider:
    """Get singleton embedding provider instance.

    Returns provider based on RAG_EMBEDDING_PROVIDER config:
    - "openai": OpenAI API (default)
    - "ollama": Local Ollama server

    Returns:
        EmbeddingProvider instance.
    """
    global _embedding_provider
    if _embedding_provider is None:
        settings = get_settings()
        if settings.rag_embedding_provider == "ollama":
            _embedding_provider = OllamaEmbeddingProvider()
            logger.info(
                "rag.embedding_provider_initialized",
                provider="ollama",
                base_url=settings.ollama_base_url,
                model=settings.ollama_embedding_model,
            )
        else:
            _embedding_provider = OpenAIEmbeddingProvider()
            logger.info(
                "rag.embedding_provider_initialized",
                provider="openai",
                model=settings.rag_embedding_model,
            )
    return _embedding_provider


def reset_embedding_service() -> None:
    """Reset the singleton embedding provider.

    Useful for testing or reconfiguration.
    """
    global _embedding_provider
    _embedding_provider = None
