"""Integration test for the end-to-end demo pipeline.

Spins up a fresh uvicorn subprocess on port 8124 (separate from the
developer's usual :8123 to avoid colliding with an already-running
server), runs `scripts/run_demo.py --reset --api-url ...`, and asserts
exit 0 + canonical summary line.

Marker: `@pytest.mark.integration` — requires `docker compose up -d`
and applied Alembic migrations. Skips automatically if Postgres isn't
reachable.
"""

from __future__ import annotations

import os
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from collections.abc import Iterator
from pathlib import Path

import pytest

# Resolve the repo root once so the subprocess calls work regardless of
# where pytest was invoked from (matches scripts/run_demo.py shape).
REPO_ROOT: Path = Path(__file__).resolve().parent.parent
UVICORN_PORT: int = 8124
DEMO_API_URL: str = f"http://127.0.0.1:{UVICORN_PORT}"
HEALTH_URL: str = f"{DEMO_API_URL}/health"

# Wall-clock budget. The PRP target is 180 s soft; integration adds
# uvicorn boot, migrations idempotency, and a fresh seeder run so we
# allow more headroom in the subprocess timeout (240 s).
UVICORN_BOOT_TIMEOUT_S: float = 30.0
DEMO_SUBPROCESS_TIMEOUT_S: float = 240.0

# Resolve `uv` to an absolute path so ruff's S607 stays happy and so the
# subprocess doesn't depend on PATH lookup at exec time.
UV_BIN: str = shutil.which("uv") or "uv"


def _postgres_reachable() -> bool:
    """Quick socket probe against docker-compose Postgres on :5433.

    Faster + cheaper than spinning a real asyncpg connection; the script
    will surface deeper DB issues at runtime if Postgres is up but not
    migrated.
    """
    try:
        with socket.create_connection(("localhost", 5433), timeout=1.0):
            return True
    except OSError:
        return False


def _wait_for_health(timeout_s: float) -> bool:
    """Poll the uvicorn health endpoint until 200 or timeout."""
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(HEALTH_URL, timeout=2.0) as resp:  # noqa: S310
                if resp.status == 200:
                    return True
        except (urllib.error.URLError, ConnectionResetError, OSError):
            pass
        time.sleep(1.0)
    return False


@pytest.fixture
def uvicorn_subprocess() -> Iterator[subprocess.Popen[bytes]]:
    """Boot uvicorn on :8124 for the integration test; tear it down after.

    Background process; we wait for /health to flip green before yielding.
    Falls back to terminate() / kill() on teardown so the test never leaks
    a child process across runs.
    """
    if not _postgres_reachable():
        pytest.skip(
            "Postgres on :5433 not reachable — bring up `docker compose up -d` "
            "before running integration tests"
        )

    env = os.environ.copy()
    # Force a known app_env so seeder_allow_production guard doesn't bite.
    env.setdefault("APP_ENV", "development")

    # Redirect uvicorn output to a temp file rather than a subprocess.PIPE.
    # The seeder + structlog produce enough INFO output to fill a 64-KB
    # pipe buffer during /seeder/generate; once full, uvicorn blocks on
    # write and the HTTP request appears to hang. Writing to a file
    # never blocks, and we keep the file around so failure mode can
    # inspect it.
    log_file_path = Path(tempfile.gettempdir()) / f"uvicorn-e2e-{os.getpid()}.log"
    log_file = log_file_path.open("w", buffering=1)

    proc = subprocess.Popen(  # noqa: S603 — internal command, trusted args
        [
            UV_BIN,
            "run",
            "uvicorn",
            "app.main:app",
            "--host",
            "127.0.0.1",
            "--port",
            str(UVICORN_PORT),
            "--log-level",
            "warning",
        ],
        cwd=str(REPO_ROOT),
        env=env,
        stdout=log_file,
        stderr=subprocess.STDOUT,
    )

    try:
        if not _wait_for_health(UVICORN_BOOT_TIMEOUT_S):
            proc.terminate()
            try:
                proc.wait(timeout=5.0)
            except subprocess.TimeoutExpired:
                proc.kill()
            log_file.close()
            log_tail = log_file_path.read_text()[-2000:] if log_file_path.exists() else "(no log)"
            pytest.skip(
                f"uvicorn did not become healthy on {DEMO_API_URL} within "
                f"{UVICORN_BOOT_TIMEOUT_S:.0f}s — tail of log:\n{log_tail}"
            )
        yield proc
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=5.0)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait(timeout=5.0)
        log_file.close()
        # Best-effort cleanup; leave the file in place if the test failed.
        if proc.returncode == 0:
            log_file_path.unlink(missing_ok=True)


