"""RAG + Agent E2E scenario for seeder validation.

This scenario validates the complete stack:
1. Generate synthetic markdown documents
2. Index documents into pgvector via /rag/index
3. Create agent session via /agents/sessions
4. Send test query via /agents/sessions/{id}/chat
5. Verify response contains citations
6. Clean up session
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from typing import Any

import httpx

from app.core.config import get_settings
from app.core.logging import get_logger

logger = get_logger(__name__)


@dataclass
class RAGScenarioResult:
    """Result of RAG + Agent scenario execution."""

    documents_indexed: int = 0
    session_created: bool = False
    session_id: str | None = None
    query_sent: bool = False
    response_received: bool = False
    citations_found: bool = False
    cleanup_completed: bool = False
    skipped: bool = False
    skip_reason: str | None = None
    errors: list[str] = field(default_factory=list)


class RAGScenarioRunner:
    """Runs the RAG + Agent E2E validation scenario."""

    def __init__(
        self,
        api_base_url: str = "http://localhost:8123",
        seed: int = 42,
    ) -> None:
        """Initialize the scenario runner.

        Args:
            api_base_url: Base URL for the API.
            seed: Random seed for reproducible document generation.
        """
        self.api_base_url = api_base_url.rstrip("/")
        self.rng = random.Random(seed)
        self.result = RAGScenarioResult()

    def _generate_test_documents(self) -> list[dict[str, str]]:
        """Generate synthetic markdown documents for testing.

        Returns:
            List of document dicts with 'content' and 'source_path' keys.
        """
        # Generate 3 small test documents about forecasting
        documents = [
            {
                "content": """# Demand Forecasting Overview

Demand forecasting is the process of predicting future customer demand.

## Key Methods
- **Naive forecasting**: Uses the last observed value
- **Seasonal naive**: Uses the same period from the previous season
- **Moving average**: Uses the mean of recent observations

## Best Practices
1. Always validate with time-based cross-validation
2. Use appropriate metrics (MAE, sMAPE, WAPE)
3. Compare against baselines
""",
                "source_path": "docs/forecasting_overview.md",
            },
            {
                "content": """# Backtesting Guide

Backtesting evaluates forecasting models using historical data.

## Split Strategies
- **Expanding window**: Training data grows with each fold
- **Sliding window**: Fixed-size training window moves forward

## Gap Parameter
The gap parameter simulates operational latency between training cutoff and test period.

## Metrics
- MAE: Mean Absolute Error
- sMAPE: Symmetric Mean Absolute Percentage Error
- WAPE: Weighted Absolute Percentage Error
""",
                "source_path": "docs/backtesting_guide.md",
            },
            {
                "content": """# Model Registry

The model registry tracks trained models and their metadata.

## Run States
- PENDING: Run created but not started
- RUNNING: Training in progress
- SUCCESS: Training completed successfully
- FAILED: Training failed
- ARCHIVED: Run archived (not for production use)

