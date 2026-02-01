"""Test fixtures for agents module."""

import uuid
from collections.abc import AsyncGenerator
from datetime import UTC, datetime, timedelta
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import get_settings
from app.core.database import get_db
from app.features.agents.deps import AgentDeps
from app.features.agents.models import AgentSession, AgentType, SessionStatus
from app.features.agents.schemas import (
    ChatRequest,
    ExperimentReport,
    RAGAnswer,
    SessionCreateRequest,
)
from app.features.agents.service import AgentService
from app.main import app

# =============================================================================
# Database Fixtures for Integration Tests
# =============================================================================


@pytest.fixture
async def db_session() -> AsyncGenerator[AsyncSession, None]:
    """Create async database session for integration tests.

    Creates tables if needed, provides a session, and cleans up test data.
    Requires PostgreSQL to be running (docker-compose up -d).
    """
    settings = get_settings()
    engine = create_async_engine(settings.database_url, echo=False)

    async_session_maker = async_sessionmaker(
        engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )

    async with async_session_maker() as session:
        try:
            yield session
        finally:
            # Clean up test sessions (those with session_id starting with "test-")
            await session.execute(
                delete(AgentSession).where(AgentSession.session_id.like("test-%"))
            )
            await session.commit()

    await engine.dispose()


@pytest.fixture
async def client(db_session: AsyncSession) -> AsyncGenerator[AsyncClient, None]:
    """Create test client with database dependency override."""

    async def override_get_db() -> AsyncGenerator[AsyncSession, None]:
        try:
            yield db_session
            await db_session.commit()
        except Exception:
            await db_session.rollback()
            raise

    app.dependency_overrides[get_db] = override_get_db

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as ac:
        yield ac

    app.dependency_overrides.clear()


# =============================================================================
# Session Fixtures
# =============================================================================


@pytest.fixture
def sample_session_create_experiment() -> SessionCreateRequest:
    """Create a sample session request for experiment agent."""
    return SessionCreateRequest(
        agent_type=AgentType.EXPERIMENT.value,
        initial_context={"objective": "test backtest"},
    )


@pytest.fixture
def sample_session_create_rag() -> SessionCreateRequest:
    """Create a sample session request for RAG assistant."""
    return SessionCreateRequest(
        agent_type=AgentType.RAG_ASSISTANT.value,
    )


@pytest.fixture
def sample_active_session() -> AgentSession:
    """Create a sample active session for testing."""
    now = datetime.now(UTC)
    session = AgentSession(
        session_id=f"test-{uuid.uuid4().hex}",
        agent_type=AgentType.EXPERIMENT.value,
        status=SessionStatus.ACTIVE.value,
        message_history=[],
        pending_action=None,
        total_tokens_used=0,
        tool_calls_count=0,
        last_activity=now,
        expires_at=now + timedelta(minutes=30),
    )
    # Set timestamp mixin fields manually for unit tests
    session.created_at = now
    session.updated_at = now
    return session


@pytest.fixture
def sample_expired_session() -> AgentSession:
    """Create a sample expired session for testing."""
    now = datetime.now(UTC)
    session = AgentSession(
        session_id=f"test-{uuid.uuid4().hex}",
        agent_type=AgentType.EXPERIMENT.value,
        status=SessionStatus.ACTIVE.value,
        message_history=[],
        pending_action=None,
        total_tokens_used=100,
        tool_calls_count=5,
        last_activity=now - timedelta(hours=1),
        expires_at=now - timedelta(minutes=30),  # Expired
    )
    session.created_at = now - timedelta(hours=2)
    session.updated_at = now - timedelta(hours=1)
    return session


@pytest.fixture
def sample_awaiting_approval_session() -> AgentSession:
    """Create a sample session awaiting approval."""
    now = datetime.now(UTC)
    session = AgentSession(
        session_id=f"test-{uuid.uuid4().hex}",
        agent_type=AgentType.EXPERIMENT.value,
        status=SessionStatus.AWAITING_APPROVAL.value,
        message_history=[{"role": "user", "content": "Run experiment"}],
        pending_action={
            "action_id": "action123",
            "action_type": "create_alias",
            "description": "Create production alias",
            "arguments": {"alias_name": "production", "run_id": "abc123"},
            "created_at": now.isoformat(),
            "expires_at": (now + timedelta(minutes=5)).isoformat(),
        },
        total_tokens_used=500,
        tool_calls_count=3,
        last_activity=now,
        expires_at=now + timedelta(minutes=30),
    )
    session.created_at = now - timedelta(minutes=10)
    session.updated_at = now
    return session


@pytest.fixture
def sample_chat_request() -> ChatRequest:
    """Create a sample chat request."""
    return ChatRequest(
        message="Run a backtest for store 1, product 10",
    )


# =============================================================================
# Agent Deps Fixtures
# =============================================================================


@pytest.fixture
def mock_db_session() -> AsyncMock:
    """Create a mock database session."""
    return AsyncMock(spec=AsyncSession)


