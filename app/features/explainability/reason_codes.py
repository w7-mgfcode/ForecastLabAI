"""Advisory retail reason-code engine for the explainability slice.

These are PURE functions — they perform no database access and take only
primitive inputs. The service layer runs the time-safe queries and extracts the
primitives; every input below therefore reflects only data the caller already
bounded ``<= as_of_date`` (or, for ``holiday_reason``, the explained horizon
date).

CRITICAL: a reason code is an advisory *correlation* signal, never a causal
claim. ``build_caveats`` always emits the NIST-grounded correlation-vs-causation
disclaimer.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import date as date_type

from app.features.explainability.schemas import ReasonCode


def stockout_reason(stockout_flags: Sequence[bool]) -> ReasonCode | None:
    """Flag stockout-suppressed history in the trailing window.

    Args:
        stockout_flags: One ``is_stockout`` flag per day in the trailing window
            (already bounded ``<= as_of_date`` by the caller).

    Returns:
        A ``stockout_constrained`` warning when any day was a stockout,
        otherwise ``None``.
    """
    stockout_days = sum(1 for flag in stockout_flags if flag)
    if stockout_days == 0:
        return None
    return ReasonCode(
        code="stockout_constrained",
        severity="warn",
        detail=(
            f"{stockout_days} stockout day(s) in the trailing "
            f"{len(stockout_flags)}-day window — observed demand may understate "
            "true demand because units could not be sold while out of stock."
        ),
    )


def promotion_reason(
    promotion_windows: Sequence[tuple[date_type, date_type]], as_of_date: date_type
) -> ReasonCode | None:
    """Flag promotions overlapping the trailing window.

    Args:
        promotion_windows: ``(start_date, end_date)`` tuples for promotions
            overlapping the trailing window (already bounded ``<= as_of_date``).
        as_of_date: The series cutoff date.

    Returns:
        A ``promotion_overlap`` info code when any promotion overlaps,
        otherwise ``None``.
    """
    if not promotion_windows:
        return None
    active_now = sum(1 for start, end in promotion_windows if start <= as_of_date <= end)
    active_clause = f"; {active_now} still active on {as_of_date.isoformat()}" if active_now else ""
    return ReasonCode(
        code="promotion_overlap",
        severity="info",
        detail=(
            f"{len(promotion_windows)} promotion(s) overlap the trailing window"
            f"{active_clause} — promotional demand may not represent the baseline."
        ),
    )


def lifecycle_reason(launch_date: date_type | None, as_of_date: date_type) -> ReasonCode | None:
    """Flag a product still in its early lifecycle.

    Args:
        launch_date: The product's launch date, or ``None`` if unknown.
        as_of_date: The series cutoff date.

    Returns:
        A ``lifecycle_decay`` info code when the product launched fewer than
        30 days before ``as_of_date``, otherwise ``None``.
    """
    if launch_date is None:
        return None
    days_since_launch = (as_of_date - launch_date).days
    if 0 <= days_since_launch < 30:
        return ReasonCode(
            code="lifecycle_decay",
            severity="info",
            detail=(
                f"Product launched {days_since_launch} day(s) ago — early-"
                "lifecycle demand is volatile and may not represent a stable "
                "baseline."
            ),
        )
    return None


def holiday_reason(
    is_holiday: bool, holiday_name: str | None, forecast_date: date_type
) -> ReasonCode | None:
    """Flag a holiday landing on the explained forecast horizon.

    Args:
        is_holiday: Whether ``forecast_date`` is flagged as a holiday.
        holiday_name: The holiday's name, when known.
        forecast_date: The date of the explained h=1 forecast.

    Returns:
        A ``holiday_effect`` info code when ``forecast_date`` is a holiday,
        otherwise ``None``.
    """
    if not is_holiday:
        return None
    name = holiday_name or "a holiday"
    return ReasonCode(
        code="holiday_effect",
        severity="info",
        detail=(
            f"The forecast date {forecast_date.isoformat()} is {name} — "
            "holiday demand typically deviates from a normal day."
        ),
    )


def history_reason(n_obs: int, min_required: int) -> ReasonCode | None:
    """Flag a series too short for a comfortable explanation.

    Args:
        n_obs: Number of observations in the series.
        min_required: Minimum comfortable observation count for the model.

    Returns:
        An ``insufficient_history`` warning when ``n_obs < min_required``,
        otherwise ``None``.
    """
    if n_obs < min_required:
        return ReasonCode(
            code="insufficient_history",
            severity="warn",
            detail=(
                f"Only {n_obs} observation(s) available; {min_required} or more "
                "is recommended for a confident explanation."
            ),
        )
    return None


# The NIST-grounded disclaimer baked into every explanation (see
# https://www.nist.gov/itl/ai-risk-management-framework).
CORRELATION_CAVEAT = (
    "Drivers describe correlation and contribution, not business causality — "
    "they explain the model's arithmetic, not why demand moved."
)

_MODEL_CAVEATS: dict[str, str] = {
    "naive": "The naive model ignores seasonality and trend entirely.",
    "seasonal_naive": "The seasonal-naive model assumes the prior cycle repeats exactly.",
    "moving_average": "The moving-average model smooths over recent shifts in demand.",
}


def build_caveats(model_type: str, reason_codes: Sequence[ReasonCode]) -> list[str]:
    """Assemble the caveat list for an explanation.

    Args:
        model_type: The baseline model type explained.
        reason_codes: The reason codes already computed for the explanation.

    Returns:
        Plain-language caveats, always starting with the correlation-vs-
        causation disclaimer.
    """
    caveats = [CORRELATION_CAVEAT]
    model_caveat = _MODEL_CAVEATS.get(model_type)
    if model_caveat is not None:
        caveats.append(model_caveat)
    codes = {rc.code for rc in reason_codes}
    if "stockout_constrained" in codes:
        caveats.append("Stockout days in the history mean the forecast may understate true demand.")
    if "insufficient_history" in codes:
        caveats.append("The short history makes this explanation less reliable than usual.")
    return caveats
