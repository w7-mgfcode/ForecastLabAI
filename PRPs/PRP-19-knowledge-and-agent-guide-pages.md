name: "PRP-19 — Knowledge page + Agent Guide page (in-product self-documentation)"
description: |
  Add two new React pages to the ForecastLabAI dashboard, frontend-led and
  fully additive:

  1. **Knowledge** (`/knowledge`) — presents, in detail, *what ForecastLabAI
     currently knows*: the RAG knowledge base (indexed sources + a live semantic
     search box) plus a summary of the live system state the agents can query
     (seeded data, registered model runs, deployment aliases).
  2. **Agent Guide** (`/guide`) — explains, in detail, *how to use the Chat
     agents*: the two agent types, their tools, the human-in-the-loop approval
     flow, session limits, the streaming protocol, and copy-paste example prompts.

  Frontend-led, with one small additive backend change: the existing
  `GET /config/ai` response gains read-only agent-limit fields so the Guide
  shows session limits live. No new backend slice, no migration, no new env var.
  Every other endpoint these pages consume already exists with a frontend hook.

## Purpose
Close the in-product self-documentation gap. Today a dashboard visitor can open
`/chat` and talk to an agent, but nothing in the UI tells them (a) what the
RAG assistant actually has indexed to answer from, or (b) how the agents work,
what they can do, or how the approval gate behaves. The two pages turn implicit
system knowledge into a visible, browsable surface — a natural onboarding pair:
**Knowledge** = "what it knows" → **Agent Guide** = "how to ask it".

> **PRP numbering:** `PRP-16` is reserved (Phase-2 LightGBM, per PRP-15).
> `PRP-17` (Showcase) and `PRP-18` (AI Model console) are used. This is `PRP-19`.

## Core Principles
1. **Context is King** — every endpoint shape, hook name, schema field, and
   pattern referenced below is linked to a real source file + line.
2. **Reuse existing patterns** — both pages are lazy routes registered exactly
   like `Showcase` (PRP-17); data comes through existing TanStack Query hooks
   (`useRagSources`, `useSeederStatus`, `useAIConfig`, …); UI uses existing
   shadcn primitives (`Card`, `Badge`, `Input`, `Tabs`, `Button`). No new
   streaming primitive, no new fetch wrapper.
3. **Additive only** — no new backend slice, no Alembic migration, no new
   `.env` var. The one backend change is additive: read-only agent-limit fields
   appended to the existing `AIModelConfig` (`GET /config/ai`) response. Plus
   one new hook (`useRetrieve`), three new TS interfaces, two new pages, one
   pure-helper module.
4. **Read-only, no duplication** — the Knowledge page is *presentational*. It
   does NOT duplicate Admin's RAG management (index / delete) — those stay in
   `frontend/src/pages/admin.tsx`. It adds the semantic-search exploration that
   Admin lacks.
5. **Strict gates honored** — `pnpm tsc --noEmit` + `pnpm lint` + `pnpm test`
   green; AND because the `config` slice `.py` files change, the repo-wide
   `ruff`/`mypy`/`pyright`/`pytest` CI jobs must be run and stay green — the
   `/config/ai` change ships with `config` slice tests.
6. **UI through skills** — pages built via `frontend-design` + `shadcn-ui` and
   dogfooded via `webapp-testing` / `agent-browser` per `.claude/rules/ui-design.md`.
   A green type-check is NOT proof the UI works.

---

## Goal
Two new nav items route to two new pages.

**`/knowledge` — Knowledge**
- A **Knowledge Base** section: `total_sources` / `total_chunks` summary, a
  read-only list of every indexed RAG source (path, type badge, chunk count,
  indexed date), and a **semantic search box** that POSTs to `/rag/retrieve`
  and renders the matching chunks with relevance scores + source citations.
- A **Live System State** section: the seeded-data summary (stores / products /
  sales / date range), the count of registered model runs, and the deployment
  aliases — i.e. what the *experiment* agent can query through its tools.
- A short explainer tying it together: "the RAG assistant answers from the
  Knowledge Base; the experiment agent acts on the Live System State."

**`/guide` — Agent Guide**
- Describes the **two agents** (`rag_assistant`, `experiment`), each with its
  purpose, its exact tool names, and what it returns.
- Walks through **how a chat session works**: pick agent → Start Session →
  send a message → streamed text + tool-call chips → approval prompts →
  New Session.
- Explains the **human-in-the-loop approval gate** (`create_alias`,
  `archive_run`).
- Lists **session limits** (token budget, tool-call cap, timeout, TTL, retries)
  — rendered **live** from `/config/ai`, which is extended to return them.
- Gives **copy-paste example prompts** per agent.
- Surfaces the **currently configured agent model** (live, from `/config/ai`)
  and links to Chat and Admin → AI Models.
- Reachable both from a flat top-level nav item AND from a help link on the
  Chat page.

## Why
- **Portfolio identity.** `.claude/rules/product-vision.md` principle 1 —
  "portfolio-grade, end-to-end … every phase ships working code". The agentic
  layer (PRP-10) and RAG layer (PRP-9) are fully built but invisible as
  *capabilities* — a reviewer has to read code to learn what the agents do.
- **Onboarding.** A first-time user opening `/chat` has no idea what to ask the
  RAG assistant (it can only answer from indexed docs) or that the experiment
  agent can run real backtests. These two pages remove that guesswork.
- **Low-cost surface.** Almost everything needed already exists server-side;
  the only backend work is a small additive `/config/ai` extension. This is
  high-value-per-line work: mostly composition of shipped endpoints into two
  polished pages.

## What
Frontend-led. Two lazy-loaded pages mirroring the `Showcase` registration
(PRP-17), two new `ROUTES` entries, two `NAV_ITEMS` entries, a help link to
`/guide` on the Chat page, one new mutation hook (`useRetrieve` for
`POST /rag/retrieve`), three new TS interfaces, and one pure-helper module with
a vitest. Plus one additive backend change: the `config` slice's `AIModelConfig`
schema + `get_effective_config` service gain read-only agent-limit fields
(`agent_max_tool_calls`, `agent_timeout_seconds`, `agent_retry_attempts`,
`agent_session_ttl_minutes`, `agent_require_approval`) so the Guide's limits are
live; shipped with `config` slice tests. No migration, no new env var.

### Success Criteria
- [ ] `GET /knowledge` in the running SPA renders the Knowledge Base section
      (source list + summary) and the Live System State section.
