"""Unit tests for the pure ranking + chart logic."""

from __future__ import annotations

import math

from app.features.model_selection.ranking import (
    build_chart_data,
    normalize_metrics,
    rank_candidates,
)
from app.features.model_selection.schemas import RankingPolicy
from app.features.model_selection.tests.conftest import make_candidate_result


def test_rank_candidates_wape_smape_abs_bias_mae_tie_break() -> None:
    """Default sort key is (wape, smape, abs(bias), mae, model_type) (LOCKED #6)."""
    # Same wape; B wins on smape; C loses smape but would win mae (irrelevant).
    results = [
        make_candidate_result("a_model", wape=10.0, smape=20.0, bias=1.0, mae=9.0),
        make_candidate_result("b_model", wape=10.0, smape=15.0, bias=5.0, mae=8.0),
        make_candidate_result("c_model", wape=10.0, smape=18.0, bias=0.0, mae=1.0),
    ]
    ranking = rank_candidates(results, RankingPolicy(), "wape")
    order = [e.model_type for e in ranking.entries if e.included]
    assert order == ["b_model", "c_model", "a_model"]
    assert ranking.winner is not None
    assert ranking.winner.model_type == "b_model"
    assert ranking.winner.rank == 1


def test_rank_candidates_model_type_breaks_full_tie() -> None:
    """Identical metrics fall back to model_type alphabetical for determinism."""
    results = [
        make_candidate_result("zeta", wape=5.0, smape=5.0, bias=0.0, mae=1.0),
        make_candidate_result("alpha", wape=5.0, smape=5.0, bias=0.0, mae=1.0),
    ]
    ranking = rank_candidates(results, RankingPolicy(), "wape")
    assert ranking.winner is not None
    assert ranking.winner.model_type == "alpha"


def test_rank_candidates_non_default_metric_puts_it_first() -> None:
    """ranking_metric='mae' ranks by mae first."""
    results = [
        make_candidate_result("high_wape_low_mae", wape=50.0, mae=1.0),
        make_candidate_result("low_wape_high_mae", wape=5.0, mae=99.0),
    ]
    ranking = rank_candidates(results, RankingPolicy(), "mae")
    assert ranking.winner is not None
    assert ranking.winner.model_type == "high_wape_low_mae"


def test_rank_candidates_excludes_missing_or_nan_metrics() -> None:
    """A NaN/None primary metric drops the candidate to an excluded entry."""
    good = make_candidate_result("good", wape=10.0)
    nan_metrics = make_candidate_result("nan_model", wape=float("nan"))
    no_metrics = make_candidate_result("no_metrics", failed=False)
    no_metrics.aggregated_metrics = None
    ranking = rank_candidates([good, nan_metrics, no_metrics], RankingPolicy(), "wape")

    assert ranking.winner is not None
    assert ranking.winner.model_type == "good"
    excluded = {e.model_type: e for e in ranking.entries if not e.included}
    assert set(excluded) == {"nan_model", "no_metrics"}
    assert excluded["nan_model"].rank is None
    assert excluded["nan_model"].exclusion_reason is not None


def test_rank_candidates_normalizes_five_metric_keys_including_rmse() -> None:
    """normalize_metrics carries all five keys incl. rmse; entries echo them."""
    metrics = normalize_metrics(
        {"mae": 1.0, "rmse": 2.0, "smape": 3.0, "wape": 4.0, "bias": 5.0}, sample_size=20
    )
    assert metrics is not None
    assert metrics.rmse == 2.0
    as_dict = metrics.as_dict()
    assert set(as_dict) == {"wape", "smape", "mae", "rmse", "bias", "sample_size"}

    ranking = rank_candidates([make_candidate_result("m", rmse=7.5)], RankingPolicy(), "wape")
    assert ranking.entries[0].metrics is not None
    assert ranking.entries[0].metrics["rmse"] == 7.5


def test_normalize_metrics_rejects_inf_wape() -> None:
    """An inf WAPE (all-zero actuals) is unrankable."""
    assert (
        normalize_metrics(
            {"mae": 1.0, "rmse": 2.0, "smape": 3.0, "wape": math.inf, "bias": 0.0}, 10
        )
        is None
    )


