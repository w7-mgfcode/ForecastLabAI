"""Integration tests for the dockerized full stack (PRP-32).

Verifies the four-service Compose stack (`postgres`, `backend`, `frontend`,
opt-in `ollama`) brought up by `make docker-up`:

  * `test_docker_stack_services_healthy` — `docker compose ps --format json`
    reports `Health: healthy` for postgres / backend / frontend. Ollama is
    asserted only when `DOCKER_STACK_GPU=1` is also set (gpu profile run).

  * `test_backend_can_reach_postgres_via_internal_dns` — `docker compose exec
    -T backend python -c …` opens a socket to `postgres:5432` (the in-cluster
    DNS name, NOT the host-published localhost:5433), confirming the network
    alias and the long-form depends_on health gate both work.

  * `test_no_hardcoded_localhost_for_internal_services` — guards the
    "no localhost for cross-container hops" invariant: greps `app/**/*.py`
    for `localhost:5433` or `localhost:11434`. `app/core/config.py` is
    allow-listed because it legitimately holds host-mode defaults.

Gated by `DOCKER_STACK_TEST=1` so the existing CI flow (GitHub Actions
`services: postgres:` containers, not docker compose) stays untouched.

To run after `make docker-up`:

    DOCKER_STACK_TEST=1 uv run pytest -v -m integration tests/test_docker_stack.py
"""

from __future__ import annotations

import json
import os
import pathlib
import re
import shutil
import subprocess
from typing import TypedDict

import pytest

# Module-level skip: only run when the operator explicitly opts in. The third
# test (no_hardcoded_localhost) is a pure static check and could run without
# the stack up — but keeping the whole module behind one switch keeps the
# "stack tests" mental model consistent.
pytestmark = pytest.mark.skipif(
    os.environ.get("DOCKER_STACK_TEST") != "1",
    reason="set DOCKER_STACK_TEST=1 to run after `make docker-up`",
)

# Resolve `docker` to an absolute path so ruff's S607 stays happy and so the
# subprocess doesn't rely on PATH lookup at exec time.
DOCKER_BIN: str = shutil.which("docker") or "docker"

REPO_ROOT: pathlib.Path = pathlib.Path(__file__).resolve().parents[1]


class ComposePsRow(TypedDict):
    """Shape of one row from `docker compose ps --format json` (JSON-LINES).

    Fields are stable across Compose v2.27+ and v5.x. `Health` is the empty
    string for services without a healthcheck — never `null` — so this stays
    `str` rather than `str | None`.
    """

    Service: str
    State: str
    Health: str
    Name: str


def _compose_ps_rows() -> dict[str, ComposePsRow]:
    """Return one ComposePsRow per service, keyed by Service.

    Critical: `docker compose ps --format json` emits JSON-LINES (one object
    per line), NOT a single JSON array — verified on Docker Compose v5.1.3
    on the dev host. Parse line-by-line; `json.loads(stdout)` would error on
    multi-row output.
    """
    proc = subprocess.run(  # noqa: S603 — internal, trusted args
        [DOCKER_BIN, "compose", "ps", "--format", "json"],
        capture_output=True,
        text=True,
        check=True,
        timeout=30,
        cwd=str(REPO_ROOT),
    )
    rows: list[ComposePsRow] = [
        json.loads(line) for line in proc.stdout.splitlines() if line.strip()
    ]
    return {row["Service"]: row for row in rows}


@pytest.mark.integration
def test_docker_stack_services_healthy() -> None:
    """`postgres`, `backend`, `frontend` all report `Health: healthy`.

    Ollama is opt-in via the `gpu` profile; only asserted when the operator
    sets `DOCKER_STACK_GPU=1`, which signals they brought the stack up via
    `make docker-up-gpu` against a host with `nvidia-container-runtime`.
    """
    by_service = _compose_ps_rows()

    missing = {"postgres", "backend", "frontend"} - set(by_service)
    assert not missing, (
        f"compose ps is missing services: {missing} — bring the stack up "
        f"with `make docker-up` first. Got: {sorted(by_service)}"
    )

    for svc in ("postgres", "backend", "frontend"):
        row = by_service[svc]
        assert row["Health"] == "healthy", (
            f"{svc} is not healthy: State={row.get('State')!r} "
            f"Health={row.get('Health')!r}. Check `docker compose logs {svc}`."
        )

    if os.environ.get("DOCKER_STACK_GPU") == "1":
        assert "ollama" in by_service, (
            "DOCKER_STACK_GPU=1 set, but ollama service is absent — "
            "bring it up with `make docker-up-gpu`."
        )
        assert by_service["ollama"]["Health"] == "healthy", (
            f"ollama is not healthy: {by_service['ollama']}"
        )


@pytest.mark.integration
def test_backend_can_reach_postgres_via_internal_dns() -> None:
    """`backend` resolves `postgres:5432` over the compose network."""
    # `-T` disables TTY allocation — required when exec'ing from pytest, or
    # docker errors with "the input device is not a TTY". Verified.
    proc = subprocess.run(  # noqa: S603 — internal, trusted args
        [
            DOCKER_BIN,
            "compose",
            "exec",
            "-T",
            "backend",
            "python",
            "-c",
            ("import socket; socket.create_connection(('postgres', 5432), timeout=2).close()"),
        ],
        capture_output=True,
        text=True,
        timeout=15,
        check=False,
        cwd=str(REPO_ROOT),
    )
    assert proc.returncode == 0, (
        f"backend could not reach postgres:5432 over the compose network.\n"
        f"stdout={proc.stdout!r}\nstderr={proc.stderr!r}"
    )


@pytest.mark.integration
def test_no_hardcoded_localhost_for_internal_services() -> None:
    """Locks in "no `localhost` for cross-container hops".

    Greps every `*.py` under `app/` (excluding tests) for `localhost:5433`
    or `localhost:11434`. The single allow-listed file is
    `app/core/config.py`, which legitimately holds host-mode defaults read
    by `pydantic-settings` when no env override is set.
    """
    allowed = {REPO_ROOT / "app" / "core" / "config.py"}
    pattern = re.compile(r"localhost:(?:5433|11434)")

    offenders: list[str] = []
    for path in (REPO_ROOT / "app").rglob("*.py"):
        if path in allowed:
            continue
        # Skip test files — they are free to spin up local services on those
        # exact ports for fixture purposes (e.g. tests/test_e2e_demo.py's
        # socket probe against :5433).
        rel = path.relative_to(REPO_ROOT).as_posix()
        if "/tests/" in rel or path.name.startswith("test_"):
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        for line_no, line in enumerate(text.splitlines(), start=1):
            if pattern.search(line):
                offenders.append(f"{rel}:{line_no}: {line.strip()}")

    assert not offenders, (
        "Found hardcoded `localhost:5433` or `localhost:11434` in app/ files "
        "outside the allow-list (only app/core/config.py may carry host-mode "
        "defaults). Move them to settings + override via the container "
        "`environment:` block.\nOffenders:\n  " + "\n  ".join(offenders)
    )