- [ ] The semantic search box on `/knowledge` POSTs `/rag/retrieve` and renders
      `ChunkResult`s with a relevance score; an empty query is rejected client-side;
      a `502` (no embedding provider) shows a graceful "search unavailable" state
      while the source list still renders.
- [ ] An empty knowledge base shows a friendly empty state pointing at
      Admin → RAG Sources (not a crash, not a blank card).
- [ ] `GET /guide` renders both agent cards with the **exact** tool names from
      the agent definitions, the approval-gate explainer, the example prompts,
      and the session limits + agent model rendered **live** from `/config/ai`.
- [ ] Both pages appear in the top nav (desktop + mobile sheet) and in `App.tsx`
      as lazy `<Route>`s wrapped in `<Suspense>`; the Chat page links to `/guide`.
- [ ] `cd frontend && pnpm tsc --noEmit && pnpm lint && pnpm test --run` all clean.
- [ ] `frontend/src/lib/knowledge-utils.test.ts` passes (pure-helper coverage).
- [ ] `GET /config/ai` returns the five additive agent-limit fields; the `config`
      slice tests (`test_schemas.py`/`test_service.py`/`test_routes.py`) cover
      them and `ruff`/`mypy`/`pyright`/`pytest` stay green.
- [ ] Only the `config` slice changes server-side; no Alembic migration; no
      `.env`/`.env.example` var.
- [ ] Admin's RAG index/delete management is untouched and NOT duplicated.
- [ ] Both pages dogfooded in a real browser (screenshot captured).

---

## All Needed Context

### Documentation & References
```yaml
- url: https://tanstack.com/query/latest/docs/framework/react/guides/queries
  why: useQuery (GET) vs useMutation (POST) — the Knowledge search is a mutation
  critical: |
    GET data → useQuery({ queryKey, queryFn }). POST actions → useMutation({
    mutationFn }). The repo's hooks follow this exactly (see use-rag-sources.ts).
    Semantic search is a POST → a useMutation, NOT a useQuery.

- url: https://reactrouter.com/en/main/route/lazy
  why: react-router v6 route registration; the repo lazy-loads every page
  critical: Mirror App.tsx — `lazy(() => import('@/pages/x'))` + `<Suspense>`.

- file: PRPs/PRP-17-demo-showcase-page.md
  why: The most recent "add a new page" PRP. Its frontend tasks (constants +
    App.tsx + lazy route + nav entry) are the exact pattern to copy.
  critical: This PRP follows PRP-17's frontend half precisely; the only deltas
    are "two pages instead of one" and "no backend slice".

- file: frontend/src/App.tsx
  why: Lazy-route registration. Add `KnowledgePage` and `GuidePage` lazily and a
    `<Route path={ROUTES.KNOWLEDGE}>` / `<Route path={ROUTES.GUIDE}>` exactly
    like the existing `ShowcasePage` block (lines 12, 42-49).
  critical: Pages are `lazy(() => import(...))`; each route element is wrapped in
    `<Suspense fallback={<PageLoader />}>`.

- file: frontend/src/lib/constants.ts
  why: ROUTES + NAV_ITEMS. Add `KNOWLEDGE: '/knowledge'` and `GUIDE: '/guide'`
    to ROUTES, and two NAV_ITEMS entries.
  critical: |
    NAV_ITEMS is `as const`. Knowledge and Agent Guide are flat top-level items
    (not grouped). Place `Knowledge` after `Visualize` and `Agent Guide` after
    `Chat` so the nav reads: Dashboard · Showcase · Explorer · Visualize ·
    Knowledge · Chat · Agent Guide · Admin (a "know it → chat → how to chat"
    cluster). No new WS URL needed.

- file: frontend/src/pages/admin.tsx
  why: THE reference page. `RagSourcesPanel` (lines 116-253) already lists
    `/rag/sources` data — copy its source-row markup. `SeederPanel`'s `StatCard`
    (lines 769-785) is the data-summary tile to reuse on the Knowledge page.
  critical: |
    - admin.tsx keeps all sub-components in ONE file (RagSourcesPanel,
      AliasesPanel, SeederPanel, StatCard helpers). Mirror that: knowledge.tsx
      and guide.tsx each hold their own internal function components — do NOT
      create a components/knowledge/ directory.
    - The Knowledge page is READ-ONLY. Copy the source LIST markup but DROP the
      "Index Document" dialog and the per-row delete AlertDialog — those are
      management actions that stay in Admin.
    - Reuse loading/error states: `<LoadingState message=.../>` and
      `<ErrorDisplay error={error} onRetry={refetch} />`.

- file: frontend/src/hooks/use-rag-sources.ts
  why: Existing RAG hooks. `useRagSources()` (GET /rag/sources) is reused as-is.
    ADD a new `useRetrieve()` mutation hook here for POST /rag/retrieve.
  critical: |
    useRagSources already returns SourceListResponse. The new useRetrieve wraps
    `api<RetrieveResponse>('/rag/retrieve', { method: 'POST', body })`. It is a
    useMutation (no cache invalidation needed — search is ephemeral).

- file: frontend/src/lib/api.ts
  why: The `api<T>()` fetch wrapper + `ApiError` (carries the RFC 7807
    ProblemDetail) + `getErrorMessage()`.
  critical: |
    `api('/rag/retrieve', { method: 'POST', body: {...} })` JSON-encodes `body`.
    On non-2xx it throws `ApiError` with `.status` and `.detail`. The Knowledge
    search must catch this: `502` → "search unavailable, configure an embedding
    provider"; other → `getErrorMessage(err)`.

- file: app/features/rag/routes.py
  why: The RAG endpoints the Knowledge page consumes.
  critical: |
    - GET  /rag/sources   → SourceListResponse  (no embeddings needed — always works)
    - POST /rag/retrieve  → RetrieveResponse    (needs an embedding provider;
      returns 502 application/problem+json if embedding generation fails — see
      routes.py:214-224). The page must degrade gracefully on 502.

- file: app/features/rag/schemas.py
  why: AUTHORITATIVE wire shapes. Mirror these field-for-field into types/api.ts.
  critical: |
    RetrieveRequest (model_config = ConfigDict(extra="forbid") — send NOTHING
    extra): query:str(1..2000), top_k:int(1..50, default 5),
    similarity_threshold:float|null(0..1, default from settings — OMIT to use
    the server default), filters:dict|null.
    ChunkResult: chunk_id, source_id, source_path, source_type, content,
    relevance_score:float(0..1), metadata:dict|null.
    RetrieveResponse: results:ChunkResult[], query_embedding_time_ms:float,
    search_time_ms:float, total_chunks_searched:int.
    SourceResponse (already typed as `RagSource` in types/api.ts:157): source_id,
    source_type, source_path, chunk_count, content_hash, indexed_at, metadata.

- file: frontend/src/types/api.ts
  why: TS type surface. `RagSource` + `SourceListResponse` (lines 157-171),
    `AgentType` (line 199), `AIModelConfig`/`ProviderHealth` (lines 360-415)
    already exist. ADD `RetrieveRequest`, `ChunkResult`, `RetrieveResponse`
    near the `// === RAG ===` block (line 156).
  critical: snake_case field names on the wire — match the Pydantic models exactly.

