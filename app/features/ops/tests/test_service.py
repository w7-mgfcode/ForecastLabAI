"""Unit tests for the ops slice's pure scoring helpers.

These run without a database (-m "not integration"): the helpers are pure
functions with no I/O.
"""

from datetime import UTC, datetime
from types import SimpleNamespace
from typing import cast

from app.features.ops.schemas import StaleReason
from app.features.ops.service import (
    _alias_staleness,
    _run_feature_frame_version,
    classify_drift,
    extract_wape,
    score_retraining_candidate,
)
from app.features.registry.models import ModelRun

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


# =============================================================================
# classify_drift
# =============================================================================


def test_classify_drift_unknown_when_empty() -> None:
    """An empty history has no trend — direction is 'unknown', delta None."""
    assert classify_drift([]) == ("unknown", None)


def test_classify_drift_unknown_when_under_two_numeric() -> None:
    """Fewer than two numeric WAPEs yields 'unknown' (None gaps don't count)."""
    assert classify_drift([None, 10.0]) == ("unknown", None)
    assert classify_drift([10.0]) == ("unknown", None)


def test_classify_drift_degrading() -> None:
    """A latest WAPE far above the prior mean is 'degrading'; delta is positive."""
    direction, delta = classify_drift([10.0, 10.0, 20.0])
    assert direction == "degrading"
    assert delta == 10.0


def test_classify_drift_improving() -> None:
    """A latest WAPE far below the prior mean is 'improving'; delta is negative."""
    direction, delta = classify_drift([20.0, 20.0, 10.0])
    assert direction == "improving"
    assert delta == -10.0


def test_classify_drift_stable_within_band() -> None:
    """A change inside the ±10% relative band is 'stable'."""
    direction, delta = classify_drift([10.0, 10.5])  # +5% < 10% band
    assert direction == "stable"
    assert delta == 0.5


def test_classify_drift_tolerates_none_gaps() -> None:
    """None gaps are skipped; classification uses only numeric observations."""
    direction, delta = classify_drift([None, 10.0, None, 12.0])  # +20% over baseline 10
    assert direction == "degrading"
    assert delta == 2.0


def test_classify_drift_zero_baseline_guard() -> None:
    """A zero baseline never divides by zero: positive error degrades, zero is stable."""
    assert classify_drift([0.0, 5.0])[0] == "degrading"
    assert classify_drift([0.0, 0.0])[0] == "stable"


def test_classify_drift_never_raises_on_sparse_history() -> None:
    """Sparse / all-None history degrades gracefully to 'unknown'."""
    assert classify_drift([None, None, None]) == ("unknown", None)


# =============================================================================
# PRP-36 — _alias_staleness V-mismatch path
# =============================================================================


def _make_run(
    *,
    run_id: str,
    store_id: int = 1,
    product_id: int = 1,
    status: str = "success",
    created_at: datetime | None = None,
    feature_frame_version: int | None = None,
) -> ModelRun:
    """Minimal duck-typed ModelRun the helpers consume.

    The helpers only read ``.status / .store_id / .product_id / .created_at
    / .id / .runtime_info`` so a SimpleNamespace is sufficient at runtime;
    we ``cast`` to ``ModelRun`` so static checking is happy.
    """
    runtime_info: dict[str, object] = {}
    if feature_frame_version is not None:
        runtime_info["feature_frame_version"] = feature_frame_version
    fake = SimpleNamespace(
        run_id=run_id,
        id=hash(run_id) & 0xFFFFFFFF,
        store_id=store_id,
        product_id=product_id,
        status=status,
        created_at=created_at or datetime(2026, 1, 1, tzinfo=UTC),
        runtime_info=runtime_info if runtime_info else None,
    )
    return cast(ModelRun, fake)


def test_run_feature_frame_version_reads_runtime_info() -> None:
    """V is read from runtime_info JSONB; missing key resolves to V=1 (filter-aligned)."""
    assert _run_feature_frame_version(_make_run(run_id="a", feature_frame_version=2)) == 2
    assert _run_feature_frame_version(_make_run(run_id="b")) == 1


def test_run_feature_frame_version_honors_any_positive_int() -> None:
    """Any positive int V is honored (e.g. 3); non-int / non-positive / bool -> V=1.

    Regression for #338: feature_frame_version is an opaque incrementing integer
    (docs/_base/DOMAIN_MODEL.md), so V>=3 must NOT be clamped to 1 — the showcase
    stale_alias_trigger step registers a V=3 run to fire the
    feature_frame_version_mismatch verdict.
    """
    v3 = _make_run(run_id="v3")
    v3.runtime_info = {"feature_frame_version": 3}
    assert _run_feature_frame_version(v3) == 3

    # Non-int / non-positive / bool all fall back to V=1.
    for bad in ("2", 0, -1, True):
        run = _make_run(run_id=f"bad-{bad!r}")
        run.runtime_info = {"feature_frame_version": bad}
        assert _run_feature_frame_version(run) == 1


