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
.PHONY: help demo demo-quick demo-clean docker-up docker-up-gpu docker-down

help:  ## show this help and exit
	@echo "ForecastLabAI Make targets:"
	@echo "  make demo          run the full end-to-end demo (~90-180 s)"
	@echo "  make demo-quick    re-run the demo without re-seeding"
	@echo "  make demo-clean    wipe the DB, then run the full demo"
	@echo "  make docker-up     bring the full stack up in containers (no GPU)"
	@echo "  make docker-up-gpu bring the full stack up with Ollama on GPU"
	@echo "  make docker-down   stop containers (keeps named volumes)"
	@echo ""
	@echo "Preconditions for the demo targets:"
	@echo "  * docker compose Postgres+pgvector must be reachable on :5433"
	@echo "  * uvicorn must already be serving on http://localhost:8123"
	@echo "    (start with: uv run uvicorn app.main:app --port 8123)"
	@echo ""
	@echo "Preconditions for the docker targets:"
	@echo "  * docker + docker compose v2 installed; `.env` populated"
	@echo "    (`cp .env.example .env`)."

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

docker-up:  ## bring the full stack up in containers (no GPU)
	docker compose up -d --wait --wait-timeout 90

docker-up-gpu:  ## bring the full stack up with Ollama on GPU
	docker compose -f docker-compose.yml -f docker-compose.gpu.yml --profile gpu up -d --wait --wait-timeout 120

docker-down:  ## stop and remove containers (keeps named volumes)
	docker compose down
