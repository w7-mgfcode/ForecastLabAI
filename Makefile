# ForecastLabAI — operator-friendly entry points.
#
# This Makefile is a thin wrapper around the existing CLI / docker-compose
# tooling. It exists so a reviewer can run the full end-to-end demo with
# one command: `make demo`. The heavy lifting happens in
# `scripts/run_demo.py` (PRP-15); the rules here just orchestrate the
# prerequisites.
#
# Conventions:
#   * Tab indentation on recipe lines (`make` requires it).
#   * Every target is `.PHONY` (no real file outputs).
#   * `uv run` prefixes every Python invocation (CLAUDE.md "Commands").
#
# Quick reference:
#   make demo        — full e2e: docker compose + migrations + run_demo
#   make demo-quick  — re-run run_demo without re-seeding (fast iteration)
#   make demo-clean  — destructive: wipe DB first, then run demo
#   make help        — list available targets

.DEFAULT_GOAL := help
.PHONY: help demo demo-quick demo-clean

help:  ## show this help and exit
	@echo "ForecastLabAI Make targets:"
	@echo "  make demo        run the full end-to-end demo (~90-180 s)"
	@echo "  make demo-quick  re-run the demo without re-seeding"
	@echo "  make demo-clean  wipe the DB, then run the full demo"
	@echo ""
	@echo "Preconditions for all targets:"
	@echo "  * docker compose Postgres+pgvector must be reachable on :5433"
	@echo "  * uvicorn must already be serving on http://localhost:8123"
	@echo "    (start with: uv run uvicorn app.main:app --port 8123)"

demo:  ## full e2e — seed -> features -> train x3 -> backtest -> register -> agent
	docker compose up -d
	uv run alembic upgrade head
	uv run python scripts/run_demo.py --seed 42

demo-quick:  ## re-run the demo without re-seeding (fast iteration)
	uv run python scripts/run_demo.py --seed 42 --skip-seed

demo-clean:  ## destructive — wipe DB then run the full demo
	docker compose up -d
	uv run alembic upgrade head
	uv run python scripts/run_demo.py --seed 42 --reset
