"""Unit tests for scripts/run_demo.py.

These tests are pure-Python and never touch the network or the database
— the HttpClient is mocked at the boundary. Integration coverage lives
in `tests/test_e2e_demo.py` (marked `@pytest.mark.integration`).
"""

from __future__ import annotations

import math
from typing import Any
from unittest.mock import AsyncMock

import pytest

from scripts import run_demo
from scripts.run_demo import (
    DEMO_ALIAS,
    DEMO_HORIZON,
    DEMO_MODEL_TYPES,
    GLYPHS,
    DemoArgs,
    DemoContext,
    HttpClient,
    Reporter,
    StepError,
    StepOutcome,
    _llm_key_present,
    _model_config_payload,
    _select_winner,
    parse_args,
)

# =============================================================================
# parse_args
# =============================================================================


class TestParseArgs:
    def test_defaults(self) -> None:
        args = parse_args([])
        assert isinstance(args, DemoArgs)
        assert args.seed == 42
        assert args.skip_seed is False
        assert args.reset is False
        assert args.quiet is False
        assert args.api_url == "http://localhost:8123"
        assert args.timeout == pytest.approx(120.0)

    def test_all_flags(self) -> None:
        args = parse_args(
            [
                "--seed",
                "7",
                "--skip-seed",
                "--reset",
                "--quiet",
                "--api-url",
                "http://127.0.0.1:8124",
                "--timeout",
                "12.5",
            ]
        )
        assert args.seed == 7
        assert args.skip_seed is True
        assert args.reset is True
        assert args.quiet is True
        assert args.api_url == "http://127.0.0.1:8124"
        assert args.timeout == pytest.approx(12.5)


# =============================================================================
# DemoContext
# =============================================================================


class TestDemoContext:
    def test_defaults(self) -> None:
        ctx = DemoContext(
            api_url="http://x",
            seed=1,
            skip_seed=False,
            reset=False,
            quiet=False,
            timeout=10.0,
        )
        assert ctx.store_id == 1
        assert ctx.product_id == 1
        assert ctx.date_start is None
        assert ctx.date_end is None
        assert ctx.seed_records == {}
        assert ctx.train_results == {}
        assert ctx.backtest_results == {}
        assert ctx.winner_model_type is None
        assert ctx.winner_wape is None
        assert ctx.winning_run_id is None
        assert ctx.session_id is None


# =============================================================================
# _select_winner
# =============================================================================


class TestSelectWinner:
    def test_picks_lowest_wape(self) -> None:
        results = {
            "naive": {"wape": 0.30, "mae": 5.0},
            "seasonal_naive": {"wape": 0.18, "mae": 3.5},
            "moving_average": {"wape": 0.22, "mae": 4.0},
        }
        winner = _select_winner(results)
        assert winner == ("seasonal_naive", 0.18)

    def test_skips_nan(self) -> None:
        results = {
            "naive": {"wape": float("nan")},
            "seasonal_naive": {"wape": 0.18},
        }
        winner = _select_winner(results)
        assert winner == ("seasonal_naive", 0.18)

    def test_all_nan_returns_none(self) -> None:
        results = {
            "naive": {"wape": float("nan")},
            "moving_average": {"wape": float("nan")},
        }
        assert _select_winner(results) is None

    def test_empty_returns_none(self) -> None:
        assert _select_winner({}) is None

    def test_missing_wape_field(self) -> None:
        results: dict[str, dict[str, float]] = {
            "naive": {},
            "seasonal_naive": {"wape": 0.42},
        }
        winner = _select_winner(results)
        assert winner == ("seasonal_naive", 0.42)


# =============================================================================
# _model_config_payload
# =============================================================================


class TestModelConfigPayload:
    def test_naive_shape(self) -> None:
        assert _model_config_payload("naive") == {"model_type": "naive"}

    def test_seasonal_naive_shape(self) -> None:
        assert _model_config_payload("seasonal_naive") == {
            "model_type": "seasonal_naive",
            "season_length": 7,
        }

    def test_moving_average_shape(self) -> None:
        assert _model_config_payload("moving_average") == {
            "model_type": "moving_average",
            "window_size": 7,
        }

    def test_unsupported_model_type_raises(self) -> None:
        with pytest.raises(ValueError, match="Unsupported demo model_type"):
            _model_config_payload("lightgbm")