def test_alias_staleness_legacy_run_treated_as_v1_no_spurious_mismatch() -> None:
    """A legacy alias (no V key) compared to an explicit-V=1 comparable is NOT stale."""
    older = datetime(2026, 1, 1, tzinfo=UTC)
    legacy = _make_run(run_id="legacy", created_at=older)  # no V key
    explicit_v1 = _make_run(
        run_id="explicit-v1",
        created_at=older,  # same created_at → no NEWER_SUCCESS_RUN either
        feature_frame_version=1,
    )
    is_stale, reason, alias_v, comparable_v = _alias_staleness(legacy, {(1, 1): explicit_v1})
    # Both normalize to V=1 — no mismatch, no newer (same created_at), so not stale.
    assert is_stale is False
    assert reason is None
    assert alias_v == 1
    assert comparable_v is None


def test_alias_staleness_status_branch_wins() -> None:
    """A non-SUCCESS aliased run is stale with RUN_NOT_SUCCESS regardless of V."""
    run = _make_run(run_id="r1", status="failed", feature_frame_version=1)
    latest_map: dict[tuple[int, int], ModelRun] = {
        (1, 1): _make_run(run_id="r2", feature_frame_version=2)
    }
    is_stale, reason, alias_v, comparable_v = _alias_staleness(run, latest_map)
    assert is_stale is True
    assert reason == StaleReason.RUN_NOT_SUCCESS.value
    assert alias_v == 1
    assert comparable_v is None


def test_alias_staleness_v_mismatch_wins_over_newer_run() -> None:
    """A V1 alias with a newer V2 comparable run reports MISMATCH, not NEWER."""
    older = datetime(2026, 1, 1, tzinfo=UTC)
    newer = datetime(2026, 5, 1, tzinfo=UTC)
    run = _make_run(run_id="v1", created_at=older, feature_frame_version=1)
    latest = _make_run(run_id="v2", created_at=newer, feature_frame_version=2)
    is_stale, reason, alias_v, comparable_v = _alias_staleness(run, {(1, 1): latest})
    assert is_stale is True
    assert reason == StaleReason.FEATURE_FRAME_VERSION_MISMATCH.value
    assert alias_v == 1
    assert comparable_v == 2


def test_alias_staleness_v1_alias_v3_latest_reports_mismatch() -> None:
    """A V1 alias with a newer V3 comparable reports MISMATCH, not NEWER (#338).

    Mirrors the showcase stale_alias_trigger scenario: the demo-production alias
    points at a V1 run while the grain's newest run is V=3. Before #338 the V=3
    latest was clamped to V=1, so this fell through to NEWER_SUCCESS_RUN.
    """
    older = datetime(2026, 1, 1, tzinfo=UTC)
    newer = datetime(2026, 5, 1, tzinfo=UTC)
    run = _make_run(run_id="v1-alias", created_at=older, feature_frame_version=1)
    latest = _make_run(run_id="v3-latest", created_at=newer, feature_frame_version=3)
    is_stale, reason, alias_v, comparable_v = _alias_staleness(run, {(1, 1): latest})
    assert is_stale is True
    assert reason == StaleReason.FEATURE_FRAME_VERSION_MISMATCH.value
    assert alias_v == 1
    assert comparable_v == 3


def test_alias_staleness_same_v_newer_run_uses_newer_reason() -> None:
    """V matches but the comparable is newer → NEWER_SUCCESS_RUN reason."""
    older = datetime(2026, 1, 1, tzinfo=UTC)
    newer = datetime(2026, 5, 1, tzinfo=UTC)
    run = _make_run(run_id="v2-old", created_at=older, feature_frame_version=2)
    latest = _make_run(run_id="v2-new", created_at=newer, feature_frame_version=2)
    is_stale, reason, alias_v, comparable_v = _alias_staleness(run, {(1, 1): latest})
    assert is_stale is True
    assert reason == StaleReason.NEWER_SUCCESS_RUN.value
    assert alias_v == 2
    assert comparable_v is None


def test_alias_staleness_v1_alias_v1_latest_legacy_back_compat() -> None:
    """A V1 alias whose latest comparable is also legacy V1 (no key) → not stale."""
    older = datetime(2026, 1, 1, tzinfo=UTC)
    run = _make_run(run_id="legacy", created_at=older)  # no V key
    # Same run is latest_by_grain — no newer comparable.
    is_stale, reason, alias_v, comparable_v = _alias_staleness(run, {(1, 1): run})
    assert is_stale is False
    assert reason is None
    # PRP-36 — legacy missing-key normalizes to V=1 inside the ops layer
    # so it matches the registry's _feature_frame_version_filter contract.
    assert alias_v == 1
    assert comparable_v is None


def test_alias_staleness_legacy_v1_vs_explicit_v1_no_mismatch_when_same_run() -> None:
    """A legacy run carrying no V key compared to itself is not stale (same id)."""
    run = _make_run(run_id="self", feature_frame_version=1)
    is_stale, reason, _, _ = _alias_staleness(run, {(1, 1): run})
    assert is_stale is False
    assert reason is None
