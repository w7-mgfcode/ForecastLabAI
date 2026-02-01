"""Embedding service for RAG knowledge base.

Provides async embedding generation using OpenAI API:
- Batch processing with configurable batch size
- Rate limit handling with exponential backoff
- Token usage logging for cost tracking

CRITICAL: Uses AsyncOpenAI for non-blocking API calls.
"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

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


class EmbeddingService:
    """Service for generating text embeddings via OpenAI API.

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
        """Initialize embedding service with OpenAI client."""
        self.settings = get_settings()
        self._encoder = tiktoken.get_encoding("cl100k_base")

        # Initialize client (will fail on first call if no API key)
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
            token_count = self.count_tokens(text)
            if token_count > self.MAX_TOKENS_PER_INPUT:
                text = self.truncate_to_tokens(text, self.MAX_TOKENS_PER_INPUT)
                token_count = self.count_tokens(text)
                logger.warning(
                    "rag.embedding_text_truncated",
                    original_tokens=self.count_tokens(text),
                    truncated_to=self.MAX_TOKENS_PER_INPUT,
                )
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


# Singleton instance for dependency injection
_embedding_service: EmbeddingService | None = None


def get_embedding_service() -> EmbeddingService:
    """Get singleton embedding service instance.

    Returns:
        EmbeddingService instance.
    """
    global _embedding_service
    if _embedding_service is None:
        _embedding_service = EmbeddingService()
    return _embedding_service