## Deployment Aliases
Aliases like 'production' or 'staging' point to successful runs.
Only SUCCESS runs can have aliases.
""",
                "source_path": "docs/model_registry.md",
            },
        ]
        return documents

    def _is_rag_configured(self) -> tuple[bool, str | None]:
        """Check if RAG is properly configured.

        Returns:
            Tuple of (is_configured, skip_reason if not configured).
        """
        try:
            settings = get_settings()

            # Check if embedding provider is configured
            rag_provider = getattr(settings, "rag_embedding_provider", None)
            if not rag_provider:
                return False, "RAG embedding provider not configured"

            # Check for required API keys based on provider
            if rag_provider == "openai":
                openai_key = getattr(settings, "openai_api_key", None)
                if not openai_key:
                    return False, "OpenAI API key not configured for RAG"
            elif rag_provider == "ollama":
                ollama_url = getattr(settings, "ollama_base_url", None)
                if not ollama_url:
                    return False, "Ollama base URL not configured for RAG"

            return True, None
        except Exception as e:
            return False, f"Failed to check RAG configuration: {e}"

    async def _check_api_health(self, client: httpx.AsyncClient) -> bool:
        """Check if the API is running.

        Args:
            client: HTTP client.

        Returns:
            True if API is healthy, False otherwise.
        """
        try:
            response = await client.get(f"{self.api_base_url}/health")
            return response.status_code == 200
        except httpx.RequestError:
            return False

    async def _index_document(
        self,
        client: httpx.AsyncClient,
        content: str,
        source_path: str,
    ) -> bool:
        """Index a document into the RAG system.

        Args:
            client: HTTP client.
            content: Document content.
            source_path: Document path.

        Returns:
            True if indexing succeeded, False otherwise.
        """
        try:
            response = await client.post(
                f"{self.api_base_url}/rag/index",
                json={
                    "source_type": "markdown",
                    "source_path": source_path,
                    "content": content,
                },
                timeout=30.0,
            )
            if response.status_code in (200, 201):
                return True
            else:
                self.result.errors.append(
                    f"Index failed for {source_path}: {response.status_code} - {response.text}"
                )
                return False
        except httpx.RequestError as e:
            self.result.errors.append(f"Index request failed: {e}")
            return False

    async def _create_agent_session(
        self,
        client: httpx.AsyncClient,
    ) -> str | None:
        """Create an agent session.

        Args:
            client: HTTP client.

        Returns:
            Session ID if created, None otherwise.
        """
        try:
            response = await client.post(
                f"{self.api_base_url}/agents/sessions",
                json={
                    "agent_type": "rag_assistant",
                    "initial_context": None,
                },
                timeout=30.0,
            )
            if response.status_code in (200, 201):
                data: dict[str, Any] = response.json()
                return str(data.get("session_id")) if data.get("session_id") else None
            else:
                self.result.errors.append(
                    f"Session creation failed: {response.status_code} - {response.text}"
                )
                return None
        except httpx.RequestError as e:
            self.result.errors.append(f"Session request failed: {e}")
            return None

    async def _send_chat_query(
        self,
        client: httpx.AsyncClient,
        session_id: str,
        query: str,
    ) -> dict[str, Any] | None:
        """Send a chat query to the agent.

        Args:
            client: HTTP client.
            session_id: Agent session ID.
            query: Query text.

        Returns:
            Response data if successful, None otherwise.
        """
        try:
            response = await client.post(
                f"{self.api_base_url}/agents/sessions/{session_id}/chat",
                json={"message": query},
                timeout=60.0,  # Agent responses can take time
            )
            if response.status_code == 200:
                result: dict[str, Any] = response.json()
                return result
            else:
                self.result.errors.append(
                    f"Chat query failed: {response.status_code} - {response.text}"
                )
                return None
        except httpx.RequestError as e:
            self.result.errors.append(f"Chat request failed: {e}")
            return None

    async def _close_session(
        self,
        client: httpx.AsyncClient,
        session_id: str,
    ) -> bool:
        """Close an agent session.

        Args:
            client: HTTP client.
            session_id: Session ID to close.

        Returns:
            True if closed successfully.
        """
        try:
            response = await client.delete(
                f"{self.api_base_url}/agents/sessions/{session_id}",
                timeout=10.0,
            )
            return response.status_code in (200, 204)
        except httpx.RequestError:
            return False

    async def run(self, dry_run: bool = False) -> RAGScenarioResult:
        """Execute the RAG + Agent E2E scenario.

        Args:
            dry_run: If True, only show what would be done.

        Returns:
            Scenario execution result.
        """
        logger.info("seeder.rag_scenario.started", dry_run=dry_run)

        if dry_run:
            documents = self._generate_test_documents()
            self.result.documents_indexed = len(documents)
            logger.info(
                "seeder.rag_scenario.dry_run",
                documents=len(documents),
                steps=[
                    "index_docs",
                    "create_session",
                    "send_query",
                    "verify_citations",
                    "cleanup",
                ],
            )
            return self.result

        # Preflight check: verify RAG is configured
        is_configured, skip_reason = self._is_rag_configured()
        if not is_configured:
            self.result.skipped = True
            self.result.skip_reason = skip_reason
            logger.info(
                "seeder.rag_scenario.skipped",
                reason=skip_reason,
            )
            return self.result

        async with httpx.AsyncClient() as client:
            # Step 0: Check API health
            if not await self._check_api_health(client):
                self.result.errors.append(
                    f"API not available at {self.api_base_url}. Start the server first."
                )
                return self.result

            # Step 1: Generate and index documents
            documents = self._generate_test_documents()
            indexed_count = 0
            for doc in documents:
                if await self._index_document(client, doc["content"], doc["source_path"]):
                    indexed_count += 1

            self.result.documents_indexed = indexed_count

            if indexed_count == 0:
                self.result.errors.append("No documents were indexed successfully")
                return self.result

            logger.info("seeder.rag_scenario.docs_indexed", count=indexed_count)

            # Step 2: Create agent session
            session_id = await self._create_agent_session(client)
            if not session_id:
                self.result.errors.append("Failed to create agent session")
                return self.result

            self.result.session_created = True
            self.result.session_id = session_id
            logger.info("seeder.rag_scenario.session_created", session_id=session_id)

            # Step 3: Send test query
            query = "What are the key methods for demand forecasting?"
            response = await self._send_chat_query(client, session_id, query)

            if response:
                self.result.query_sent = True
                self.result.response_received = True

                # Step 4: Verify citations
                # Check if response contains citation-like content
                response_text = str(response.get("response", "")).lower()
                citations = response.get("citations", [])

                if citations or "source" in response_text or "docs/" in response_text:
                    self.result.citations_found = True
                    logger.info("seeder.rag_scenario.citations_verified")
                else:
                    logger.warning("seeder.rag_scenario.no_citations_found")

            # Step 5: Cleanup
            if session_id:
                if await self._close_session(client, session_id):
                    self.result.cleanup_completed = True
                    logger.info("seeder.rag_scenario.cleanup_completed")

        logger.info(
            "seeder.rag_scenario.completed",
            success=len(self.result.errors) == 0,
            documents=self.result.documents_indexed,
            citations_found=self.result.citations_found,
        )

        return self.result


async def run_rag_scenario(
    api_base_url: str = "http://localhost:8123",
    seed: int = 42,
    dry_run: bool = False,
) -> RAGScenarioResult:
    """Convenience function to run the RAG + Agent scenario.

    Args:
        api_base_url: Base URL for the API.
        seed: Random seed for reproducibility.
        dry_run: If True, only show what would be done.

    Returns:
        Scenario execution result.
    """
    runner = RAGScenarioRunner(api_base_url=api_base_url, seed=seed)
    return await runner.run(dry_run=dry_run)
