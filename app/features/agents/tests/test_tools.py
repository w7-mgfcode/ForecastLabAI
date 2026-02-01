"""Unit tests for agent tools."""

from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.features.agents.tools.backtesting_tools import compare_backtest_results
from app.features.agents.tools.rag_tools import (
    format_citations,
    has_sufficient_evidence,
)
from app.features.agents.tools.registry_tools import (
    archive_run,
    compare_runs,
    create_alias,
    get_run,
    list_runs,
)


class TestRegistryTools:
    """Tests for registry tool functions."""

    @pytest.mark.asyncio
    async def test_list_runs_calls_service(self) -> None:
        """Should call registry service list_runs."""
        mock_db = AsyncMock()

        with patch("app.features.agents.tools.registry_tools.RegistryService") as MockService:
            mock_service = MagicMock()
            mock_result = MagicMock()
            mock_result.model_dump.return_value = {
                "runs": [],
                "total": 0,
                "page": 1,
                "page_size": 20,
            }
            mock_service.list_runs = AsyncMock(return_value=mock_result)
            MockService.return_value = mock_service

            result = await list_runs(
                db=mock_db,
                page=1,
                page_size=20,
                model_type="naive",
            )

            assert result["total"] == 0
            mock_service.list_runs.assert_called_once()

    @pytest.mark.asyncio
    async def test_list_runs_caps_page_size(self) -> None:
        """Should cap page_size at 100."""
        mock_db = AsyncMock()

        with patch("app.features.agents.tools.registry_tools.RegistryService") as MockService:
            mock_service = MagicMock()
            mock_result = MagicMock()
            mock_result.model_dump.return_value = {"runs": [], "page_size": 100}
            mock_service.list_runs = AsyncMock(return_value=mock_result)
            MockService.return_value = mock_service

            await list_runs(
                db=mock_db,
                page_size=200,  # Request more than limit
            )

            # Should have been capped to 100
            call_kwargs = mock_service.list_runs.call_args.kwargs
            assert call_kwargs["page_size"] == 100

    @pytest.mark.asyncio
    async def test_get_run_found(self) -> None:
        """Should return run when found."""
        mock_db = AsyncMock()

        with patch("app.features.agents.tools.registry_tools.RegistryService") as MockService:
            mock_service = MagicMock()
            mock_result = MagicMock()
            mock_result.model_dump.return_value = {
                "run_id": "abc123",
                "model_type": "naive",
            }
            mock_service.get_run = AsyncMock(return_value=mock_result)
            MockService.return_value = mock_service

            result = await get_run(db=mock_db, run_id="abc123")

            assert result is not None
            assert result["run_id"] == "abc123"

    @pytest.mark.asyncio
    async def test_get_run_not_found(self) -> None:
        """Should return None when not found."""
        mock_db = AsyncMock()

        with patch("app.features.agents.tools.registry_tools.RegistryService") as MockService:
            mock_service = MagicMock()
            mock_service.get_run = AsyncMock(return_value=None)
            MockService.return_value = mock_service

            result = await get_run(db=mock_db, run_id="nonexistent")

            assert result is None

    @pytest.mark.asyncio
    async def test_compare_runs_success(self) -> None:
        """Should compare two runs."""
        mock_db = AsyncMock()

        with patch("app.features.agents.tools.registry_tools.RegistryService") as MockService:
            mock_service = MagicMock()
            mock_result = MagicMock()
            mock_result.model_dump.return_value = {
                "run_a": {"run_id": "a"},
                "run_b": {"run_id": "b"},
                "config_diff": {},
                "metrics_diff": {"mae": -1.5},
            }
            mock_service.compare_runs = AsyncMock(return_value=mock_result)
            MockService.return_value = mock_service

            result = await compare_runs(
                db=mock_db,
                run_id_a="a",
                run_id_b="b",
            )

            assert result is not None
            assert "metrics_diff" in result

    @pytest.mark.asyncio
    async def test_create_alias_success(self) -> None:
        """Should create alias."""
        mock_db = AsyncMock()

        with patch("app.features.agents.tools.registry_tools.RegistryService") as MockService:
            mock_service = MagicMock()
            mock_result = MagicMock()
            mock_result.model_dump.return_value = {
                "alias_name": "production",
                "run_id": "abc123",
            }
            mock_service.create_alias = AsyncMock(return_value=mock_result)
            MockService.return_value = mock_service

            result = await create_alias(
                db=mock_db,
                alias_name="production",
                run_id="abc123",
            )

            assert result["alias_name"] == "production"

    @pytest.mark.asyncio
    async def test_archive_run_success(self) -> None:
        """Should archive run."""
        mock_db = AsyncMock()

        with patch("app.features.agents.tools.registry_tools.RegistryService") as MockService:
            mock_service = MagicMock()
            mock_result = MagicMock()
            mock_result.model_dump.return_value = {
                "run_id": "abc123",
                "status": "archived",
            }
            mock_service.update_run = AsyncMock(return_value=mock_result)
            MockService.return_value = mock_service

            result = await archive_run(db=mock_db, run_id="abc123")

            assert result is not None
            assert result["status"] == "archived"


