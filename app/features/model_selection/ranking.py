"""Pure ranking + confidence logic for the champion selector (issue #353).

No DB, no I/O — every function here is deterministic and unit-tested directly.
The ranking key and confidence policy implement the PRP's LOCKED decision #6
(deterministic tie-break chain) and the relative-improvement confidence model.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from app.features.model_selection.schemas import (
    CandidateResult,
    ChartData,
    ConfidenceLevel,
    FoldChart,
    ModelRankEntry,
    RankingPolicy,
    RankingResult,
)

# Below this relative WAPE lead over second place, the winner is a near-tie and
# confidence is capped at LOW (the lead is not meaningful).
NEAR_TIE_EPSILON = 0.02

# The metric keys that MUST be finite for a candidate to be rankable. rmse is
# carried for the contract but not required (it never enters the sort key).
_REQUIRED_FINITE = ("wape", "smape", "mae", "bias")


@dataclass(frozen=True)
class NormalizedMetrics:
    """The five backtest metrics plus the derived sample size, all floats."""

    wape: float
    smape: float
    mae: float
    rmse: float
    bias: float
    sample_size: int

    def as_dict(self) -> dict[str, float]:
        """Stable 6-key dict embedded in ``ModelRankEntry.metrics``."""
        return {
            "wape": self.wape,
            "smape": self.smape,
            "mae": self.mae,
            "rmse": self.rmse,
            "bias": self.bias,
            "sample_size": float(self.sample_size),
        }


def _is_finite(value: float) -> bool:
    return not (math.isnan(value) or math.isinf(value))


def normalize_metrics(
    aggregated_metrics: dict[str, float] | None,
    sample_size: int,
) -> NormalizedMetrics | None:
    """Coerce a raw 5-key backtest metric dict into ``NormalizedMetrics``.

    Returns ``None`` (candidate is unrankable) when the dict is missing/empty or
    when any of the sort-key metrics (wape, smape, mae, bias) is NaN/inf — e.g.
    a WAPE of ``inf`` from an all-zero actual window.
    """
    if not aggregated_metrics:
        return None

    def _g(key: str) -> float:
        raw = aggregated_metrics.get(key)
        return float(raw) if raw is not None else math.nan

    metrics = NormalizedMetrics(
        wape=_g("wape"),
        smape=_g("smape"),
        mae=_g("mae"),
        rmse=_g("rmse"),
        bias=_g("bias"),
        sample_size=sample_size,
    )
    if not all(_is_finite(getattr(metrics, name)) for name in _REQUIRED_FINITE):
        return None
    return metrics


def _primary_value(metrics: NormalizedMetrics, ranking_metric: str) -> float:
    """Value of the primary ranking metric (``bias`` ranks by magnitude)."""
    if ranking_metric == "bias":
        return abs(metrics.bias)
    return float(getattr(metrics, ranking_metric))


def _sort_key(
    metrics: NormalizedMetrics, model_type: str, ranking_metric: str
) -> tuple[float, float, float, float, str]:
    """Deterministic sort key (LOCKED #6).

    Primary = the chosen ranking metric, then the fixed tie-break chain
    ``wape -> smape -> abs(bias) -> mae -> model_type`` with the primary metric
    removed from the chain so it is never duplicated.
    """
    chain: list[tuple[str, float]] = [
        ("wape", metrics.wape),
        ("smape", metrics.smape),
        ("bias", abs(metrics.bias)),
        ("mae", metrics.mae),
    ]
    key: list[float] = [_primary_value(metrics, ranking_metric)]
    key.extend(value for name, value in chain if name != ranking_metric)
    return (key[0], key[1], key[2], key[3], model_type)


def rank_candidates(
    results: list[CandidateResult],
    policy: RankingPolicy,
    ranking_metric: str = "wape",
    availability_status: str | None = None,
) -> RankingResult:
    """Rank completed candidates and pick a deterministic winner.

    Failed/filtered candidates are never hidden — they appear as excluded
    ``ModelRankEntry`` rows (``rank=None``) after the ranked winners.
    """
    valid: list[tuple[CandidateResult, NormalizedMetrics]] = []
    excluded: list[ModelRankEntry] = []

    for result in results:
        if result.failed:
            excluded.append(_excluded_entry(result, result.error or "candidate backtest failed"))
            continue
        metrics = normalize_metrics(result.aggregated_metrics, result.sample_size)
        if metrics is None:
            excluded.append(_excluded_entry(result, "missing or non-finite primary metric"))
            continue
        if metrics.sample_size < policy.minimum_sample_size:
            excluded.append(
                _excluded_entry(
                    result,
                    f"sample_size {metrics.sample_size} below minimum {policy.minimum_sample_size}",
                )
            )
            continue
        valid.append((result, metrics))

    if not valid:
        return RankingResult(
            winner=None,
            entries=excluded,
            confidence="low",
            reasons=["No candidate produced a valid backtest."],
        )

    ordered = sorted(valid, key=lambda pair: _sort_key(pair[1], pair[0].model_type, ranking_metric))
    ranked_entries = [
        ModelRankEntry(
            rank=index + 1,
            model_type=result.model_type,
            params=result.params,
            included=True,
            metrics=metrics.as_dict(),
        )
        for index, (result, metrics) in enumerate(ordered)
    ]

    confidence, reasons = _confidence(ordered, policy, availability_status)

    return RankingResult(
        winner=ranked_entries[0],
        entries=ranked_entries + excluded,
        confidence=confidence,
        reasons=reasons,
    )


def _excluded_entry(result: CandidateResult, reason: str) -> ModelRankEntry:
    return ModelRankEntry(
        rank=None,
        model_type=result.model_type,
        params=result.params,
        included=False,
        exclusion_reason=reason,
        metrics=None,
    )


def _confidence(
    ordered: list[tuple[CandidateResult, NormalizedMetrics]],
    policy: RankingPolicy,
    availability_status: str | None,
) -> tuple[ConfidenceLevel, list[str]]:
    """Derive the recommendation confidence from the ranked candidates.

    Order of checks: a single valid candidate, limited availability, or an
    over-threshold winner bias all cap confidence at LOW; a clear WAPE lead with
    acceptable bias is HIGH; everything in between is MEDIUM.
    """
    reasons: list[str] = []
    winner_metrics = ordered[0][1]

    if len(ordered) == 1:
        reasons.append("Only one candidate produced a valid backtest.")
        return "low", reasons

    second_metrics = ordered[1][1]
    if second_metrics.wape > 0:
        rel_improvement = (second_metrics.wape - winner_metrics.wape) / second_metrics.wape
    else:
        rel_improvement = 0.0

    bias_ok = abs(winner_metrics.bias) <= policy.max_acceptable_abs_bias

    if availability_status == "limited":
        reasons.append("Data availability is limited; treat the recommendation cautiously.")
        return "low", reasons
    if not bias_ok:
        reasons.append(
            f"Winner bias {winner_metrics.bias:.3f} exceeds the acceptable bound "
            f"{policy.max_acceptable_abs_bias:.3f}."
        )
        return "low", reasons
    if rel_improvement < NEAR_TIE_EPSILON:
        reasons.append(f"Winner WAPE lead over second place is {rel_improvement:.1%} — a near tie.")
        return "low", reasons
    if rel_improvement >= policy.high_confidence_rel_improvement:
        reasons.append(
            f"Winner WAPE beats second place by {rel_improvement:.1%} "
            f"(>= {policy.high_confidence_rel_improvement:.0%})."
        )
        return "high", reasons

    reasons.append(
        f"Winner leads second place by {rel_improvement:.1%}, below the "
        f"{policy.high_confidence_rel_improvement:.0%} high-confidence threshold."
    )
    return "medium", reasons


def _fold_wape(actuals: list[float], predictions: list[float]) -> float:
    """WAPE (%) for one fold; 0.0 when the actual window sums to zero."""
    denominator = sum(abs(a) for a in actuals)
    if denominator == 0:
        return 0.0
    numerator = sum(abs(a - p) for a, p in zip(actuals, predictions, strict=False))
    return numerator / denominator * 100.0


def build_chart_data(results: list[CandidateResult], ranking: RankingResult) -> ChartData:
    """Assemble the chart-ready comparison payload from candidate results.

    Keyed by ``model_type``; when a candidate list repeats a model_type the last
    occurrence wins (acceptable for v1 — duplicate model_types are uncommon).
    """
    by_type: dict[str, CandidateResult] = {r.model_type: r for r in results}
    wape_by_model: dict[str, float] = {}
    bias_by_model: dict[str, float] = {}
    fold_stability: dict[str, list[float]] = {}

    for entry in ranking.entries:
        if not entry.included or entry.metrics is None:
            continue
        wape_by_model[entry.model_type] = entry.metrics["wape"]
        bias_by_model[entry.model_type] = entry.metrics["bias"]
        result = by_type.get(entry.model_type)
        if result is not None:
            fold_stability[entry.model_type] = [
                _fold_wape(fold.actuals, fold.predictions) for fold in result.folds
            ]

    winner_folds: list[FoldChart] = []
    if ranking.winner is not None:
        winner_result = by_type.get(ranking.winner.model_type)
        if winner_result is not None:
            winner_folds = winner_result.folds

    return ChartData(
        wape_by_model=wape_by_model,
        bias_by_model=bias_by_model,
        fold_stability=fold_stability,
        winner_actual_vs_predicted=winner_folds,
    )
