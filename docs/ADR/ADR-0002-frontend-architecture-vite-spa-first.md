# ADR-0002: Frontend Architecture — Vite SPA First

- Status: Accepted
- Date: 2026-01-26

## Context
ForecastLabAI needs a modern dashboard to showcase data exploration, model runs, training/prediction actions, and RAG Q&A.
For a portfolio repository, the priority is:
- fast iteration
- simple deployment
- minimal framework overhead
- clear separation of concerns (API vs UI)

A Next.js full-stack approach is attractive but introduces additional complexity (routing conventions, server rendering choices, API route overlap, deployment knobs) that is not required for Phase-0/Phase-1 goals.

## Decision
Use **Vite** to build a **React SPA dashboard** for Phase-0/Phase-1.

- UI consumes the backend via a configurable base URL (e.g., `VITE_API_BASE_URL`).
- Table-heavy pages use shadcn/ui Data Table pattern (TanStack Table).
- Backend remains the single source of truth for business logic and data access.

## Alternatives Considered
1) **Next.js**
   - Pros: full-stack React, SSR/SSG options, built-in routing and API routes, strong ecosystem.
   - Cons: higher architectural surface area; SSR/SSG decisions are not needed for a portfolio analytics UI; can blur boundaries with FastAPI.

2) **Vite SPA (selected)**
   - Pros: minimal boilerplate, fast dev server, clear separation (FastAPI API), straightforward deployment.
   - Cons: no SSR/SSG out of the box; SEO not a concern for this internal-style dashboard.

## Consequences
- Positive:
  - Faster implementation of portfolio-visible UI features (tables, filters, actions).
  - Clear API-first architecture aligned with typed FastAPI contracts.
- Negative / Risks:
  - If we later need SSR/SSG or server-side routing semantics, migration to Next.js will require rework.
- Mitigations:
  - Keep API contracts stable and well-typed (OpenAPI + Pydantic schemas).
  - Keep UI logic thin; avoid embedding business rules in the frontend.

## Links
- INITIAL: `INITIAL-8.md` (Dashboard), `INITIAL-7.md` (FastAPI Contracts)
- PRP: (to be created) `docs/PRP/PRP-frontend-dashboard.md`