def test_rank_candidates_excludes_below_minimum_sample_size() -> None:
    """A candidate below the policy sample floor is excluded."""
    results = [
        make_candidate_result("ok", wape=10.0, sample_size=40),
        make_candidate_result("tiny", wape=1.0, sample_size=5),
    ]
    ranking = rank_candidates(results, RankingPolicy(minimum_sample_size=30), "wape")
    assert ranking.winner is not None
    assert ranking.winner.model_type == "ok"
    excluded = [e for e in ranking.entries if not e.included]
    assert excluded[0].model_type == "tiny"


def test_confidence_high_when_winner_beats_second_by_10_percent() -> None:
    """A >=10% relative WAPE lead with acceptable bias yields HIGH confidence."""
    results = [
        make_candidate_result("winner", wape=10.0, bias=0.1),
        make_candidate_result("second", wape=20.0, bias=0.1),
    ]
    ranking = rank_candidates(results, RankingPolicy(), "wape", availability_status="ready")
    assert ranking.winner is not None
    assert ranking.winner.model_type == "winner"
    assert ranking.confidence == "high"


def test_confidence_low_for_single_valid_candidate() -> None:
    ranking = rank_candidates([make_candidate_result("solo", wape=10.0)], RankingPolicy(), "wape")
    assert ranking.confidence == "low"


def test_confidence_low_for_near_tie() -> None:
    """A sub-epsilon lead is a near tie → LOW."""
    results = [
        make_candidate_result("a", wape=10.0),
        make_candidate_result("b", wape=10.05),
    ]
    ranking = rank_candidates(results, RankingPolicy(), "wape", availability_status="ready")
    assert ranking.confidence == "low"


def test_confidence_medium_when_lead_below_high_threshold() -> None:
    """A 5% lead (between epsilon and 10%) is MEDIUM."""
    results = [
        make_candidate_result("a", wape=9.5),
        make_candidate_result("b", wape=10.0),
    ]
    ranking = rank_candidates(results, RankingPolicy(), "wape", availability_status="ready")
    assert ranking.confidence == "medium"


def test_confidence_low_when_availability_limited() -> None:
    """Limited availability caps confidence at LOW even with a clear lead."""
    results = [
        make_candidate_result("winner", wape=10.0),
        make_candidate_result("second", wape=20.0),
    ]
    ranking = rank_candidates(results, RankingPolicy(), "wape", availability_status="limited")
    assert ranking.confidence == "low"


def test_confidence_low_when_bias_over_threshold() -> None:
    """A winner bias above the policy bound caps confidence at LOW."""
    results = [
        make_candidate_result("winner", wape=10.0, bias=50.0),
        make_candidate_result("second", wape=20.0, bias=0.0),
    ]
    ranking = rank_candidates(
        results, RankingPolicy(max_acceptable_abs_bias=1.0), "wape", availability_status="ready"
    )
    assert ranking.confidence == "low"


def test_all_failed_candidates_yield_no_winner() -> None:
    results = [
        make_candidate_result("x", failed=True, error="train error"),
        make_candidate_result("y", failed=True, error="value error"),
    ]
    ranking = rank_candidates(results, RankingPolicy(), "wape")
    assert ranking.winner is None
    assert ranking.confidence == "low"
    assert all(not e.included for e in ranking.entries)


def test_winner_entry_carries_params_for_rebuild() -> None:
    """The winner entry preserves the original candidate params."""
    results = [
        make_candidate_result("seasonal_naive", wape=10.0, params={"season_length": 7}),
        make_candidate_result("naive", wape=20.0, params={}),
    ]
    ranking = rank_candidates(results, RankingPolicy(), "wape")
    assert ranking.winner is not None
    assert ranking.winner.model_type == "seasonal_naive"
    assert ranking.winner.params == {"season_length": 7}


def test_chart_data_has_wape_bias_fold_stability_and_winner_actual_vs_predicted() -> None:
    """build_chart_data populates all four chart series."""
    results = [
        make_candidate_result("winner", wape=10.0, n_folds=3),
        make_candidate_result("second", wape=20.0, n_folds=3),
    ]
    ranking = rank_candidates(results, RankingPolicy(), "wape")
    chart = build_chart_data(results, ranking)

    assert set(chart.wape_by_model) == {"winner", "second"}
    assert chart.wape_by_model["winner"] == 10.0
    assert set(chart.bias_by_model) == {"winner", "second"}
    assert len(chart.fold_stability["winner"]) == 3
    assert all(isinstance(v, float) for v in chart.fold_stability["winner"])
    assert len(chart.winner_actual_vs_predicted) == 3
    assert chart.winner_actual_vs_predicted[0].actuals