- file: app/features/agents/agents/experiment.py
  why: The experiment agent's EXACT tool names + behavior for the Guide page.
  critical: |
    Tools (use these EXACT names on the Guide page): tool_list_runs,
    tool_get_run, tool_run_backtest, tool_compare_backtest_results,
    tool_compare_runs, tool_create_alias (REQUIRES APPROVAL),
    tool_archive_run (REQUIRES APPROVAL). The system prompt (lines 45-72)
    describes the workflow — paraphrase it, do not invent capabilities.

- file: app/features/agents/agents/rag_assistant.py
  why: The RAG assistant's EXACT tool names + behavior for the Guide page.
  critical: |
    Tools: tool_retrieve_context, tool_format_citations, tool_check_evidence,
    tool_list_sources. It answers ONLY from retrieved evidence, cites
    source_path:chunk_id, and says "I don't have enough information" when the
    knowledge base lacks coverage (system prompt lines 38-67).

- file: app/features/agents/agents/base.py
  why: Shared agent behavior + the approval helper for the Guide page.
  critical: |
    `requires_approval(name)` checks `settings.agent_require_approval`.
    SYSTEM_PROMPT_HEADER / SAFETY_INSTRUCTIONS (lines 269-294) state the safety
    contract — the Guide's "approval" section paraphrases SAFETY_INSTRUCTIONS.

- file: app/core/config.py
  why: The agent session limits to state on the Guide page (lines 147-172).
  critical: |
    Defaults to quote on the Guide (label them "default"): agent_max_tokens=4096,
    agent_max_tool_calls=10, agent_timeout_seconds=120, agent_retry_attempts=3,
    agent_require_approval=["create_alias","archive_run"],
    agent_session_ttl_minutes=120, agent_default_model="anthropic:claude-sonnet-4-5".
    The LIVE model is shown via /config/ai (useAIConfig) — the static numbers
    above are config defaults; phrase them as "default" since an operator can
    change them in Admin → AI Models.

- file: frontend/src/hooks/use-config.ts
  why: `useAIConfig()` (GET /config/ai) — the Guide page uses it to show the
    currently-configured agent model AND the (now live) session limits.
  critical: Reuse the hook as-is; do NOT add a config hook. The hook's response
    type `AIModelConfig` in types/api.ts gains the five new agent-limit fields.

- file: app/features/config/schemas.py
  why: `AIModelConfig` (GET /config/ai response, lines 65-83). Extend it with
    read-only agent-limit fields so the Guide renders limits live.
  critical: |
    ADD to AIModelConfig (NOT to AIModelConfigUpdate — these stay read-only,
    not operator-settable here): agent_max_tool_calls:int,
    agent_timeout_seconds:int, agent_retry_attempts:int,
    agent_session_ttl_minutes:int, agent_require_approval:list[str].
    agent_max_tokens is ALREADY present — do not re-add it.

- file: app/features/config/service.py
  why: `get_effective_config` (line 129) builds AIModelConfig from the Settings
    singleton. Populate the five new fields from `settings.*`.
  critical: The new fields are sourced from Settings exactly like the existing
    agent_* fields (app/core/config.py lines 147-172) — pure read, no DB, no
    migration. Mirror the existing `agent_max_tokens=settings.agent_max_tokens`
    line.

- file: app/features/config/tests/
  why: test_schemas.py / test_service.py / test_routes.py — extend each so the
    five new fields are covered (construction, service mapping from Settings,
    and the GET /config/ai route response). Required by test-requirements.md.

- file: frontend/src/pages/chat.tsx
  why: The actual chat flow the Guide page describes — keep the Guide accurate
    to it: pick agent in a Select → "Start Session" → type → stream → approval
    prompt → "New Session".
  critical: |
    Client → server WS frame is `{ session_id, message }`. Server → client
    events: text_delta, tool_call_start, tool_call_end, approval_required,
    complete, error (see types/api.ts:185-197 AgentEventType). Describe these
    accurately; do not invent event names.

- file: docs/_base/API_CONTRACTS.md
  why: Cross-check the /rag and /agents endpoint contracts + WS event list.
  critical: The "WebSocket Events (/agents/stream)" section is the source of
    truth for the Guide's streaming description.

- file: frontend/src/hooks/use-demo-pipeline.test.ts
  why: The vitest pattern — test PURE exported helpers (applyEvent,
    createInitialSteps), not the React component. `knowledge-utils.test.ts`
    mirrors this.

- file: frontend/src/lib/date-utils.ts  &  frontend/src/lib/status-utils.ts
  why: Precedent for a `lib/*.ts` pure-helper module. `knowledge-utils.ts` joins
    them — pure functions, no React, easy to unit-test.

- file: frontend/src/hooks/use-runs.ts  &  frontend/src/hooks/use-seeder.ts
  why: The Live System State section reuses these. use-seeder.ts exports
    `useSeederStatus()` (GET /seeder/status → SeederStatus). use-runs.ts exports
    the runs + aliases hooks used by admin.tsx (`useAliases`) and
    explorer/runs.tsx.
  critical: VERIFY the exact export names in use-runs.ts before wiring — reuse
    whatever it exports for runs (paginated) + aliases; do not add new hooks.

- file: .claude/rules/ui-design.md
  why: UI built/dogfooded via frontend-design + shadcn-ui + webapp-testing.
- file: .claude/rules/output-formatting.md
  why: If the Guide uses status glyphs, reuse the ✅/⚠️/⏭️ vocabulary.