@pytest.mark.integration
def test_run_demo_e2e_exits_green(uvicorn_subprocess: subprocess.Popen[bytes]) -> None:
    """`scripts/run_demo.py --reset` exits 0 and prints the canonical summary."""
    # Run the script against the freshly booted uvicorn.
    result = subprocess.run(  # noqa: S603 — internal command, trusted args
        [
            UV_BIN,
            "run",
            "python",
            "scripts/run_demo.py",
            "--seed",
            "42",
            "--reset",
            "--api-url",
            DEMO_API_URL,
            # Per-step timeout. /seeder/generate for demo_minimal can spend
            # 60-90 s on inserts on slower hardware (3 stores x 10 products
            # x 92 days of sales + inventory + prices + promotions). The
            # default 60 s is fine for the foreground steps but tight for
            # seed; bump to 120 s for the integration run.
            "--timeout",
            "120",
        ],
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
        timeout=DEMO_SUBPROCESS_TIMEOUT_S,
        check=False,
    )

    stdout = result.stdout
    stderr = result.stderr
    # Echo the script output back through pytest so debugging is easy
    # when this test fails on a developer machine or CI.
    print("---- run_demo stdout ----", file=sys.stderr)
    print(stdout, file=sys.stderr)
    print("---- run_demo stderr ----", file=sys.stderr)
    print(stderr, file=sys.stderr)

    assert result.returncode == 0, (
        f"run_demo.py exited {result.returncode}; see stdout/stderr captured above"
    )
    # Canonical final-line contract from PRP-15 success criteria.
    assert "alias=demo-production" in stdout
    assert "winner=" in stdout
    assert "wall_clock=" in stdout
    # We expect three backtested model types.
    assert "runs=3" in stdout


# PRP-38 — wall-clock budgets for the in-process showcase_rich pipeline.
SHOWCASE_RICH_WALL_BUDGET_SOFT_S: float = 240.0
SHOWCASE_RICH_WALL_BUDGET_HARD_S: float = 300.0


@pytest.mark.integration
def test_run_demo_showcase_rich_e2e(
    uvicorn_subprocess: subprocess.Popen[bytes],
) -> None:
    """PRP-38 — POST /demo/run with scenario=showcase_rich exits green.

    Asserts:

    - HTTP 200 from /demo/run within the SOFT wall-clock budget (240 s) —
      soft-warn beyond, hard-fail beyond the HARD budget (300 s).
    - Pipeline ``overall_status == "pass"``.
    - At least one V2 run was registered: the ``v2_train`` step's data
      carries ``feature_frame_version == 2`` and a non-empty
      ``v2_run_id``.
    - The ``backtest`` step's data echoes ``bucketed_aggregated_metrics``
      with the expected bucket-id subset (PRP-36 contract).
    """
    import json

    # The pipeline expects a seeded DB; reset+skip_seed=False so the run
    # generates SHOWCASE_RICH data first. POST /demo/run is synchronous —
    # it returns the full DemoRunResult.
    body = json.dumps(
        {
            "seed": 42,
            "reset": True,
            "skip_seed": False,
            "scenario": "showcase_rich",
        }
    ).encode("utf-8")

    start = time.monotonic()
    req = urllib.request.Request(  # noqa: S310 — http://127.0.0.1 internal URL
        f"{DEMO_API_URL}/demo/run",
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=SHOWCASE_RICH_WALL_BUDGET_HARD_S) as resp:  # noqa: S310
            payload = resp.read()
            assert resp.status == 200, f"POST /demo/run -> {resp.status}"
    except urllib.error.HTTPError as exc:
        # An RFC 7807 problem+json comes back here; surface it.
        raise AssertionError(f"POST /demo/run failed: HTTP {exc.code} body={exc.read()!r}") from exc
    wall = time.monotonic() - start
    result = json.loads(payload)

    # ---- Wall-clock budget ----------------------------------------------------
    if wall > SHOWCASE_RICH_WALL_BUDGET_HARD_S:
        pytest.fail(
            f"showcase_rich exceeded HARD budget: {wall:.1f}s > "
            f"{SHOWCASE_RICH_WALL_BUDGET_HARD_S:.0f}s"
        )
    if wall > SHOWCASE_RICH_WALL_BUDGET_SOFT_S:
        # Soft-warn — surface to the operator but keep the test green.
        print(
            f"⚠️ showcase_rich over SOFT budget: {wall:.1f}s > "
            f"{SHOWCASE_RICH_WALL_BUDGET_SOFT_S:.0f}s",
            file=sys.stderr,
        )

    # ---- Overall status ------------------------------------------------------
    assert result["overall_status"] == "pass", (
        f"pipeline did not pass: status={result['overall_status']!r} "
        f"steps={[(s['step_name'], s['status'], s['detail']) for s in result['steps']]}"
    )

    # ---- V2 run registered ---------------------------------------------------
    by_name = {s["step_name"]: s for s in result["steps"]}
    v2 = by_name.get("v2_train")
    assert v2 is not None, "v2_train step missing from showcase_rich run"
    assert v2["status"] == "pass", (
        f"v2_train did not pass: {v2['status']!r} detail={v2['detail']!r}"
    )
    assert v2["data"]["feature_frame_version"] == 2
    assert v2["data"]["v2_run_id"], "v2_train did not surface a v2_run_id"

    # ---- Bucket metrics populated --------------------------------------------
    bt = by_name.get("backtest")
    assert bt is not None and bt["status"] == "pass"
    buckets = bt["data"].get("bucketed_aggregated_metrics")
    assert buckets is not None and len(buckets) >= 1, (
        f"backtest emitted no horizon-bucket metrics on showcase_rich: "
        f"detail={bt['detail']!r} data_keys={list(bt['data'].keys())}"
    )
    # At minimum the near-horizon buckets should be present given
    # n_splits=3, horizon=14.
    assert "h_1_7" in buckets


