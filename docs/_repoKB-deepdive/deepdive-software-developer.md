# Deep Dive: Software Developer

## Scope

This document studies ForecastLabAI as a working developer would: how to navigate it, how the backend and frontend are wired, which files matter first, how to add features safely, and where the sharp edges are.

## 1. Research

### First impression of the repo

ForecastLabAI is not a starter template. It is a broad working application with:

- a slice-based FastAPI backend
- a route-rich React frontend
- an end-to-end demo path
- ML, RAG, and agent workflows
- real migrations and tests

The repo is large, but its structure is disciplined enough that a developer can move with confidence if they follow local patterns.

### High-value entrypoints

For a developer, these are the first files worth reading:

- `AGENTS.md`
- `pyproject.toml`
- `frontend/package.json`
- `app/main.py`
- `app/core/config.py`
- `app/core/database.py`
- `frontend/src/App.tsx`
- `frontend/src/lib/api.ts`

These files define the rules, the stack, the app wiring, and the transport contract.

### Backend development model

The backend is organized around vertical slices under `app/features/`. Each slice typically owns:

- route handlers
- schemas
- business/service logic
- persistence models when needed
- tests

This is the key implementation rule: do not start by asking "which helper can I invent?" Start by asking "which slice owns this behavior?"

### Backend slice inventory

The repo currently contains these major backend feature areas:

- analytics
- agents
- backtesting
- batch
- config
- data_platform
- demo
- dimensions
- explainability
- featuresets
- forecasting
- ingest
- jobs
- model_selection
- ops
- rag
- registry
- scenarios
- seeder

### Frontend development model

The frontend is structured by workflow:

- pages under `frontend/src/pages/*`
- reusable components under `frontend/src/components/*`
- API/state hooks under `frontend/src/hooks/*`
- transport and utility helpers under `frontend/src/lib/*`

That means the usual page implementation path is:

1. page composes the workflow
2. hooks fetch and mutate data
3. components render domain-specific UI
4. helpers format or transform data

### API access pattern

`frontend/src/lib/api.ts` is the frontend transport seam. It:

- builds URLs from `VITE_API_BASE_URL`
- serializes JSON request bodies
- parses JSON and `application/problem+json`
- throws typed `ApiError` failures

This is important because frontend fixes should generally use this helper instead of raw fetches.

### React Query pattern

Hooks such as `frontend/src/hooks/use-model-selection.ts` show the preferred pattern:

- one hook per query or mutation
- stable `queryKey`s
- mutation success invalidation or cache seeding
- polling only where workflow state requires it

This keeps page components focused on state transitions and rendering.

### WebSocket pattern

`frontend/src/hooks/use-websocket.ts` wraps:

- connection status
- JSON message parsing
- reconnect logic
- send/disconnect/reconnect helpers

That avoids scattering WebSocket lifecycle logic through pages like `chat.tsx` and `showcase.tsx`.

### Testing footprint

Observed from repo inspection:

- 328 Python files under `app/`
- 176 backend test files
- 229 frontend TS/TSX files
- 57 frontend test files

This is a repo where tests are part of the implementation surface. A developer should expect to touch them.

## 2. Compose A Role-Based Plan

### Developer onboarding plan

Recommended order:

1. read `AGENTS.md`
2. read `README.md`
3. inspect `app/main.py`
4. inspect `frontend/src/App.tsx`
5. pick one backend slice end to end
6. pick one frontend workflow end to end
7. inspect the matching tests

### Safe change plan

When implementing anything non-trivial:

1. find the owner slice or page workflow
2. read route, schema, service, and tests together
3. inspect adjacent frontend code if the change is user-visible
4. reuse existing helper patterns
5. add or update tests before calling the work done

### Backend change workflow

For endpoint or service changes:

1. inspect `routes.py`
2. inspect `schemas.py`
3. inspect `service.py`
4. inspect relevant `models.py`
5. inspect `tests/`
6. patch the narrowest owning surface

### Frontend change workflow

For UI or workflow changes:

1. inspect page component
2. inspect relevant hook
3. inspect domain component
4. inspect utility/helper module if any
5. inspect matching tests
6. patch the narrowest surface

### When to use `core` or `shared`

Move code to `app/core/` only when it is truly cross-cutting platform behavior:

- config
- logging
- database/session
- middleware
- error handling

Move code to `app/shared/` when multiple slices need the same pure or semi-pure logic. Forecast feature-frame logic is a good example of this pattern.

### Developer risk map

Handle these areas carefully:

- `app/main.py`
- `app/core/database.py`
- `app/core/problem_details.py`
- `app/features/featuresets/tests/test_leakage.py`
- `alembic/versions/*`

These are high-blast-radius files or rules.

## 3. Validate

### Evidence that the repo is developer-friendly

- Commands are clearly documented.
- Stack configuration is centralized.
- Slice structure is consistent.
- There are many examples of the preferred patterns.
- Frontend transport is standardized.
- WebSocket behavior is abstracted.
- Quality gates are explicit and strict.

### Backend sharp edges

1. Import cycles between slices can happen; some services already use lazy imports to avoid them.
2. Long-running work may be triggered from API-managed workflows.
3. Artifact and run compatibility rules span multiple slices.
4. Time-safety requirements make "small" ML changes riskier than they first appear.

### Frontend sharp edges

1. Polling workflows can hide backend state assumptions.
2. Route-level UX often depends on specific backend response fields.
3. WebSocket flows need careful streaming and terminal-state handling.
4. Multiple advanced pages can share subtle utility logic.

### Practical verification habits

For backend:

- run relevant slice tests first
- run integration tests if schema or DB behavior changed
- verify error paths still return RFC 7807 responses

For frontend:

- run the nearest component or utility tests first
- verify page behavior against the real endpoint contract
- check loading, empty, success, and error states

For cross-stack:

- verify request/response field names exactly
- verify polling and WebSocket state transitions
- verify any new config field is reflected end to end

## 4. Generate

## Generated Developer Findings

### Best mental model

The repo is easiest to work in when you think in workflows, not just files. The backend slices and frontend pages are different projections of the same product flows.

### Biggest strengths for day-to-day development

1. consistent backend slice architecture
2. consistent frontend route and hook layering
3. strong validation gates
4. real examples of nearly every pattern you need
5. explicit local-first runtime story

### Biggest developer risks

1. changing shared forecasting assumptions without updating downstream consumers
2. breaking import-order or dependency assumptions in backend slices
3. drifting frontend expectations away from backend contracts
4. under-testing changes that touch AI, ML, or orchestration surfaces

### Recommended developer heuristics

1. Stay inside the owner slice until forced out.
2. Treat tests as part of the design.
3. Prefer additive schema changes over broad rewrites.
4. Inspect the workflow end to end before patching.
5. Respect the repo's invariants: time-safety, migrations, strict typing, RFC 7807, approval-gated mutation.

### Final developer view

ForecastLabAI is broad but navigable. It rewards disciplined developers who follow established seams and punishes casual cross-cutting edits. The fastest correct path is to read the owner slice, read its tests, and change the smallest coherent unit.