- file: .claude/rules/test-requirements.md
  why: New TS component owning non-trivial state SHOULD have a vitest — satisfied
    by extracting pure helpers into knowledge-utils.ts and testing them.
- file: .claude/rules/commit-format.md
  why: `type(scope): description (#issue)`; scope `ui` for frontend/**, `docs`
    for README/docs. Open the tracking issue FIRST.
- file: .claude/rules/branch-naming.md
  why: `<type>/<kebab-slug>` off dev → `feat/knowledge-and-guide-pages`.
```

### Current Codebase tree (relevant)
```bash
frontend/src/
├── App.tsx                       # MOD — add /knowledge + /guide lazy routes
├── lib/
│   ├── api.ts                    # reuse api<T>() + ApiError + getErrorMessage
│   ├── constants.ts              # MOD — ROUTES + NAV_ITEMS
│   ├── date-utils.ts             # precedent: pure lib helper module
│   ├── status-utils.ts           # precedent: pure lib helper module
│   └── knowledge-utils.ts        # NEW — pure helpers for the Knowledge page
├── types/api.ts                  # MOD — +RetrieveRequest, ChunkResult, RetrieveResponse
├── hooks/
│   ├── use-rag-sources.ts        # MOD — +useRetrieve mutation
│   ├── use-seeder.ts             # reuse useSeederStatus
│   ├── use-runs.ts               # reuse runs + aliases hooks
│   └── use-config.ts             # reuse useAIConfig
├── pages/
│   ├── admin.tsx                 # reference (RagSourcesPanel, StatCard) — UNCHANGED
│   ├── chat.tsx                  # reference for the Guide's accuracy — UNCHANGED
│   ├── showcase.tsx              # reference page registration (PRP-17)
│   ├── knowledge.tsx             # NEW — the Knowledge page
│   └── guide.tsx                 # NEW — the Agent Guide page
└── components/
    ├── ui/                       # reuse Card, Badge, Input, Button, Tabs, Separator
    └── common/                   # reuse LoadingState, ErrorDisplay
```

### Desired Codebase tree (files added / changed)
```bash
NEW  frontend/src/pages/knowledge.tsx           # Knowledge page (KB + live state)
NEW  frontend/src/pages/guide.tsx               # Agent Guide page
NEW  frontend/src/lib/knowledge-utils.ts        # pure helpers (testable, no React)
NEW  frontend/src/lib/knowledge-utils.test.ts   # vitest — pure-helper coverage
MOD  frontend/src/types/api.ts                  # +RetrieveRequest/ChunkResult/RetrieveResponse; +5 AIModelConfig fields
MOD  frontend/src/hooks/use-rag-sources.ts      # +useRetrieve mutation hook
MOD  frontend/src/lib/constants.ts              # +KNOWLEDGE/GUIDE routes, +2 NAV_ITEMS
MOD  frontend/src/App.tsx                       # +2 lazy imports, +2 <Route>s
MOD  frontend/src/pages/chat.tsx                # + help link to /guide
MOD  app/features/config/schemas.py             # +5 read-only agent-limit fields on AIModelConfig
MOD  app/features/config/service.py             # populate the 5 fields in get_effective_config
MOD  app/features/config/tests/test_schemas.py  # cover the new fields
MOD  app/features/config/tests/test_service.py  # cover get_effective_config mapping
MOD  app/features/config/tests/test_routes.py   # cover GET /config/ai response
MOD  README.md                                  # mention the two new pages in the feature list
MOD  docs/_base/REPO_MAP_INDEX.md               # +rows for knowledge.tsx + guide.tsx
KEEP frontend/src/pages/admin.tsx               # UNCHANGED — management stays here
KEEP all other app/** (backend)                 # UNCHANGED — only the config slice changes
```

### Known Gotchas & Library Quirks
```typescript
// CRITICAL: FRONTEND-LED PRP with ONE additive backend change — the config
//   slice only (schemas.py + service.py + tests). No new slice, no Alembic
//   migration, no .env var. Because .py files DO change, the repo-wide
//   ruff/mypy/pyright/pytest gates genuinely apply — run them (see Validation
//   Level 4), do not assume they pass trivially. The three pnpm gates still
//   gate the frontend half.

// CRITICAL: /rag/retrieve needs an embedding provider (OpenAI key or Ollama).
//   With none configured it returns 502 application/problem+json. The Knowledge
//   page MUST degrade gracefully: the source LIST (GET /rag/sources) needs NO
//   embeddings and always works; only the SEARCH box can 502 — catch ApiError,
//   show "Semantic search unavailable — configure an embedding provider in
//   Admin → AI Models", keep the rest of the page functional.

// CRITICAL: RetrieveRequest is ConfigDict(extra="forbid"). Send ONLY
//   { query, top_k } (+ optional similarity_threshold/filters). Any stray field
//   → 422. OMIT similarity_threshold entirely to use the server-side default.

// CRITICAL: search is a useMutation, NOT a useQuery. The query string is
//   user-typed and submitted on click/Enter — it is an imperative action with
//   ephemeral results, exactly the useMutation shape. (useQuery would re-fire
//   on every keystroke / refetch.)

// CRITICAL: the Knowledge page is READ-ONLY. Do NOT add index/delete actions —
//   they already live in Admin → RAG Sources (admin.tsx RagSourcesPanel). The
//   Knowledge page COPIES the source-row display markup but DROPS the dialog
//   and the delete AlertDialog. Duplicating management UI is the anti-pattern.

// CRITICAL: the Guide page must use the EXACT agent tool names from the agent
//   definitions (experiment.py / rag_assistant.py). Do not paraphrase tool
//   names. A user copying "tool_run_backtest" into chat must match reality.

// GOTCHA: agent limit numbers (4096 tokens, 10 tool calls, 120s, TTL 120 min)
//   are config DEFAULTS — an operator can change them. Label them "default" on
//   the Guide. The LIVE agent model comes from /config/ai (useAIConfig); render
//   that dynamically, not a hardcoded model string.

// GOTCHA: empty knowledge base — a fresh DB has zero RAG sources. The Knowledge
//   Base section must show a friendly empty state ("No documents indexed yet —
//   add some in Admin → RAG Sources, or run the RAG seeder scenario"), not a
//   blank card and not a crash.

// GOTCHA: NAV_ITEMS is declared `as const`. Adding two flat entries is fine;
//   keep the object shape `{ label, href }` identical to the existing flat
//   items (Dashboard/Showcase/Chat/Admin) so top-nav.tsx's `'items' in item`
//   discriminator still works.

// GOTCHA: react-router lazy route — the page file MUST `export default` the
//   component (App.tsx does `lazy(() => import('@/pages/knowledge'))`). Named
//   helper exports from the SAME file are allowed, but the Knowledge page's
//   pure helpers live in lib/knowledge-utils.ts so they are import-cheap to
//   unit-test (mirrors use-demo-pipeline.ts exporting applyEvent et al.).

// GOTCHA: new frontend files use LF line endings (the repo's CRLF note in
//   memory applies to .py files only). Match the surrounding .tsx files — they
//   are LF. eslint.config.js + tsc are the enforcers.

// GOTCHA: every commit needs an open issue (commit-format.md). Open the
//   tracking issue BEFORE the first commit. No AI co-author trailer, ever.
```

### Known Tradeoffs (decided — do not re-litigate)
```yaml
interpretation:
  decision: "ForecastLab's current knowledge" = the RAG knowledge base (what the
    rag_assistant answers from) PLUS the live system state (what the experiment
    agent acts on: seeded data, runs, aliases). The Knowledge page shows both.
  why: The agentic layer has two agents with two distinct knowledge surfaces.
    Showing only the RAG corpus would under-represent "what the system knows"
    and would also thinly duplicate Admin's RAG tab. Showing both makes the page
    a genuine "knowledge dashboard" and a true counterpart to the Agent Guide.
  status: confirmed — Resolved Decision 1 keeps both the RAG corpus and the
    Live System State section; not scoped down to RAG-only.
minimal-backend:
  decision: no NEW backend slice and no /knowledge or /guide API. The only
    server-side change is additive: read-only agent-limit fields on the existing
    AIModelConfig (GET /config/ai) response.
  why: Every page datum except the live session limits is already served
    (/rag/sources, /rag/retrieve, /seeder/status, /registry/runs,
    /registry/aliases, /config/ai). The maintainer chose live limits over static
    text (Resolved Decision 3), and /config/ai is the natural, already-existing
    home for them — extending it beats a new endpoint.
guide-content-plus-live-config:
  decision: the Guide page is hand-authored content + live /config/ai data (the
    configured model AND the session limits).
  why: It is documentation; the prose (agents, tools, approval flow, example
    prompts) is stable. The two things that legitimately drift — the model and
    the limits — are both fetched live from /config/ai.
search-is-mutation:
  decision: semantic search uses useMutation, not useQuery.
  why: it is a user-initiated imperative action with throwaway results.
```

---

## Implementation Blueprint

### Data models / types (`frontend/src/types/api.ts`, add near line 156 `// === RAG ===`)
```typescript
// Append to the existing RAG block — mirror app/features/rag/schemas.py exactly.

export interface RetrieveRequest {
  query: string
  top_k?: number              // 1..50, server default 5
  similarity_threshold?: number  // 0..1 — OMIT to use the server default
  filters?: Record<string, unknown> | null
}

export interface ChunkResult {
  chunk_id: string
  source_id: string
  source_path: string
  source_type: string
  content: string
  relevance_score: number     // 0..1
  metadata: Record<string, unknown> | null
}

export interface RetrieveResponse {
  results: ChunkResult[]
  query_embedding_time_ms: number
  search_time_ms: number
  total_chunks_searched: number
}
```

### Backend change (`app/features/config/schemas.py` + `service.py`)
```python
# schemas.py — append to AIModelConfig (the GET /config/ai response model),
# NOT to AIModelConfigUpdate (these are read-only, not operator-settable here):
agent_max_tool_calls: int = Field(description="Per-session tool-call cap")
agent_timeout_seconds: int = Field(description="Per-run agent timeout (seconds)")
agent_retry_attempts: int = Field(description="Agent retry attempts on failure")
agent_session_ttl_minutes: int = Field(description="Session time-to-live (minutes)")
agent_require_approval: list[str] = Field(
    description="Tool names gated by human-in-the-loop approval"
)
# agent_max_tokens is ALREADY on AIModelConfig — do not re-add it.

# service.py — get_effective_config(): populate each from the Settings singleton,
# mirroring the existing `agent_max_tokens=settings.agent_max_tokens` line.
```

### Frontend type extension (`frontend/src/types/api.ts`, existing `AIModelConfig`)
```typescript
// EXTEND the existing AIModelConfig interface (~line 360) with the five fields
// the backend now returns — snake_case, matching the Pydantic model:
//   agent_max_tool_calls: number
//   agent_timeout_seconds: number
//   agent_retry_attempts: number
//   agent_session_ttl_minutes: number
//   agent_require_approval: string[]
// agent_max_tokens already exists on AIModelConfig — do not duplicate it.
```

### Hook (`frontend/src/hooks/use-rag-sources.ts`, append)
```typescript
// Pseudocode — mirror the existing useIndexDocument mutation shape.
import type { RetrieveRequest, RetrieveResponse } from '@/types/api'

export function useRetrieve() {
  return useMutation({
    mutationFn: (body: RetrieveRequest) =>
      api<RetrieveResponse>('/rag/retrieve', { method: 'POST', body }),
    // no onSuccess cache invalidation — search results are ephemeral
  })
}
```

### Pure helpers (`frontend/src/lib/knowledge-utils.ts`)
```typescript
// Pure, React-free, unit-testable. Exact helper set is implementer's choice;
// at minimum provide these two so knowledge-utils.test.ts has real coverage:

import type { RagSource, ChunkResult } from '@/types/api'

/** Relevance score (0..1) → a display percentage string, e.g. 0.873 -> "87%". */
export function formatRelevance(score: number): string { /* clamp 0..1, round */ }