# =============================================================================
# Reporter
# =============================================================================


class TestReporter:
    def test_glyph_mapping(self) -> None:
        # The five status values that StepOutcome.status can take must all
        # have a glyph; the reporter falls back to "?" otherwise but the
        # status taxonomy is closed here.
        assert GLYPHS["pass"] == "✅"  # noqa: S105 — false positive: GLYPHS["pass"] is a status glyph
        assert GLYPHS["fail"] == "❌"
        assert GLYPHS["warn"] == "⚠️"
        assert GLYPHS["skip"] == "⏭️"
        assert "run" in GLYPHS

    def test_verbose_emits_step_lines(self, capsys: pytest.CaptureFixture[str]) -> None:
        reporter = Reporter(quiet=False, total_steps=2)
        reporter.header()
        reporter.record(StepOutcome(name="precheck", status="pass", detail="ok", duration_ms=12.3))
        reporter.record(
            StepOutcome(name="seed", status="skip", detail="--skip-seed", duration_ms=0.5)
        )
        out = capsys.readouterr().out
        assert "ForecastLabAI Demo" in out
        assert "✅" in out
        assert "⏭️" in out
        assert "Step  1/2" in out
        assert "Step  2/2" in out

    def test_quiet_skips_banner(self, capsys: pytest.CaptureFixture[str]) -> None:
        reporter = Reporter(quiet=True, total_steps=1)
        reporter.header()
        reporter.record(StepOutcome(name="precheck", status="pass", detail="ok", duration_ms=1.0))
        out = capsys.readouterr().out
        assert "ForecastLabAI Demo" not in out
        assert "✅" in out  # glyph still emitted in quiet mode
        assert "precheck: ok" in out

    def test_summary_green(self, capsys: pytest.CaptureFixture[str]) -> None:
        ctx = DemoContext(
            api_url="x", seed=42, skip_seed=False, reset=False, quiet=False, timeout=10.0
        )
        ctx.winner_model_type = "seasonal_naive"
        ctx.backtest_results = {"naive": {}, "seasonal_naive": {}, "moving_average": {}}
        reporter = Reporter(quiet=False, total_steps=3)
        green = reporter.summary(
            [
                StepOutcome(name="a", status="pass", detail="", duration_ms=1),
                StepOutcome(name="b", status="pass", detail="", duration_ms=1),
            ],
            ctx,
            wall_clock_s=42.0,
        )
        out = capsys.readouterr().out
        assert green is True
        assert "Result: GREEN" in out
        assert "runs=3 winner=seasonal_naive" in out
        assert f"alias={DEMO_ALIAS}" in out
        assert "wall_clock=42s" in out

    def test_summary_failure(self, capsys: pytest.CaptureFixture[str]) -> None:
        ctx = DemoContext(
            api_url="x", seed=42, skip_seed=False, reset=False, quiet=False, timeout=10.0
        )
        reporter = Reporter(quiet=False, total_steps=2)
        green = reporter.summary(
            [
                StepOutcome(name="a", status="fail", detail="boom", duration_ms=1),
            ],
            ctx,
            wall_clock_s=10.0,
        )
        out = capsys.readouterr().out
        assert green is False
        assert "NOT READY" in out
        assert "1 step(s) failed" in out
        assert "winner=n/a" in out

    def test_summary_over_budget_soft_warns(self, capsys: pytest.CaptureFixture[str]) -> None:
        ctx = DemoContext(
            api_url="x", seed=42, skip_seed=False, reset=False, quiet=False, timeout=10.0
        )
        ctx.winner_model_type = "naive"
        ctx.backtest_results = {"naive": {}}
        reporter = Reporter(quiet=False, total_steps=1)
        green = reporter.summary(
            [
                StepOutcome(name="a", status="pass", detail="", duration_ms=1),
            ],
            ctx,
            wall_clock_s=999.0,
        )
        out = capsys.readouterr().out
        assert green is True
        assert "GREEN" in out
        assert "over budget" in out


# =============================================================================
# StepError formatting
# =============================================================================


