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
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )

    try:
        if not _wait_for_health(UVICORN_BOOT_TIMEOUT_S):
            proc.terminate()
            try:
                proc.wait(timeout=5.0)
            except subprocess.TimeoutExpired:
                proc.kill()
            pytest.skip(
                f"uvicorn did not become healthy on {DEMO_API_URL} within "
                f"{UVICORN_BOOT_TIMEOUT_S:.0f}s — check that migrations ran"
            )
        yield proc
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=5.0)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait(timeout=5.0)


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
            "--timeout",
            "60",
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