@pytest.mark.integration
def test_run_demo_showcase_rich_decision_portfolio(
    uvicorn_subprocess: subprocess.Popen[bytes],
) -> None:
    """PRP-39 — showcase_rich exercises decision + portfolio lifecycle.

    Asserts:

    - HTTP 200 from /demo/run within the SOFT wall-clock budget (240 s);
      hard-fail beyond the HARD budget (300 s).
    - Pipeline ``overall_status == "pass"``.
    - All four new PRP-39 step events fire with status ∈ {pass, warn}:
      champion_compat_compare, stale_alias_trigger, safer_promote_flow,
      batch_preset.
    - The cleanup step restores ``demo-production`` alias to the original
      V2 winner captured before the safer-Promote swap (R15).
    """
    import json

    body = json.dumps(
        {
            "seed": 42,
            "reset": True,
            "skip_seed": False,
            "scenario": "showcase_rich",
        }
    ).encode("utf-8")

    start = time.monotonic()
    req = urllib.request.Request(  # noqa: S310 — http://127.0.0.1 internal URL
        f"{DEMO_API_URL}/demo/run",
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=SHOWCASE_RICH_WALL_BUDGET_HARD_S) as resp:  # noqa: S310
            payload = resp.read()
            assert resp.status == 200, f"POST /demo/run -> {resp.status}"
    except urllib.error.HTTPError as exc:
        raise AssertionError(f"POST /demo/run failed: HTTP {exc.code} body={exc.read()!r}") from exc
    wall = time.monotonic() - start
    result = json.loads(payload)

    if wall > SHOWCASE_RICH_WALL_BUDGET_HARD_S:
        pytest.fail(
            f"showcase_rich decision/portfolio exceeded HARD budget: "
            f"{wall:.1f}s > {SHOWCASE_RICH_WALL_BUDGET_HARD_S:.0f}s"
        )
    if wall > SHOWCASE_RICH_WALL_BUDGET_SOFT_S:
        print(
            f"⚠️ showcase_rich decision/portfolio over SOFT budget: "
            f"{wall:.1f}s > {SHOWCASE_RICH_WALL_BUDGET_SOFT_S:.0f}s",
            file=sys.stderr,
        )

    assert result["overall_status"] == "pass", (
        f"pipeline did not pass: status={result['overall_status']!r} "
        f"steps={[(s['step_name'], s['status'], s['detail']) for s in result['steps']]}"
    )

    by_name = {s["step_name"]: s for s in result["steps"]}

    # ---- PRP-39 — all four new step events fired ---------------------------
    ok_statuses = {"pass", "warn"}
    for step_name in (
        "champion_compat_compare",
        "stale_alias_trigger",
        "safer_promote_flow",
        "batch_preset",
    ):
        step = by_name.get(step_name)
        assert step is not None, f"{step_name} missing from showcase_rich run"
        assert step["status"] in ok_statuses, (
            f"{step_name} status={step['status']!r} detail={step['detail']!r}"
        )

    # ---- PRP-39 — champion_compat_compare derives V_a/V_b client-side -----
    compat = by_name["champion_compat_compare"]
    if compat["status"] == "pass":
        # Skip status is also legitimate when no V1 baseline on the grain.
        assert compat["data"]["compatible"] is False, (
            f"compat_compare expected compatible=false, got {compat['data']!r}"
        )
        assert compat["data"]["comparable_reason"] == "feature_frame_version_mismatch"

    # ---- PRP-39 — stale_alias_trigger surfaces V mismatch on /ops ---------
    stale = by_name["stale_alias_trigger"]
    if stale["status"] == "pass":
        assert stale["data"]["stale_reason"] == "feature_frame_version_mismatch", (
            f"unexpected stale_reason: {stale['data']!r}"
        )

    # ---- PRP-39 — batch_preset returned a terminal status -----------------
    batch = by_name["batch_preset"]
    if batch["status"] in ok_statuses:
        assert batch["data"].get("batch_id"), "batch_preset emitted no batch_id"
        assert batch["data"].get("preset_source") == "quick_baseline_sweep"

    # ---- PRP-39 R15 — cleanup restores the alias --------------------------
    cleanup = by_name.get("cleanup")
    assert cleanup is not None
    # If safer_promote_flow swapped the alias, cleanup MUST have restored it.
    promote = by_name["safer_promote_flow"]
    if promote["status"] == "pass":
        assert cleanup["data"].get("alias_restored") is True, (
            "cleanup did not restore the alias swapped by safer_promote_flow"
        )
        restored = cleanup["data"].get("restored_run_id")
        before = promote["data"].get("before_run_id")
        assert restored == before, (
            f"cleanup restored to {restored!r}, expected the pre-swap alias target {before!r}"
        )


