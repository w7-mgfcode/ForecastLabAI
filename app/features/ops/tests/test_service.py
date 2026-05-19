"""Unit tests for the ops slice's pure scoring helpers.

These run without a database (-m "not integration"): the helpers are pure
functions with no I/O.
"""

from app.features.ops.service import extract_wape, score_retraining_candidate

# =============================================================================
# score_retraining_candidate
# =============================================================================


def test_score_zero_when_fresh_and_no_error() -> None:
    """A brand-new run with no WAPE scores 0.0."""
    assert score_retraining_candidate(0, None) == 0.0


def test_score_max_when_fully_stale_and_max_error() -> None:
    """90+ days stale with WAPE 100 saturates both terms to 1.0."""
    assert score_retraining_candidate(90, 100.0) == 1.0


def test_score_clamps_negative_staleness_and_high_wape() -> None:
    """Negative staleness clamps to 0; WAPE above the cap clamps to 1.0."""
    # staleness -> 0.0, error -> 1.0; score = 0.6*0 + 0.4*1.0 = 0.4
    assert score_retraining_candidate(-5, 250.0) == 0.4


def test_score_midpoint() -> None:
    """Half-stale with half-max WAPE lands at the weighted midpoint."""
    # staleness 45/90 -> 0.5, error 50/100 -> 0.5; score = 0.6*0.5 + 0.4*0.5 = 0.5
    assert score_retraining_candidate(45, 50.0) == 0.5


def test_score_staleness_only_when_wape_unknown() -> None:
    """With WAPE unknown the score degrades to the staleness term alone."""
    # staleness 90 -> 1.0, error -> 0.0; score = 0.6
    assert score_retraining_candidate(90, None) == 0.6


def test_score_is_bounded() -> None:
    """The score never escapes [0.0, 1.0] for extreme inputs."""
    assert score_retraining_candidate(10_000, 10_000.0) == 1.0
    assert score_retraining_candidate(-10_000, -10_000.0) == 0.0


# =============================================================================
# extract_wape
# =============================================================================


def test_extract_wape_prefers_wape_then_wape_mean() -> None:
    """The 'wape' key wins; 'wape_mean' and 'WAPE' are fallbacks."""
    assert extract_wape({"wape": 12.0}) == 12.0
    assert extract_wape({"wape_mean": 8.5}) == 8.5
    assert extract_wape({"WAPE": 4.0}) == 4.0
    assert extract_wape({"wape": 1.0, "wape_mean": 99.0}) == 1.0


def test_extract_wape_returns_none_for_missing_or_empty() -> None:
    """None and an empty / unrelated dict yield None — never an exception."""
    assert extract_wape(None) is None
    assert extract_wape({}) is None
    assert extract_wape({"mae": 3.2}) is None


def test_extract_wape_rejects_non_numeric_and_bool() -> None:
    """A non-numeric value yields None; bool is rejected (it is not a metric)."""
    assert extract_wape({"wape": "bad"}) is None
    assert extract_wape({"wape": None}) is None
    assert extract_wape({"wape": True}) is None
    assert extract_wape({"wape": False}) is None


def test_extract_wape_coerces_int_to_float() -> None:
    """An integer WAPE is returned as a float."""
    result = extract_wape({"wape": 25})
    assert result == 25.0
    assert isinstance(result, float)