/** Group indexed sources by source_type for the "by type" summary. */
export function groupSourcesByType(sources: RagSource[]): Record<string, RagSource[]> { /* ... */ }

/** Optional: short, single-line excerpt of a chunk for the result card. */
export function chunkExcerpt(chunk: ChunkResult, maxChars?: number): string { /* ... */ }
```

### Knowledge page (`frontend/src/pages/knowledge.tsx`)
```text
export default function KnowledgePage()
Layout (build with frontend-design + shadcn-ui; mirror admin.tsx structure):

- Header: <h1>Knowledge</h1> + one sentence: "Everything ForecastLabAI can
  currently draw on — the RAG knowledge base its assistant answers from, and the
  live data its experiment agent acts on."

- SECTION 1 — Knowledge Base (Card):
    * useRagSources() → SourceListResponse.
    * CardDescription: "{total_sources} sources • {total_chunks} chunks".
    * Source list: read-only rows (path, <Badge>{source_type}</Badge>,
      "{chunk_count} chunks", "Indexed {date}"). COPY the row markup from
      admin.tsx RagSourcesPanel lines 209-243 MINUS the delete AlertDialog.
    * Empty state when sources.length === 0 → friendly message + link to
      ROUTES.ADMIN ("Index documents in Admin → RAG Sources").
    * isLoading → <LoadingState/>; error → <ErrorDisplay onRetry={refetch}/>.