@pytest.mark.integration
def test_run_demo_showcase_rich_full_epic(
    uvicorn_subprocess: subprocess.Popen[bytes],
) -> None:
    """PRP-41 — showcase_rich exposes the agent_hitl_flow + ops_snapshot steps.

    Asserts the PRP-41 contracts hold WHEN the steps execute. The full
    showcase_rich pipeline has a pre-existing fragility documented in
    ``docs/_base/RUNBOOKS.md`` entry 18 — ``safer_promote_flow`` (PRP-39)
    swaps the ``demo-production`` alias to a placeholder run whose
    ``artifact_uri`` ``_parse_artifact_key`` can't parse, breaking the
    downstream ``scenario_simulate_and_save`` step on a fresh-DB run.
    That cascade is OUT OF SCOPE for PRP-41 (it's a PRP-39/40 interaction
    bug); this test tolerates it by:

    - Requiring HTTP 200 + a terminal pipeline_complete event.
    - Requiring step_count >= 23 (the legacy showcase_rich headcount).
    - Requiring the PRP-41 contract shapes (`agent_hitl_flow` + `ops_snapshot`
      payload structure) WHEN those steps fired; SKIPping the assertion when
      they did not run because an earlier step failed fast.
    """
    import json

    body = json.dumps(
        {
            "seed": 42,
            "reset": True,
            "skip_seed": False,
            "scenario": "showcase_rich",
        }
    ).encode("utf-8")

    start = time.monotonic()
    req = urllib.request.Request(  # noqa: S310 — http://127.0.0.1 internal URL
        f"{DEMO_API_URL}/demo/run",
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=SHOWCASE_RICH_WALL_BUDGET_HARD_S) as resp:  # noqa: S310
            payload = resp.read()
            assert resp.status == 200, f"POST /demo/run -> {resp.status}"
    except urllib.error.HTTPError as exc:
        raise AssertionError(f"POST /demo/run failed: HTTP {exc.code} body={exc.read()!r}") from exc
    wall = time.monotonic() - start
    result = json.loads(payload)

    if wall > SHOWCASE_RICH_WALL_BUDGET_HARD_S:
        pytest.fail(
            f"showcase_rich full epic exceeded HARD budget: "
            f"{wall:.1f}s > {SHOWCASE_RICH_WALL_BUDGET_HARD_S:.0f}s"
        )

    by_name = {s["step_name"]: s for s in result["steps"]}

    # ---- PRP-41 — agent_hitl_flow contract (when the step ran) -----------
    hitl = by_name.get("agent_hitl_flow")
    if hitl is not None:
        assert hitl["status"] in {"pass", "skip"}, (
            f"agent_hitl_flow unexpected status={hitl['status']!r} detail={hitl['detail']!r}"
        )
        if hitl["status"] == "pass":
            # When the LLM key is configured, the data carries the approval decision.
            assert hitl["data"].get("approval_decision") in {
                "executed",
                "rejected",
                "expired",
            }
            assert isinstance(hitl["data"].get("session_id"), str)

    # ---- PRP-41 — ops_snapshot contract (when the step ran) --------------
    ops = by_name.get("ops_snapshot")
    if ops is not None:
        assert ops["status"] in {"pass", "warn"}, (
            f"ops_snapshot unexpected status={ops['status']!r} detail={ops['detail']!r}"
        )
        for key in (
            "stale_aliases_count",
            "retraining_candidates_count",
            "total_runs",
            "total_aliases",
            "degrading_health_count",
        ):
            assert key in ops["data"], f"ops_snapshot missing KPI key {key!r}"
            assert isinstance(ops["data"][key], int) and ops["data"][key] >= 0

    # ---- #324 — the safer-promote cascade is fixed --------------------------
    # The KNOWN_PREEXISTING_FAILURES tolerance for scenario_simulate_and_save is
    # removed: it now resolves the champion via ctx.winning_run_id (not the
    # safer-promote-corrupted alias) and MUST pass.
    scenario_step = by_name.get("scenario_simulate_and_save")
    assert scenario_step is not None, "scenario_simulate_and_save did not run on showcase_rich"
    assert scenario_step["status"] == "pass", (
        "scenario_simulate_and_save must pass after #324, got "
        f"status={scenario_step['status']!r} detail={scenario_step['detail']!r}"
    )

    # ---- PR1 (PRP-42, #329) — knowledge phase must never hard-fail -----------
    # The embedding-provider knowledge steps now SKIP gracefully whether the
    # provider is truly unreachable OR rejects an invalid/placeholder key (the
    # 401/403 -> EMBEDDING_AUTH classification, RUNBOOKS 20-22). They may pass
    # (provider reachable + corpus matches), skip (unreachable / bad key), or
    # warn (retrieve indexed but found no hits) -- but they must NOT fail.
    KNOWLEDGE_STEPS = {"rag_index_subset", "rag_retrieve_probe"}
    for name in KNOWLEDGE_STEPS:
        step = by_name.get(name)
        if step is not None:
            assert step["status"] in {"pass", "skip", "warn"}, (
                f"{name} must skip/warn gracefully on an unreachable/invalid "
                f"embedding key (#329), got status={step['status']!r} "
                f"detail={step['detail']!r}"
            )

    # No step may hard-fail on showcase_rich now: #324 is fixed and the
    # knowledge phase skips instead of 401/502-failing. Any fail is a regression.
    failed = [s for s in result["steps"] if s["status"] == "fail"]
    assert not failed, "unexpected showcase_rich failure(s): " + ", ".join(
        f"{s['step_name']!r} (detail={s['detail']!r})" for s in failed
    )
    assert result["overall_status"] == "pass", (
        f"no failed steps but overall_status={result['overall_status']!r}"
    )


@pytest.mark.integration
def test_run_demo_precondition_failure_exits_2() -> None:
    """A bogus API URL surfaces as a precondition failure with exit 2.

    Verifies the script does NOT silently exit 0 when the backend is
    unreachable — a behaviour we lean on in the integration fixture
    above and that users rely on locally when they forget to start
    uvicorn.
    """
    result = subprocess.run(  # noqa: S603 — internal command, trusted args
        [
            UV_BIN,
            "run",
            "python",
            "scripts/run_demo.py",
            "--api-url",
            "http://127.0.0.1:1",  # almost certainly unbound
            "--timeout",
            "2",
            "--quiet",
        ],
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
        timeout=30.0,
        check=False,
    )
    assert result.returncode == 2, (
        f"expected exit 2 on unreachable API; got {result.returncode}\n"
        f"stdout={result.stdout!r}\nstderr={result.stderr!r}"
    )
