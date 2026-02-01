# ADR-0002: Frontend Architecture — Vite SPA First

- Status: Implemented
- Date: 2026-01-26
- Updated: 2026-02-01

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

## Implementation

The frontend was scaffolded in `frontend/` with:

- **React 19** + TypeScript 5.9 (strict mode)
- **Vite 7** with `@tailwindcss/vite` plugin
- **Tailwind CSS 4** (new `@import "tailwindcss"` syntax)
- **shadcn/ui** (New York style) with 26 pre-installed components
- **TanStack Query** + **TanStack Table** for data management
- **React Router 7** for client-side routing
- **Recharts** for data visualization

Path aliases (`@/`) configured in both `tsconfig.json` and `vite.config.ts`.
API proxy configured to forward `/api/*` requests to `http://localhost:8123`.

## Links
- INITIAL: `INITIAL-11A.md` (Frontend Setup), `INITIAL-11B.md` (Architecture), `INITIAL-11C.md` (Pages)
- PRP: `PRPs/PRP-11A-frontend-setup.md`