- SECTION 2 — Semantic Search (Card, inside or below Section 1):
    * Controlled <Input> for the query + a "Search" <Button>.
    * useRetrieve() mutation. On submit: trim query; if empty, do nothing
      (button disabled). Call mutateAsync({ query, top_k: 5 }).
    * Render results: for each ChunkResult a small card — relevance badge
      (formatRelevance), source_path:source_type, chunkExcerpt(content).
    * mutation.isPending → spinner on the button.
    * mutation.error → if ApiError.status === 502: "Semantic search unavailable
      — configure an embedding provider in Admin → AI Models"; else
      getErrorMessage(error). The source list above stays usable regardless.
    * Empty results (200, results.length === 0) → "No matching content found."

- SECTION 3 — Live System State (Card or grid of Cards):
    * useSeederStatus() → StatCard grid (reuse the StatCard pattern from
      admin.tsx lines 769-785): Stores, Products, Sales, date range.
    * Reuse the runs hook from use-runs.ts → show the registered model-run
      count; reuse the aliases hook → list deployment aliases (name + model_type).
    * One explainer line: "The RAG assistant answers from the Knowledge Base;
      the experiment agent acts on this Live System State." Link to /guide and
      /chat.
```

### Agent Guide page (`frontend/src/pages/guide.tsx`)
```text
export default function GuidePage()
Mostly static, well-structured content. Build with frontend-design + shadcn-ui.

- Header: <h1>Agent Guide</h1> + "How to use the Chat agents."

- Live config callout: useAIConfig() → "Agents currently run on
  {config.agent_model}." (graceful if loading/errored — just omit the callout).
  Link: "manage in Admin → AI Models".

- SECTION — The two agents (two Cards, side by side on desktop):
    * RAG Assistant (rag_assistant):
        - Purpose: evidence-grounded Q&A over the knowledge base; cites
          source_path:chunk_id; says "I don't have enough information" when
          coverage is missing.
        - Tools: tool_retrieve_context, tool_list_sources,
          tool_format_citations, tool_check_evidence.
        - Link: "See what it can answer from → /knowledge".
    * Experiment Agent (experiment):
        - Purpose: plan + run backtests, compare models, recommend/deploy a
          winner.
        - Tools: tool_list_runs, tool_get_run, tool_run_backtest,
          tool_compare_backtest_results, tool_compare_runs,
          tool_create_alias (⚠ requires approval), tool_archive_run (⚠ requires
          approval).

- SECTION — How a chat session works (ordered list, mirror chat.tsx):
    1. Open Chat, pick an agent type, click "Start Session".
    2. Type a message and send.
    3. Watch the reply stream token-by-token; tool calls show as chips
       (tool_call_start → tool_call_end).
    4. If the agent proposes a guarded action, an approval prompt appears —
       approve or reject.
    5. "New Session" starts a fresh conversation.

- SECTION — Human-in-the-loop approval:
    * Explain create_alias + archive_run pause for approval (from
      agent_require_approval). Paraphrase base.py SAFETY_INSTRUCTIONS.

- SECTION — Session limits (a small table, rendered LIVE from useAIConfig()):
    * Token budget (agent_max_tokens) · Tool calls (agent_max_tool_calls) ·
      Timeout (agent_timeout_seconds) · Retries (agent_retry_attempts) ·
      Session TTL (agent_session_ttl_minutes) · Approval-gated tools
      (agent_require_approval). All from GET /config/ai. Graceful when the
      query is loading/errored (show a skeleton or omit the table, never crash).
      Note: configurable in Admin → AI Models.

- SECTION — Example prompts (copy-paste, in <code>/Card blocks):
    * RAG Assistant: "What forecasting models does ForecastLabAI support?",
      "How does backtesting prevent data leakage?", "What is in your knowledge
      base?"
    * Experiment Agent: "Backtest a seasonal_naive model for store 1 product 1
      over the last 90 days and compare it to the naive baseline.",
      "List the most recent model runs and tell me which has the lowest WAPE."

