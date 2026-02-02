"""Integration tests for agent routes.

Requires PostgreSQL to be running (docker-compose up -d).
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import AsyncClient

from app.features.agents.schemas import ExperimentReport


@pytest.mark.integration
class TestSessionRoutes:
    """Integration tests for session management routes."""

    @pytest.mark.asyncio
    async def test_create_experiment_session(self, client: AsyncClient) -> None:
        """Should create experiment session."""
        with patch("app.features.agents.agents.experiment.get_experiment_agent") as mock_get:
            mock_get.return_value = MagicMock()

            response = await client.post(
                "/agents/sessions",
                json={"agent_type": "experiment"},
            )

        assert response.status_code == 201
        data = response.json()
        assert data["agent_type"] == "experiment"
        assert data["status"] == "active"
        assert "session_id" in data
        assert len(data["session_id"]) == 32

    @pytest.mark.asyncio
    async def test_create_rag_session(self, client: AsyncClient) -> None:
        """Should create RAG assistant session."""
        with patch("app.features.agents.agents.rag_assistant.get_rag_assistant_agent") as mock_get:
            mock_get.return_value = MagicMock()

            response = await client.post(
                "/agents/sessions",
                json={"agent_type": "rag_assistant"},
            )

        assert response.status_code == 201
        data = response.json()
        assert data["agent_type"] == "rag_assistant"

    @pytest.mark.asyncio
    async def test_create_session_invalid_type(self, client: AsyncClient) -> None:
        """Should reject invalid agent type."""
        response = await client.post(
            "/agents/sessions",
            json={"agent_type": "invalid_type"},
        )

        assert response.status_code == 422  # Pydantic validation error

    @pytest.mark.asyncio
    async def test_get_session(self, client: AsyncClient) -> None:
        """Should get existing session."""
        # Create session first
        with patch("app.features.agents.agents.experiment.get_experiment_agent") as mock_get:
            mock_get.return_value = MagicMock()

            create_response = await client.post(
                "/agents/sessions",
                json={"agent_type": "experiment"},
            )

        session_id = create_response.json()["session_id"]

        # Get session
        response = await client.get(f"/agents/sessions/{session_id}")

        assert response.status_code == 200
        data = response.json()
        assert data["session_id"] == session_id

    @pytest.mark.asyncio
    async def test_get_session_not_found(self, client: AsyncClient) -> None:
        """Should return 404 for nonexistent session."""
        response = await client.get("/agents/sessions/nonexistent123")

        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_close_session(self, client: AsyncClient) -> None:
        """Should close session."""
        # Create session first
        with patch("app.features.agents.agents.experiment.get_experiment_agent") as mock_get:
            mock_get.return_value = MagicMock()

            create_response = await client.post(
                "/agents/sessions",
                json={"agent_type": "experiment"},
            )

        session_id = create_response.json()["session_id"]

        # Close session
        response = await client.delete(f"/agents/sessions/{session_id}")

        assert response.status_code == 204

        # Verify it's closed
        get_response = await client.get(f"/agents/sessions/{session_id}")
        assert get_response.json()["status"] == "closed"


@pytest.mark.integration
class TestChatRoutes:
    """Integration tests for chat routes."""

    @pytest.mark.asyncio
    async def test_chat_success(self, client: AsyncClient) -> None:
        """Should process chat message."""
        # Create session
        with patch("app.features.agents.agents.experiment.get_experiment_agent") as mock_get:
            mock_agent = MagicMock()
            mock_result = MagicMock()
            mock_result.output = ExperimentReport(
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
            mock_agent.run = AsyncMock(return_value=mock_result)
            mock_get.return_value = mock_agent

            create_response = await client.post(
                "/agents/sessions",
                json={"agent_type": "experiment"},
            )
            session_id = create_response.json()["session_id"]

            # Send chat
            response = await client.post(
                f"/agents/sessions/{session_id}/chat",
                json={"message": "Run a backtest"},
            )

        assert response.status_code == 200
        data = response.json()
        assert data["session_id"] == session_id
        assert "message" in data

    @pytest.mark.asyncio
    async def test_chat_session_not_found(self, client: AsyncClient) -> None:
        """Should return 404 for nonexistent session."""
        response = await client.post(
            "/agents/sessions/nonexistent123/chat",
            json={"message": "Hello"},
        )

        assert response.status_code == 404


@pytest.mark.integration
class TestApprovalRoutes:
    """Integration tests for approval routes."""

    @pytest.mark.asyncio
    async def test_approve_action_no_pending(self, client: AsyncClient) -> None:
        """Should return 400 when no pending action."""
        # Create session
        with patch("app.features.agents.agents.experiment.get_experiment_agent") as mock_get:
            mock_get.return_value = MagicMock()

            create_response = await client.post(
                "/agents/sessions",
                json={"agent_type": "experiment"},
            )

        session_id = create_response.json()["session_id"]

        # Try to approve
        response = await client.post(
            f"/agents/sessions/{session_id}/approve",
            json={"action_id": "act123", "approved": True},
        )

        assert response.status_code == 400

    @pytest.mark.asyncio
    async def test_approve_session_not_found(self, client: AsyncClient) -> None:
        """Should return 404 for nonexistent session."""
        response = await client.post(
            "/agents/sessions/nonexistent123/approve",
            json={"action_id": "act123", "approved": True},
        )

        assert response.status_code == 404


@pytest.mark.integration
class TestHealthCheck:
    """Integration tests for health check compatibility."""

    @pytest.mark.asyncio
    async def test_health_with_agents(self, client: AsyncClient) -> None:
        """Health check should work with agents feature loaded."""
        response = await client.get("/health")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"