class TestStepError:
    def test_format_includes_request_id(self) -> None:
        err = StepError(
            step="seed",
            status_code=500,
            problem={
                "title": "Internal Server Error",
                "detail": "boom",
                "request_id": "req-xyz",
            },
        )
        text = str(err)
        assert "HTTP 500" in text
        assert "Internal Server Error" in text
        assert "boom" in text
        assert "request_id=req-xyz" in text


# =============================================================================
# HttpClient — mocked
# =============================================================================


class TestHttpClientMocked:
    @pytest.mark.asyncio
    async def test_2xx_returns_body(self) -> None:
        client = HttpClient("http://test", timeout=5.0)
        # Patch the internal httpx client so no real network call is made.
        mock_response = AsyncMock()
        mock_response.status_code = 200
        mock_response.json = lambda: {"status": "ok"}
        client._client.request = AsyncMock(return_value=mock_response)  # type: ignore[method-assign]
        body = await client.request("precheck", "GET", "/health")
        assert body == {"status": "ok"}

    @pytest.mark.asyncio
    async def test_204_returns_empty_dict(self) -> None:
        client = HttpClient("http://test", timeout=5.0)
        mock_response = AsyncMock()
        mock_response.status_code = 204
        client._client.request = AsyncMock(return_value=mock_response)  # type: ignore[method-assign]
        body = await client.request("delete", "DELETE", "/x")
        assert body == {}

    @pytest.mark.asyncio
    async def test_non_2xx_raises_steperror_with_problem(self) -> None:
        client = HttpClient("http://test", timeout=5.0)
        mock_response = AsyncMock()
        mock_response.status_code = 400
        mock_response.json = lambda: {
            "title": "Validation Error",
            "detail": "bad payload",
            "request_id": "abc",
        }
        client._client.request = AsyncMock(return_value=mock_response)  # type: ignore[method-assign]
        with pytest.raises(StepError) as excinfo:
            await client.request("seed", "POST", "/seeder/generate", json_body={"x": 1})
        err = excinfo.value
        assert err.status_code == 400
        assert err.problem["detail"] == "bad payload"


# =============================================================================
# Step payload shapes (sanity check that we send what the API expects)
# =============================================================================