class TestBacktestingTools:
    """Tests for backtesting tool functions."""

    def test_compare_backtest_results_better(self) -> None:
        """Should identify better model."""
        # Use actual backtest response structure
        result_a = {
            "backtest_id": "bt-a",
            "main_model_results": {
                "model_type": "naive",
                "aggregated_metrics": {"mae": 12.0, "smape": 18.0},
            },
        }
        result_b = {
            "backtest_id": "bt-b",
            "main_model_results": {
                "model_type": "seasonal_naive",
                "aggregated_metrics": {"mae": 10.0, "smape": 15.0},
            },
        }

        comparison = compare_backtest_results(result_a, result_b)

        # The comparison returns metric_comparison with per-metric analysis
        assert "model_a" in comparison
        assert "model_b" in comparison
        assert "metric_comparison" in comparison
        assert "recommendation" in comparison
        # Model B should be better (lower MAE)
        assert "Model B" in comparison["recommendation"]

    def test_compare_backtest_results_worse(self) -> None:
        """Should identify when first model is better."""
        result_a = {
            "backtest_id": "bt-a",
            "main_model_results": {
                "model_type": "naive",
                "aggregated_metrics": {"mae": 8.0, "smape": 12.0},
            },
        }
        result_b = {
            "backtest_id": "bt-b",
            "main_model_results": {
                "model_type": "seasonal_naive",
                "aggregated_metrics": {"mae": 10.0, "smape": 15.0},
            },
        }

        comparison = compare_backtest_results(result_a, result_b)

        # Model A should be better (lower MAE)
        assert "Model A" in comparison["recommendation"]


class TestRAGTools:
    """Tests for RAG tool functions."""

    def test_format_citations_with_results(self) -> None:
        """Should format retrieval results as citations."""
        retrieval_result: dict[str, Any] = {
            "results": [
                {
                    "chunk_id": "chunk-1",
                    "source_path": "docs/api.md",
                    "source_type": "markdown",
                    "content": "The forecast endpoint accepts model_type...",
                    "relevance_score": 0.92,
                },
                {
                    "chunk_id": "chunk-2",
                    "source_path": "docs/models.md",
                    "source_type": "markdown",
                    "content": "Available models include naive, seasonal_naive...",
                    "relevance_score": 0.88,
                },
            ],
            "query": "forecast API models",
            "total_results": 2,
        }
        citations = format_citations(retrieval_result)

        assert len(citations) == 2
        assert citations[0]["source_path"] == "docs/api.md"
        assert citations[0]["chunk_id"] == "chunk-1"

    def test_format_citations_empty(self) -> None:
        """Should handle empty results."""
        citations = format_citations({"results": []})
        assert citations == []

    def test_has_sufficient_evidence_true(self) -> None:
        """Should return True when evidence is sufficient."""
        retrieval_result: dict[str, Any] = {
            "results": [
                {"chunk_id": "c1", "relevance_score": 0.92},
                {"chunk_id": "c2", "relevance_score": 0.88},
            ]
        }
        result = has_sufficient_evidence(
            retrieval_result,
            min_results=1,
            min_relevance=0.7,
        )
        assert result is True

    def test_has_sufficient_evidence_insufficient_results(self) -> None:
        """Should return False when not enough results."""
        result = has_sufficient_evidence(
            {"results": []},
            min_results=1,
        )
        assert result is False

    def test_has_sufficient_evidence_low_relevance(self) -> None:
        """Should return False when relevance too low."""
        retrieval: dict[str, Any] = {
            "results": [
                {"chunk_id": "c1", "relevance_score": 0.5},
                {"chunk_id": "c2", "relevance_score": 0.4},
            ]
        }
        result = has_sufficient_evidence(
            retrieval,
            min_results=1,
            min_relevance=0.7,
        )
        assert result is False
