# ADR Index

This index tracks Architecture Decision Records (ADRs) for **ForecastLabAI / ForecastOps**.

**Rules**
- ADRs are append-only: do not rewrite history. If a decision changes, add a new ADR and mark the old one as **Superseded**.
- Keep ADRs concise (ideally 1–2 pages).

| ADR ID | Title | Status | Date | One-line Decision |
|---|---|---:|---:|---|
| ADR-0001 | ADR Template | Proposed | 2026-01-26 | Standard ADR format for this repository |
| ADR-0002 | Frontend Architecture: Vite SPA first | Accepted | 2026-01-26 | Use Vite SPA for Phase-0/Phase-1; revisit Next.js later |
| ADR-0003 | Vector Storage: pgvector in PostgreSQL | Accepted | 2026-01-26 | Store embeddings and similarity search in Postgres via pgvector |
| ADR-0004 | (TBD) Data grain and uniqueness constraints | Proposed | 2026-01-26 | Define canonical grains per fact table (e.g., sales_daily) |
| ADR-0005 | (TBD) Backtesting protocol | Proposed | 2026-01-26 | Standardize rolling/expanding window backtests (no random splits) |