- CTA: <Button> linking to ROUTES.CHAT — "Open Chat".
```

### list of tasks (in execution order)
```yaml
Task 1 — Tracking GitHub issue: ✅ DONE — issue #185
  https://github.com/w7-mgfcode/ForecastLabAI/issues/185
  Do NOT open another issue. Every commit below references (#185).

Task 2 — Backend: extend GET /config/ai with agent-limit fields:
  MODIFY app/features/config/schemas.py
    - Append to AIModelConfig (NOT AIModelConfigUpdate): agent_max_tool_calls:int,
      agent_timeout_seconds:int, agent_retry_attempts:int,
      agent_session_ttl_minutes:int, agent_require_approval:list[str].
      agent_max_tokens is already present — leave it.
  MODIFY app/features/config/service.py
    - In get_effective_config (line 129), populate each new field from the
      Settings singleton, mirroring `agent_max_tokens=settings.agent_max_tokens`.
  MODIFY app/features/config/tests/{test_schemas.py,test_service.py,test_routes.py}
    - Cover the five new fields: schema construction, service mapping from
      Settings, and the GET /config/ai route response shape.
  VALIDATE: uv run ruff check app/ && uv run mypy app/ && uv run pyright app/ &&
    uv run pytest -v app/features/config/tests

Task 3 — Types:
  MODIFY frontend/src/types/api.ts
    - Add RetrieveRequest, ChunkResult, RetrieveResponse to the `// === RAG ===`
      block (after SourceListResponse / IndexDocumentResponse, ~line 182).
    - EXTEND the existing AIModelConfig interface (~line 360) with the five new
      fields from Task 2 (agent_max_tool_calls, agent_timeout_seconds,
      agent_retry_attempts, agent_session_ttl_minutes, agent_require_approval).
    - Field names snake_case, matching the Pydantic models exactly.

Task 4 — Hook:
  MODIFY frontend/src/hooks/use-rag-sources.ts
    - Add `useRetrieve()` — a useMutation wrapping POST /rag/retrieve (see
      pseudocode). Import RetrieveRequest/RetrieveResponse from @/types/api.
    - hooks/index.ts already re-exports use-rag-sources — no change there.
    - useAIConfig() already exists in use-config.ts — no new config hook.

Task 5 — Pure helpers + routing + constants:
  CREATE frontend/src/lib/knowledge-utils.ts — formatRelevance,
    groupSourcesByType, chunkExcerpt (pure, no React import).
  MODIFY frontend/src/lib/constants.ts
    - ROUTES: add `KNOWLEDGE: '/knowledge'` and `GUIDE: '/guide'`.
    - NAV_ITEMS: add `{ label: 'Knowledge', href: ROUTES.KNOWLEDGE }` after the
      Visualize group, and `{ label: 'Agent Guide', href: ROUTES.GUIDE }` after
      the Chat entry (before Admin). Keep the flat `{ label, href }` shape.
  MODIFY frontend/src/App.tsx
    - `const KnowledgePage = lazy(() => import('@/pages/knowledge'))`
    - `const GuidePage = lazy(() => import('@/pages/guide'))`
    - Two `<Route>`s wrapped in `<Suspense fallback={<PageLoader/>}>`, mirroring
      the ShowcasePage block.

Task 6 — Knowledge page:
  CREATE frontend/src/pages/knowledge.tsx
    - `export default function KnowledgePage()` (see "Knowledge page" layout).
    - Section 1: useRagSources() — read-only source list + summary + empty state.
    - Section 2: useRetrieve() — search box, results cards, 502 graceful state.
    - Section 3: useSeederStatus() + useRuns()/useAliases() — StatCard grid +
      runs count + alias list + explainer linking /guide and /chat.
    - Reuse LoadingState / ErrorDisplay; reuse Card/Badge/Input/Button.
    - Build via the frontend-design + shadcn-ui skills (.claude/rules/ui-design.md).

Task 7 — Agent Guide page + Chat help-link:
  CREATE frontend/src/pages/guide.tsx
    - `export default function GuidePage()` (see "Agent Guide page" layout).
    - useAIConfig() for the live model callout AND the live session-limits table
      (graceful when loading/errored).
    - EXACT agent tool names from experiment.py / rag_assistant.py.
    - Example prompts; CTA → ROUTES.CHAT.
  MODIFY frontend/src/pages/chat.tsx
    - Add a small, unobtrusive help link to ROUTES.GUIDE (e.g. near the agent
      Select or the page header) — "New here? Read the Agent Guide". Do not
      restructure the chat flow; this is one link.

Task 8 — Frontend test:
  CREATE frontend/src/lib/knowledge-utils.test.ts
    - vitest, mirror use-demo-pipeline.test.ts structure (describe/it/expect).
    - formatRelevance: 0.873 -> "87%"; clamps 0 and 1; handles out-of-range.
    - groupSourcesByType: groups a mixed RagSource[] into per-type buckets;
      empty array -> {}.
    - chunkExcerpt: truncates long content; short content returned intact.

Task 9 — Docs:
  MODIFY README.md — add the two pages to the feature/endpoint list (near where
    Showcase / dashboard pages are described).
  MODIFY docs/_base/REPO_MAP_INDEX.md — add rows for frontend/src/pages/knowledge.tsx
    and frontend/src/pages/guide.tsx in the document index table.

Task 10 — Dogfood the running UI (mandatory per ui-design.md):
  - docker compose up -d ; uv run alembic upgrade head ; seed data once
    (uv run python scripts/seed_random.py --full-new --seed 42 --confirm).
  - uv run uvicorn app.main:app --port 8123 & ; cd frontend && pnpm dev.
  - Use webapp-testing / agent-browser: open /knowledge — confirm the source
    list renders, run a semantic search, confirm result cards + relevance
    badges, confirm the Live System State tiles. Open /guide — confirm both
    agent cards, the live model callout, and the LIVE limits table (values
    match GET /config/ai). Confirm the Chat page's help link reaches /guide.
    Capture screenshots.
  - Optional: with no embedding key, confirm the search box shows the graceful
    502 state while the rest of /knowledge still works.

Task 11 — Commit + PR:
  Branch: feat/knowledge-and-guide-pages (off dev, per branch-naming.md).
  Commits (each referencing the Task-1 issue; no AI co-author trailer).
  Scope note: the config slice has no dedicated scope in commit-format.md;
  it was introduced under `api,ui` (commit db530d5), so use `api` for it.
    1. feat(api): expose agent session limits on GET /config/ai (#185)
    2. feat(ui): knowledge page — RAG corpus + live system state (#185)
    3. feat(ui): agent guide page explaining the chat agents (#185)
    4. test(ui): knowledge-utils pure-helper coverage (#185)
    5. docs(docs): document the knowledge + agent guide pages (#185)
  Open PR into dev; CI green; merge.
```

### Integration Points
```yaml
DATABASE:    NONE — no migration, no DB schema change.
BACKEND:     config slice ONLY — AIModelConfig schema + get_effective_config
             service gain five read-only agent-limit fields; config slice tests
             updated. No new slice, no new endpoint, all other app/** unchanged.
CONFIG:      NONE — no new env var (the limits already exist in Settings).
FRONTEND ROUTING:
  - ROUTES.KNOWLEDGE + ROUTES.GUIDE + two NAV_ITEMS entries (constants.ts).
  - Two lazy <Route>s in App.tsx; a help link to /guide on chat.tsx.
CI:
  - No new workflow. ci.yml's existing jobs cover it. The frontend gates run as
    today; the Python jobs now genuinely exercise the config-slice change —
    they must be GREEN, not assumed-trivial.
```

---

## Validation Loop

### Level 1: Type & Lint (frontend)
```bash
cd frontend
pnpm install
pnpm tsc --noEmit        # zero type errors — new types + pages must compile
pnpm lint                # eslint clean
# Expected: no errors. Fix any before proceeding.
```

### Level 2: Unit test (frontend)
```bash
cd frontend
pnpm test --run          # vitest — knowledge-utils.test.ts must pass
# Expected: all green, including the new knowledge-utils suite.
```

### Level 3: Manual end-to-end (the maintainer's actual UX)
```bash
docker compose up -d && uv run alembic upgrade head
uv run python scripts/seed_random.py --full-new --seed 42 --confirm   # data + RAG
uv run uvicorn app.main:app --port 8123 &
until curl -fs http://127.0.0.1:8123/health; do sleep 2; done
cd frontend && pnpm dev          # http://localhost:5173

# Browser checks (via webapp-testing / agent-browser):
#  /knowledge — source list renders; type a query, click Search, see ChunkResult
#               cards with relevance %; Live System State tiles show seeded data.
#  /guide     — both agent cards with exact tool names; live model callout;
#               limits table; example prompts; "Open Chat" button works.
#  Nav        — "Knowledge" and "Agent Guide" appear in desktop nav + mobile sheet.
```

### Level 4: Backend gates (the config slice .py files DID change)
```bash
uv run ruff check . && uv run ruff format --check .
uv run mypy app/ && uv run pyright app/              # both --strict, both gate
uv run pytest -v -m "not integration" app/features/config/tests
docker compose up -d
uv run pytest -v -m integration app/features/config/tests
# Expected: all green. The config slice change is additive + read-only.
```

---

## Final Validation Checklist
- [ ] `cd frontend && pnpm tsc --noEmit` clean
- [ ] `cd frontend && pnpm lint` clean
- [ ] `cd frontend && pnpm test --run` all green (incl. `knowledge-utils.test.ts`)
- [ ] `uv run ruff check . && uv run mypy app/ && uv run pyright app/` clean
- [ ] `uv run pytest -v app/features/config/tests` green (new agent-limit fields)
- [ ] `GET /config/ai` returns agent_max_tool_calls, agent_timeout_seconds,
      agent_retry_attempts, agent_session_ttl_minutes, agent_require_approval
- [ ] `/knowledge` renders: source list + summary, semantic search, Live System
      State tiles; empty-KB and 502-search states both handled gracefully
- [ ] `/guide` renders: both agent cards with EXACT tool names, approval-gate
      section, LIVE limits table + live model from `/config/ai`, example prompts
- [ ] Both pages reachable from desktop nav AND mobile sheet; Chat links to /guide
- [ ] Both pages dogfooded in a real browser (screenshots captured)
- [ ] Admin → RAG Sources is unchanged; no index/delete management duplicated
- [ ] Only the `config` slice changed under `app/**`; no Alembic migration; no
      `.env` var added
- [ ] README + `docs/_base/REPO_MAP_INDEX.md` updated
- [ ] Branch `feat/knowledge-and-guide-pages`; every commit references the
      Task-1 issue; no AI co-author trailer

---

## Anti-Patterns to Avoid
- ❌ Don't add a NEW backend slice or endpoint — the only backend change is
  five additive read-only fields on the existing `AIModelConfig` response.
- ❌ Don't add the new limit fields to `AIModelConfigUpdate` (the PATCH body) —
  they are read-only on the GET response, not operator-settable here.
- ❌ Don't duplicate Admin's RAG index/delete management on the Knowledge page —
  it is READ-ONLY; management stays in `admin.tsx`.
- ❌ Don't use `useQuery` for the semantic search — it is a user-initiated POST →
  `useMutation`.
- ❌ Don't send extra fields on `RetrieveRequest` — it is `extra="forbid"`; omit
  `similarity_threshold` to use the server default.
- ❌ Don't let a `502` from `/rag/retrieve` blank the page — the source list does
  not need embeddings; degrade only the search box.
- ❌ Don't invent agent tool names on the Guide — copy them verbatim from
  `experiment.py` / `rag_assistant.py`.
- ❌ Don't hardcode the agent model string on the Guide — render it from
  `/config/ai`.
- ❌ Don't hand-roll the pages without the `frontend-design` / `shadcn-ui` skills,
  and don't claim "done" on a green type-check — dogfood in a real browser
  (`.claude/rules/ui-design.md`).
- ❌ Don't create a `components/knowledge/` directory — keep sub-components inside
  the page file, mirroring `admin.tsx`.
- ❌ Don't `git push --force` on dev/main; don't add AI co-author trailers; every
  commit references the open issue.

---

## Resolved Decisions (maintainer-confirmed 2026-05-18)
1. **Knowledge page scope → RAG + Live System State.** The `/knowledge` page
   ships all three sections — Knowledge Base, Semantic Search, and Live System
   State (seeded data, runs, aliases). Not scoped down to RAG-only.
2. **Navigation → two flat nav items AND a Chat help-link.** Both `Knowledge`
   and `Agent Guide` are flat top-level nav entries (8 items total); ADDITIONALLY
   the Chat page carries a help link to `/guide` (Task 5 + Task 7).
3. **Guide limits → live, backend folded into this PRP.** The session limits are
   rendered live from `/config/ai`, which is extended in this PRP (Task 2) with
   five read-only agent-limit fields. PRP-19 is therefore frontend-led with one
   small additive backend change — it is no longer "frontend-only".

---

## Confidence Score

**8 / 10** for one-pass implementation success.

**Why high:**
- Frontend-led and almost entirely additive — two new pages + a handful of small
  edits. The one backend change is a five-field, read-only, additive extension
  of an existing response model (`AIModelConfig`), sourced straight from
  `Settings` — no migration, no new endpoint, no behavioural change.
- Every endpoint is already shipped and already has a hook; the page-registration
  pattern is a verbatim copy of PRP-17's `Showcase` wiring, cited file+line.
- `admin.tsx` already renders `/rag/sources` data — the source-list markup is
  lifted, not invented. The one new hook (`useRetrieve`) is a ~6-line clone of
  the existing `useIndexDocument` mutation.
- Validation gates are concrete and fast: three pnpm gates for the frontend,
  plus the config-slice backend gates (ruff/mypy/pyright/pytest).
- All three Open Questions are now Resolved Decisions — no scoping ambiguity.

**Why not 10:**
- Both pages are genuine UI composition work — layout, hierarchy, and the
  Guide's content density need a real-browser dogfooding pass (Task 10); a green
  `tsc` will not catch a cramped layout or a broken nav link.
- The `502`-graceful search path depends on the local embedding-provider state;
  it must be exercised both with and without a key to confirm the degrade path.
- The backend change is small but DOES make the repo-wide mypy/pyright/pytest
  gates load-bearing — the config-slice tests must be extended, not skipped.

All risks are caught by the validation loop (browser dogfood + the 502 toggle +
the config-slice test run) and the fixes are local.