@pytest.fixture
def sample_agent_deps(mock_db_session: AsyncMock) -> AgentDeps:
    """Create sample agent dependencies."""
    return AgentDeps(
        db=mock_db_session,
        session_id="test-session-123",
        request_id="req-456",
    )


# =============================================================================
# Agent Output Fixtures
# =============================================================================


@pytest.fixture
def sample_experiment_report() -> ExperimentReport:
    """Create a sample experiment report."""
    return ExperimentReport(
        run_id="run123",
        status="success",
        summary="Experiment completed successfully. Best model: seasonal_naive",
        metrics={"mae": 8.9, "smape": 12.5},
        recommendations=["Deploy seasonal_naive model", "Monitor for 1 week"],
    )


@pytest.fixture
def sample_rag_answer() -> RAGAnswer:
    """Create a sample RAG answer."""
    return RAGAnswer(
        answer="The forecast API supports naive and seasonal_naive models.",
        confidence="high",
        sources=[
            {
                "source_path": "docs/api.md",
                "relevance": 0.92,
            }
        ],
    )


# =============================================================================
# Mock Agent Fixtures
# =============================================================================


@pytest.fixture
def mock_experiment_agent() -> MagicMock:
    """Create a mock experiment agent."""
    agent = MagicMock()

    # Mock run method
    mock_result = MagicMock()
    mock_result.data = ExperimentReport(
        run_id="run123",
        status="success",
        summary="Test completed",
        metrics={"mae": 10.5},
        recommendations=["Use naive model"],
    )
    mock_usage = MagicMock()
    mock_usage.total_tokens = 100
    mock_result.usage.return_value = mock_usage
    mock_result.all_messages.return_value = []

    agent.run = AsyncMock(return_value=mock_result)

    return agent


@pytest.fixture
def mock_rag_agent() -> MagicMock:
    """Create a mock RAG assistant agent."""
    agent = MagicMock()

    mock_result = MagicMock()
    mock_result.data = RAGAnswer(
        answer="Test answer based on evidence.",
        confidence="high",
        sources=[],
    )
    mock_usage = MagicMock()
    mock_usage.total_tokens = 50
    mock_result.usage.return_value = mock_usage
    mock_result.all_messages.return_value = []

    agent.run = AsyncMock(return_value=mock_result)

    return agent


# =============================================================================
# Service Fixtures
# =============================================================================


@pytest.fixture
def agent_service() -> AgentService:
    """Create an agent service instance."""
    return AgentService()


@pytest.fixture
def mock_agent_service(mock_experiment_agent: MagicMock, mock_rag_agent: MagicMock) -> AgentService:
    """Create an agent service with mocked agents."""
    service = AgentService()

    # Patch the agent getters
    def mock_get_agent(agent_type: str) -> Any:
        if agent_type == AgentType.EXPERIMENT.value:
            return mock_experiment_agent
        elif agent_type == AgentType.RAG_ASSISTANT.value:
            return mock_rag_agent
        else:
            raise ValueError(f"Unknown agent type: {agent_type}")

    service._get_agent = mock_get_agent  # type: ignore[method-assign]

    return service


# =============================================================================
# Tool Result Fixtures
# =============================================================================


@pytest.fixture
def sample_list_runs_result() -> dict[str, Any]:
    """Sample result from list_runs tool."""
    return {
        "runs": [
            {
                "run_id": "abc123",
                "model_type": "naive",
                "status": "success",
                "metrics": {"mae": 10.5},
            },
            {
                "run_id": "def456",
                "model_type": "seasonal_naive",
                "status": "success",
                "metrics": {"mae": 8.9},
            },
        ],
        "total": 2,
        "page": 1,
        "page_size": 20,
    }


@pytest.fixture
def sample_backtest_result() -> dict[str, Any]:
    """Sample result from run_backtest tool."""
    return {
        "run_id": "backtest123",
        "model_type": "naive",
        "n_splits": 5,
        "aggregated_metrics": {
            "mae_mean": 10.5,
            "mae_std": 1.2,
            "smape_mean": 15.3,
            "smape_std": 2.1,
        },
        "fold_metrics": [
            {"fold": 0, "mae": 10.2, "smape": 14.8},
            {"fold": 1, "mae": 10.8, "smape": 15.5},
        ],
        "status": "success",
    }


@pytest.fixture
def sample_retrieval_result() -> dict[str, Any]:
    """Sample result from retrieve_context tool."""
    return {
        "results": [
            {
                "chunk_id": "chunk-1",
                "source_path": "docs/api.md",
                "source_type": "markdown",
                "content": "The forecast endpoint accepts model_type...",
                "similarity": 0.92,
            },
            {
                "chunk_id": "chunk-2",
                "source_path": "docs/models.md",
                "source_type": "markdown",
                "content": "Available models include naive, seasonal_naive...",
                "similarity": 0.88,
            },
        ],
        "query": "forecast API models",
        "total_results": 2,
    }
