# INITIAL-0.md — ForecastLabAI / ForecastOps — Overview

## FEATURE:
Build a portfolio-ready end-to-end retail analytics system:
- Retail data platform (multi-table mini warehouse)
- Forecasting + backtesting (ForecastOps)
- Typed FastAPI serving layer
- Dashboard (shadcn/ui Data Table)
- RAG assistant (pgvector) + optional PydanticAI agent workflows

Core principle: **no hardcoding**. Everything configurable via Settings/env + validated API payloads + per-run configs.

## EXAMPLES:
- examples/seed_demo_data.py — synthetic multi-store dataset generation (parametrized)
- examples/e2e_smoke.sh — compose up → migrate → seed → train → predict → query
- examples/api/*.http — ingest/train/predict endpoints usage with variables
- examples/dashboard_screenshots/* — portfolio evidence

## DOCUMENTATION:
- /docs/ARCHITECTURE.md
- /docs/ADR/*
- FastAPI, Pydantic v2, SQLModel/SQLAlchemy, Alembic
- Postgres + pgvector
- scikit-learn
- shadcn/ui + TanStack Table
- PydanticAI (optional)

## OTHER CONSIDERATIONS:
- Time-series leakage prevention is non-negotiable
- Idempotent ingest (replay-safe)
- Model registry must support reproducibility (config + data window + artifact + metrics + git SHA)
- RAG must return citations or “not found”
