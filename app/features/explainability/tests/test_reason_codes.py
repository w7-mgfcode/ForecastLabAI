"""Unit tests for the advisory reason-code engine."""

from __future__ import annotations

from datetime import date

from app.features.explainability.reason_codes import (
    CORRELATION_CAVEAT,
    build_caveats,
    history_reason,
    holiday_reason,
    lifecycle_reason,
    promotion_reason,
    stockout_reason,
)
from app.features.explainability.schemas import ReasonCode

AS_OF = date(2024, 3, 1)


class TestStockoutReason:
    """Tests for stockout_reason."""

    def test_fires_on_stockout_days(self) -> None:
        """A stockout day produces a warn-level reason code."""
        code = stockout_reason([False, True, False, True])
        assert code is not None
        assert code.code == "stockout_constrained"
        assert code.severity == "warn"
        assert "2 stockout" in code.detail

    def test_none_when_no_stockout(self) -> None:
        """No stockout days yields None."""
        assert stockout_reason([False, False, False]) is None

    def test_none_for_empty_window(self) -> None:
        """An empty window yields None."""
        assert stockout_reason([]) is None


class TestPromotionReason:
    """Tests for promotion_reason."""

    def test_fires_on_overlap(self) -> None:
        """An overlapping promotion produces an info reason code."""
        code = promotion_reason([(date(2024, 2, 20), date(2024, 2, 25))], AS_OF)
        assert code is not None
        assert code.code == "promotion_overlap"
        assert code.severity == "info"

    def test_detects_promotion_active_at_cutoff(self) -> None:
        """A promotion active on as_of_date is called out in the detail."""
        code = promotion_reason([(date(2024, 2, 25), date(2024, 3, 10))], AS_OF)
        assert code is not None
        assert "still active" in code.detail

    def test_none_when_no_promotions(self) -> None:
        """No promotions yields None."""
        assert promotion_reason([], AS_OF) is None


class TestLifecycleReason:
    """Tests for lifecycle_reason."""

    def test_fires_for_recent_launch(self) -> None:
        """A launch under 30 days ago produces an info reason code."""
        code = lifecycle_reason(date(2024, 2, 15), AS_OF)
        assert code is not None
        assert code.code == "lifecycle_decay"

    def test_none_for_old_launch(self) -> None:
        """A launch over 30 days ago yields None."""
        assert lifecycle_reason(date(2023, 1, 1), AS_OF) is None

    def test_none_when_launch_unknown(self) -> None:
        """An unknown launch date yields None."""
        assert lifecycle_reason(None, AS_OF) is None


class TestHolidayReason:
    """Tests for holiday_reason."""

    def test_fires_on_holiday(self) -> None:
        """A holiday forecast date produces an info reason code."""
        code = holiday_reason(True, "New Year", date(2024, 3, 2))
        assert code is not None
        assert code.code == "holiday_effect"
        assert "New Year" in code.detail

    def test_none_on_normal_day(self) -> None:
        """A non-holiday forecast date yields None."""
        assert holiday_reason(False, None, date(2024, 3, 2)) is None


class TestHistoryReason:
    """Tests for history_reason."""

    def test_fires_for_short_series(self) -> None:
        """Fewer observations than required produces a warn reason code."""
        code = history_reason(5, 14)
        assert code is not None
        assert code.code == "insufficient_history"
        assert code.severity == "warn"

    def test_none_for_sufficient_history(self) -> None:
        """Enough observations yields None."""
        assert history_reason(30, 14) is None


class TestBuildCaveats:
    """Tests for build_caveats."""

    def test_always_includes_correlation_caveat(self) -> None:
        """Every caveat list starts with the correlation-vs-causation disclaimer."""
        caveats = build_caveats("naive", [])
        assert caveats[0] == CORRELATION_CAVEAT

    def test_includes_model_specific_caveat(self) -> None:
        """A model-specific caveat is appended for each baseline."""
        assert any("seasonality" in c for c in build_caveats("naive", []))
        assert any("prior cycle" in c for c in build_caveats("seasonal_naive", []))
        assert any("smooths" in c for c in build_caveats("moving_average", []))

    def test_adds_stockout_caveat(self) -> None:
        """A stockout reason code adds an understated-demand caveat."""
        stockout = ReasonCode(code="stockout_constrained", severity="warn", detail="x")
        caveats = build_caveats("naive", [stockout])
        assert any("understate" in c for c in caveats)