class TestStepPayloads:
    @pytest.mark.asyncio
    async def test_step_seed_sends_demo_minimal(
        self,
    ) -> None:
        """Seed step posts demo_minimal scenario with correct dims + dates."""
        calls: list[dict[str, Any]] = []

        class _RecordingClient:
            async def request(
                self,
                step: str,
                method: str,
                path: str,
                *,
                json_body: dict[str, Any] | None = None,
            ) -> dict[str, Any]:
                calls.append({"step": step, "method": method, "path": path, "json_body": json_body})
                return {"records_created": {"sales_daily": 100}}

        ctx = DemoContext(
            api_url="x",
            seed=42,
            skip_seed=False,
            reset=False,
            quiet=False,
            timeout=10.0,
        )
        outcome = await run_demo.step_seed(ctx, _RecordingClient())  # type: ignore[arg-type]
        assert outcome.status == "pass"
        assert len(calls) == 1
        body = calls[0]["json_body"]
        assert calls[0]["path"] == "/seeder/generate"
        assert body is not None
        assert body["scenario"] == "demo_minimal"
        assert body["seed"] == 42
        assert body["stores"] == 3
        assert body["products"] == 10
        assert body["start_date"] == "2024-10-01"
        assert body["end_date"] == "2024-12-31"

    @pytest.mark.asyncio
    async def test_step_seed_skipped(self) -> None:
        """When --skip-seed is set, no HTTP call is made."""
        called = False

        class _AssertNotCalled:
            async def request(self, *args: Any, **kwargs: Any) -> dict[str, Any]:
                nonlocal called
                called = True
                return {}

        ctx = DemoContext(
            api_url="x",
            seed=42,
            skip_seed=True,
            reset=False,
            quiet=False,
            timeout=10.0,
        )
        outcome = await run_demo.step_seed(ctx, _AssertNotCalled())  # type: ignore[arg-type]
        assert outcome.status == "skip"
        assert called is False

    @pytest.mark.asyncio
    async def test_step_reset_no_op_without_flag(self) -> None:
        called = False

        class _AssertNotCalled:
            async def request(self, *args: Any, **kwargs: Any) -> dict[str, Any]:
                nonlocal called
                called = True
                return {}

        ctx = DemoContext(
            api_url="x",
            seed=42,
            skip_seed=False,
            reset=False,
            quiet=False,
            timeout=10.0,
        )
        outcome = await run_demo.step_reset(ctx, _AssertNotCalled())  # type: ignore[arg-type]
        assert outcome.status == "skip"
        assert called is False

    @pytest.mark.asyncio
    async def test_step_features_sends_cutoff_iso(self) -> None:
        from datetime import date as _date

        calls: list[dict[str, Any]] = []

        class _RecordingClient:
            async def request(
                self,
                step: str,
                method: str,
                path: str,
                *,
                json_body: dict[str, Any] | None = None,
            ) -> dict[str, Any]:
                calls.append({"path": path, "json_body": json_body})
                return {"row_count": 30, "feature_columns": ["a", "b", "c"]}

        ctx = DemoContext(
            api_url="x",
            seed=42,
            skip_seed=False,
            reset=False,
            quiet=False,
            timeout=10.0,
        )
        ctx.date_end = _date(2024, 12, 31)
        outcome = await run_demo.step_features(ctx, _RecordingClient())  # type: ignore[arg-type]
        assert outcome.status == "pass"
        body = calls[0]["json_body"]
        assert body["cutoff_date"] == "2024-12-31"
        assert body["store_id"] == 1
        assert body["product_id"] == 1

    @pytest.mark.asyncio
    async def test_step_train_all_sends_three_in_parallel(self) -> None:
        from datetime import date as _date

        seen_models: list[str] = []

        class _RecordingClient:
            async def request(
                self,
                step: str,
                method: str,
                path: str,
                *,
                json_body: dict[str, Any] | None = None,
            ) -> dict[str, Any]:
                assert json_body is not None
                assert path == "/forecasting/train"
                seen_models.append(json_body["config"]["model_type"])
                return {"model_path": f"/tmp/{json_body['config']['model_type']}.pkl"}  # noqa: S108

        ctx = DemoContext(
            api_url="x",
            seed=42,
            skip_seed=False,
            reset=False,
            quiet=False,
            timeout=10.0,
        )
        ctx.date_start = _date(2024, 10, 1)
        ctx.date_end = _date(2024, 12, 31)
        outcome = await run_demo.step_train_all(ctx, _RecordingClient())  # type: ignore[arg-type]
        assert outcome.status == "pass"
        assert set(seen_models) == set(DEMO_MODEL_TYPES)
        # train_end_date should be horizon-padded so backtest has room.
        # End - horizon = 2024-12-17.

    @pytest.mark.asyncio
    async def test_step_agent_skips_without_keys(self, monkeypatch: pytest.MonkeyPatch) -> None:
        # Force the module-level Settings to report no keys.
        monkeypatch.setattr(run_demo, "_llm_key_present", lambda: False)

        called = False

        class _AssertNotCalled:
            async def request(self, *args: Any, **kwargs: Any) -> dict[str, Any]:
                nonlocal called
                called = True
                return {}

        ctx = DemoContext(
            api_url="x",
            seed=42,
            skip_seed=False,
            reset=False,
            quiet=False,
            timeout=10.0,
        )
        outcome = await run_demo.step_agent(ctx, _AssertNotCalled())  # type: ignore[arg-type]
        assert outcome.status == "skip"
        assert called is False


# =============================================================================
# _llm_key_present (sanity — only checks the API is wired, not actual values)
# =============================================================================


class TestLlmKeyPresent:
    def test_returns_bool(self) -> None:
        # Whatever the actual env is, the function must return a bool.
        result = _llm_key_present()
        assert isinstance(result, bool)


# =============================================================================
# Module-level constants sanity
# =============================================================================


class TestModuleConstants:
    def test_demo_model_types_count(self) -> None:
        assert len(DEMO_MODEL_TYPES) == 3
        assert set(DEMO_MODEL_TYPES) == {"naive", "seasonal_naive", "moving_average"}

    def test_demo_alias_format(self) -> None:
        # Must match the registry alias_name pattern ^[a-z0-9][a-z0-9\-_]*$.
        assert DEMO_ALIAS == "demo-production"
        assert DEMO_ALIAS[0].isalnum()

    def test_horizon_positive(self) -> None:
        assert DEMO_HORIZON >= 1
        assert not math.isnan(DEMO_HORIZON)
