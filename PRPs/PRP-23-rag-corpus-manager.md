name: "PRP-23 — RAG Corpus Manager: one-click bulk-index of bundled project docs"
description: |
  Promote the MVP of `docs/optional-features/01-rag-corpus-manager.md` into code.

  A fresh ForecastLabAI install has an **empty RAG corpus** (`0 sources / 0 chunks`),
  so the RAG Assistant agent can cite nothing and the Knowledge page is a permanent
  empty state — despite the repo bundling ~115 markdown files under `docs/`, `PRPs/`,
  and the root.

  This PRP adds **one new orchestration endpoint** — `POST /rag/index/project-docs` —
  that discovers the bundled markdown and indexes each file through the existing
  `RAGService.index_document` path (reusing its chunking, embedding, SHA-256
  content-hash idempotency, and upsert). The Admin → "RAG Sources" tab gets an
  **"Index Project Docs"** button that calls it and toasts the summary.

  Everything else the feature doc lists is **already done** or **out of scope**:
  source listing / deletion / provider-health / Knowledge empty-state all exist;
  stale-detection, re-index, chunk-preview, and the Knowledge source-type filter are
  explicitly deferred to a follow-up ("Full Version" — see Anti-Patterns / NOTES).

> **PRP numbering:** `PRP-16` is reserved (Phase-2 LightGBM). `PRP-17`–`PRP-22` are
> used. This is `PRP-23`. Source plan: `.agents/plans/rag-index-project-docs.md`.

## Purpose

Close the "the RAG corpus starts empty and there is no operator-facing way to fill
it" gap. Today the only ways to populate the corpus are (a) `POST /rag/index` once
per file (~115 calls, requires pasting each path) or (b) the seeder's synthetic
3-document scenario, which indexes throwaway test prose rather than the real project
documentation. An operator or demo reviewer needs **one click** that turns
`0 sources` into a populated, citable corpus drawn from the repo's own docs.

## Core Principles

1. **Context is King** — every endpoint shape, schema field, service method, hook
   name, and pattern below is linked to a real source file with verified line
   numbers.
2. **Reuse, don't reinvent** — `index_project_docs` is a thin orchestrator over the
   existing `RAGService.index_document`; it does NOT re-implement hashing, chunking,
   embedding, or upsert. The route mirrors the existing `index_document` route's
   exception handling; the hook mirrors `useIndexDocument`.
3. **Additive only** — NO Alembic migration (no schema change — `category` rides in
   the existing `DocumentSource.metadata_` JSONB), NO new slice, NO `.env` var, NO
   `app/main.py` change (the `rag` router is already wired).
4. **Strict gates honored** — `.py` files in the `rag` slice change, so the repo-wide
   `ruff` / `mypy --strict` / `pyright --strict` / `pytest` CI jobs genuinely apply;
   the new endpoint ships with unit + integration tests.
5. **UI through the running app** — the Admin button is verified in a real browser
   via `webapp-testing` per `.claude/rules/ui-design.md`. A green `tsc` is NOT proof
   the UI works.

---

## Goal

**Backend (additive, no migration, no `main.py` change):**

- `POST /rag/index/project-docs` — discovers markdown under `docs/**`, `PRPs/**`,
  and a fixed root-file allow-list (`README.md`, `AGENTS.md`, `CHANGELOG.md`),
  indexes each through `RAGService.index_document`, and returns a per-file +
  aggregate summary. Request body is three optional booleans (`include_docs`,
  `include_prps`, `include_root`, all default `true`). Idempotent — re-runs return
  every file `unchanged` via the existing SHA-256 short-circuit. A single
  unreadable / non-UTF-8 file is reported `failed` without aborting the batch;
  `EmbeddingError` / `SQLAlchemyError` are batch-fatal and surface as `502` /
  `application/problem+json`.

**Frontend:**

- New TanStack mutation hook `useIndexProjectDocs` in `use-rag-sources.ts`.
- Three new TS types (`IndexProjectDocsRequest`, `ProjectDocResult`,
  `IndexProjectDocsResponse`) in `types/api.ts`.
- An **"Index Project Docs"** button in the Admin → "RAG Sources" tab
  (`RagSourcesPanel`) — spinner while running, a `toast` summary on completion,
  and a `['rag-sources']` query invalidation so the list + counts refresh.

## Why

- **Portfolio identity.** `.claude/rules/product-vision.md` principle 1 —
  "portfolio-grade, end-to-end … every phase ships working code". The RAG slice
  exists end-to-end but is invisible: a reviewer opening a fresh system sees an
  empty Knowledge page and an agent that can cite nothing. This makes the existing
  RAG investment demonstrable.
- **Demo narrative.** `docs/optional-features/README.md` § "Promotion Criteria" —
  a feature should "improve the demo narrative without breaking the local-first
  setup". Bulk-indexing the repo's own docs is the most direct way to show the RAG
  Assistant working off real evidence.
- **Operator workflow.** The feature doc's user value: "Demo reviewers can index
  project docs without CLI setup"; "the Knowledge page becomes a real corpus
  browser instead of mostly an empty-state page".

## What

A logged-in operator opens **Admin → RAG Sources**, sees `0 sources • 0 chunks`,
clicks **Index Project Docs**, watches a spinner for up to ~1–3 minutes (first run,
real embedding provider), then sees a toast — e.g. *"Indexed 112, updated 0,
unchanged 0, 3 failed — 1 480 chunks"* — and the source list populates. Opening
**Knowledge** now shows the corpus and semantic search returns cited chunks.
Clicking **Index Project Docs** again completes near-instantly with every file
`unchanged`.

### Success Criteria

- [ ] `POST /rag/index/project-docs` indexes `docs/**/*.md`, `PRPs/**/*.md`, and the
      root allow-list; returns `IndexProjectDocsResponse` with per-file results +
      aggregate counts.
- [ ] Idempotent — a second call with unchanged files returns every result
      `unchanged` and creates no new chunks.
- [ ] `include_docs` / `include_prps` / `include_root` toggles select roots
      independently; an empty `{}` body indexes all three.
- [ ] A single unreadable / non-UTF-8 file is reported `status="failed"` with an
      `error` string and does not abort the batch.
- [ ] `EmbeddingError` → `502`, `SQLAlchemyError` → `DatabaseError` /
      `application/problem+json` (no partial commit — the request rolls back).
- [ ] Admin → "RAG Sources" has a working "Index Project Docs" button: spinner,
      toast summary (`toast.warning` when `failed > 0`, else `toast.success`), and
      a live source-list refresh.
- [ ] All validation gates (ruff, mypy --strict, pyright --strict, pytest unit +
      integration, frontend tsc/lint/test) pass; integration tests leave no
      `test-` rows in `document_source`.
- [ ] `docs/_base/API_CONTRACTS.md` lists the new endpoint.
- [ ] No regression in existing RAG tests or `app/core/tests/test_strict_mode_policy.py`.

## All Needed Context

### Documentation & References

```yaml
# ---- External docs ----
- url: https://docs.python.org/3/library/pathlib.html#pathlib.Path.rglob
  why: Path.rglob("*.md") for recursive discovery. CRITICAL — rglob on a
       NON-EXISTENT directory yields nothing (no exception); relied on so an
       absent docs/ or PRPs/ root simply contributes 0 files.
- url: https://fastapi.tiangolo.com/tutorial/body/
  why: A Pydantic model as a request body whose fields ALL have defaults
       validates an empty `{}` payload — the frontend always posts `{}`.
- url: https://docs.pydantic.dev/latest/concepts/models/#extra-fields
  why: ConfigDict(extra="forbid") on the request → an unknown body field 422s.
       Mirrors the existing IndexRequest.

# ---- Source feature spec ----
- file: docs/optional-features/01-rag-corpus-manager.md
  why: The spec. Implement ONLY the "MVP Scope" section. "Full Version" (stale
       detection, re-index, chunk preview, Knowledge filters) is OUT OF SCOPE.
- file: .agents/plans/rag-index-project-docs.md
  why: The source implementation plan this PRP refines (notably: the unit test
       now targets a new pure _discover_project_doc_files helper, not a mocked
       index_document — see "Resolved Decisions").

# ---- Backend: the rag slice (all changes land here) ----
- file: app/features/rag/routes.py
  why: lines 61-133 — `index_document` route: the EXACT exception-handling
       shape to mirror (EmbeddingError→502, SQLAlchemyError→DatabaseError) and
       the structured-logging style. Lines 12-19 — the schema import block to
       extend. Lines 1-24 — router, `logger`, `RAGService` imports.
- file: app/features/rag/service.py
  why: lines 130-251 — `index_document`, the method `index_project_docs`
       orchestrates per file. lines 159-163 — the `if request.content:` branch
       (see the empty-file GOTCHA). lines 173-191 — the SHA-256 idempotency
       short-circuit. lines 61-81 — `__init__` + the `base_dir` test override.
       lines 94-128 — `_read_content_from_path` (path-traversal pattern).
       lines 29-38 — the schema import block to extend.
- file: app/features/rag/schemas.py
  why: lines 17-43 `IndexRequest`, 46-65 `IndexResponse` — the schema style to
       mirror: `ConfigDict(extra="forbid")` on the request, `Literal` status
       field, `Args:` docstrings. NOTE: `IndexRequest` is NOT `strict=True`, so
       the new request model needs no `Field(strict=False)` overrides and
       `app/core/tests/test_strict_mode_policy.py` is unaffected.
- file: app/features/rag/models.py
  why: lines 35-66 `DocumentSource` — confirms `source_type` is free-form
       `String(50)` (we keep `"markdown"`), `metadata_` is JSONB (we store
       `{"category": ...}`), and `uq_source_type_path` drives idempotency.
- file: app/features/rag/chunkers.py
  why: `get_chunker("markdown")` → `MarkdownChunker`. Confirms `"markdown"` is a
       valid `source_type` for every project doc.
- file: app/core/exceptions.py
  why: `DatabaseError` — re-raised on `SQLAlchemyError`; already imported in
       `routes.py:9`.

# ---- Backend: tests ----
- file: app/features/rag/tests/conftest.py
  why: `db_session` + `client` integration fixtures, `mock_embedding_service`
       unit fixture, and the cleanup at LINE 46
       (`DocumentSource.source_path.like("test-%")`) — this PRP widens it to
       `"%test-%"` so nested fixture paths (`docs/test-*.md`) are cleaned up.
- file: app/features/rag/tests/test_routes.py
  why: lines 22-37 `create_mock_embedding_service()` and the
       `patch("app.features.rag.service.get_embedding_service", ...)` pattern;
       `TestIndexEndpoint` (45-167) class layout to mirror.
- file: app/features/rag/tests/test_service.py
  why: `TestRAGServiceUnit` — pure-unit class layout (`RAGService()` with no DB,
       no mocks); the home for the new `_discover_project_doc_files` unit test.

# ---- Frontend ----
- file: frontend/src/hooks/use-rag-sources.ts
  why: lines 29-41 `useIndexDocument` — the EXACT mutation-hook shape
       (`useMutation` + `api(...)` + `invalidateQueries(['rag-sources'])`).
- file: frontend/src/pages/admin.tsx
  why: lines 116-253 `RagSourcesPanel` — where the button goes; the `CardHeader`
       actions area (148-205); the lucide import block (4-21 — `Library` must be
       ADDED); `toast` already imported (line 68); the `handleGenerate` toast
       pattern (470-488); the `Loader2` spinner-in-button pattern (line 199).
- file: frontend/src/types/api.ts
  why: lines 258-313 — the `// === RAG ===` block to extend; `RagSource`,
       `IndexDocumentResponse`, `RetrieveResponse` naming convention.
- file: frontend/src/lib/api.ts
  why: lines 23-44 — `api<T>(endpoint, {method, body})`; a truthy `{}` body is
       JSON-stringified to `"{}"`.

# ---- Rules ----
- file: .claude/rules/security-patterns.md
  why: § "File operations" — `pathlib.Path.resolve()`, allow-listed roots, no
       `..`. Discovery globs only fixed roots under `base_dir` (no user input) →
       inherently allow-listed; keep it that way.
- file: .claude/rules/test-requirements.md
  why: new endpoint ⇒ route test with 2xx happy path + ≥1 error path.
- file: .claude/rules/commit-format.md
  why: commit `type(scope): description (#issue)`; `rag,ui` comma-pair scope is
       allowed; every commit references an open issue; NO AI co-author trailer.
```

### Current Codebase tree (relevant)

```
app/features/rag/
├── __init__.py
├── chunkers.py            # MarkdownChunker / OpenAPIChunker — UNCHANGED
├── embeddings.py          # OpenAI / Ollama providers — UNCHANGED
├── models.py              # DocumentSource / DocumentChunk — UNCHANGED (no migration)
├── routes.py              # /rag/index, /retrieve, /sources — ADD one route
├── schemas.py             # IndexRequest, …, DeleteResponse — ADD three models
├── service.py             # RAGService — ADD _discover_project_doc_files + index_project_docs
└── tests/
    ├── conftest.py        # MODIFY line 46 cleanup glob
    ├── test_chunkers.py   # UNCHANGED
    ├── test_embeddings.py # UNCHANGED
    ├── test_routes.py     # ADD TestIndexProjectDocsEndpoint
    ├── test_schemas.py    # ADD new-schema cases
    └── test_service.py    # ADD _discover_project_doc_files unit test

frontend/src/
├── hooks/use-rag-sources.ts   # ADD useIndexProjectDocs
├── pages/admin.tsx            # ADD button in RagSourcesPanel
└── types/api.ts               # ADD 3 interfaces

docs/_base/API_CONTRACTS.md    # ADD one table row
```

### Desired Codebase tree (files added / changed)

No new files. Eleven existing files are modified:

```
MODIFY  app/features/rag/schemas.py            + IndexProjectDocsRequest / ProjectDocResult / IndexProjectDocsResponse
MODIFY  app/features/rag/service.py            + _discover_project_doc_files() + index_project_docs() + 2 module constants
MODIFY  app/features/rag/routes.py             + POST /rag/index/project-docs route
MODIFY  app/features/rag/tests/conftest.py     ~ cleanup glob "test-%" -> "%test-%"
MODIFY  app/features/rag/tests/test_schemas.py + new-schema validation cases
MODIFY  app/features/rag/tests/test_service.py + _discover_project_doc_files unit test
MODIFY  app/features/rag/tests/test_routes.py  + TestIndexProjectDocsEndpoint (integration)
MODIFY  frontend/src/types/api.ts              + 3 interfaces
MODIFY  frontend/src/hooks/use-rag-sources.ts  + useIndexProjectDocs hook
MODIFY  frontend/src/pages/admin.tsx           + "Index Project Docs" button (+ Library icon import)
MODIFY  docs/_base/API_CONTRACTS.md            + endpoint-table row
```

### Known Gotchas & Library Quirks

```python
# CRITICAL: CRLF line endings. Every existing app/**/*.py file in this repo is
#   CRLF-terminated (no .gitattributes — project memory). A FULL-FILE rewrite
#   (the Write tool, or a text-mode dump) silently flips them to LF and produces
#   a whole-file diff. Use the Edit tool (exact string replacement — it preserves
#   the surrounding line endings) for every .py change. After EACH edit run
#   `git diff --stat`: the changed-line count must be small. If you see a
#   whole-file churn, the EOLs flipped — restore CRLF before continuing. New
#   files: none here. Frontend .ts/.tsx files are LF — safe.

# CRITICAL: NO app/main.py change. The `rag` router is already wired
#   (main.py:27 import, main.py:142 include_router). The new route attaches to
#   the existing `router = APIRouter(prefix="/rag", ...)` in routes.py.

# CRITICAL: NO Alembic migration. DocumentSource / DocumentChunk are unchanged.
#   The per-source `category` ("docs" | "prp" | "root") rides inside the EXISTING
#   `DocumentSource.metadata_` JSONB column. `.claude/rules` require a migration
#   only when the SCHEMA changes — adding one here would be wrong.

# CRITICAL: index_document's content branch (service.py:160) is `if request.content:`
#   — an EMPTY string is FALSY, so an empty .md file passed as content="" falls
#   through to `_read_content_from_path(rel)`, which resolves the relative path
#   against CWD. In production CWD == base_dir (uvicorn runs from the repo root),
#   so the redundant re-read succeeds and the file indexes to 0 chunks. In a
#   base_dir-OVERRIDE test (CWD != base_dir) it raises FileNotFoundError — which
#   is a subclass of OSError and is therefore caught by the per-file
#   `except (OSError, ValueError)` and reported `status="failed"`. NEVER fatal.
#   Mitigation: make every test fixture file NON-EMPTY (`"# Test\n\nContent."`).
#   Do NOT "fix" index_document — it is shared with POST /rag/index.

# CRITICAL: pass BOTH source_path (the clean RELATIVE posix path — the DB id) AND
#   content (the file text) to IndexRequest. source_path drives the
#   `(source_type, source_path)` idempotency lookup + is stored; content (when
#   truthy) is hashed/chunked. NEVER store an absolute path — it is
#   machine-specific and breaks idempotency across machines/CI.

# CRITICAL: route-test base_dir injection. The route does `RAGService()` with no
#   args (→ base_dir = Path.cwd()). To point an integration test at a tmp_path,
#   patch the class symbol in the routes module:
#     patch("app.features.rag.routes.RAGService",
#           functools.partial(RAGService, base_dir=str(tmp_path)))
#   `partial(Cls, kw=v)()` constructs `Cls(kw=v)`. Patch
#   `app.features.rag.service.get_embedding_service` SEPARATELY (the existing
#   test pattern) so __init__ picks up the mock provider.

# CRITICAL: integration-test cleanup. conftest.py:46 deletes
#   `source_path LIKE 'test-%'`. Project-doc source paths are NESTED
#   (`docs/test-proj-1.md`) and do NOT start with `test-`. Widen the glob to
#   `"%test-%"` (Task 1). Real corpus paths (`docs/ARCHITECTURE.md`, `PRPs/PRP-1-…`)
#   never contain `test-`, so the wider LIKE is safe; existing `test-`-prefixed
#   fixtures still match. Name every new fixture file with a `test-` token.

# GOTCHA: synchronous by design. Indexing runs in-request. ~115 bundled markdown
#   files ⇒ the first run with a real embedding provider takes ~1-3 min (one
#   batched embedding call per file). `fetch` has no default timeout and the
#   TanStack mutation waits, so this is acceptable for an admin action; re-runs
#   are fast (all `unchanged`). The jobs-layer upgrade is the deferred
#   "Full Version" — OUT OF SCOPE here.

# GOTCHA: status-Literal widening. IndexResponse.status is
#   Literal["indexed","updated","unchanged"]; ProjectDocResult.status is
#   Literal["indexed","updated","unchanged","failed"]. Assigning the narrower
#   into the wider is fine for mypy/pyright (subtype). "failed" is only ever set
#   in the per-file except branch.

# GOTCHA: EmbeddingError is NOT an OSError/ValueError (it extends Exception), so
#   it is NOT caught by the per-file `except (OSError, ValueError)` — it
#   propagates out of the loop, the request rolls back, and the route maps it to
#   502. Same for SQLAlchemyError. This is intentional: a dead embedding provider
#   makes the whole batch pointless.

# GOTCHA: `RAGService()` is safe to construct in a pure unit test with no mocks —
#   __init__ only builds the (lazy) embedding client + a tiktoken encoder, no
#   network. test_service.py::TestRAGServiceUnit already relies on this.

# GOTCHA: admin.tsx does NOT currently import `Library` from lucide-react. Add it
#   to the existing import block (admin.tsx:4-21). `toast` IS already imported
#   (admin.tsx:68).
```

### Resolved Decisions (carried from `.agents/plans/rag-index-project-docs.md`)

- **Scope = MVP only.** Out of scope: `GET /rag/sources/{id}/chunks` + chunk
  preview, `POST /rag/sources/{id}/reindex` + stale detection, the Knowledge-page
  source-type filter, per-source embedding-metadata columns (would need a
  migration). Keeping the PR small matches the maintainer preference in
  `CLAUDE.local.md` ("prefer a smaller PR over a bundled one").
- **Root file allow-list = `("README.md", "AGENTS.md", "CHANGELOG.md")`.** `CLAUDE.md`
  is excluded — it is mostly an operating index and `@import`s `AGENTS.md` (whose
  substance is already indexed).
- **`source_type` stays `"markdown"` for every project doc.** The `docs|prp|root`
  distinction is stored as `metadata.category`, which powers the existing
  `RetrieveRequest.filters.category` path (`service.py:585-589`) for free, with no
  schema change.
- **Refinement vs the plan:** discovery is extracted into a pure, sync
  `_discover_project_doc_files` helper so it can be unit-tested with no DB and no
  mocks (the plan's "mock `index_document`" approach would pass a `MagicMock`
  where `mypy --strict` expects an `AsyncSession`). The full `index_project_docs`
  loop/aggregate path is covered by the route integration test.
- **Synchronous in-request** (not the jobs layer) — see the GOTCHA above.

## Implementation Blueprint

### Data models — backend schemas (`app/features/rag/schemas.py`)

Append after `DeleteResponse`. Mirror `IndexRequest` / `IndexResponse` style.

```python
# Pseudocode — do not copy verbatim; add full `Args:` docstrings per file style.

class IndexProjectDocsRequest(BaseModel):
    """Request to bulk-index bundled project documentation."""
    model_config = ConfigDict(extra="forbid")          # NOT strict=True (mirror IndexRequest)
    include_docs: bool = Field(default=True, description="Index docs/**/*.md")
    include_prps: bool = Field(default=True, description="Index PRPs/**/*.md")
    include_root: bool = Field(default=True, description="Index README/AGENTS/CHANGELOG")

class ProjectDocResult(BaseModel):
    """Per-file outcome of a project-docs index run."""
    source_path: str
    status: Literal["indexed", "updated", "unchanged", "failed"]
    chunks_created: int
    error: str | None = None

class IndexProjectDocsResponse(BaseModel):
    """Aggregate result of POST /rag/index/project-docs."""
    results: list[ProjectDocResult]
    total_files: int
    indexed: int
    updated: int
    unchanged: int
    failed: int
    total_chunks: int
    duration_ms: float
```

`Literal`, `BaseModel`, `ConfigDict`, `Field` are already imported (`schemas.py:11-14`).

### Data models — frontend types (`frontend/src/types/api.ts`, in the `// === RAG ===` block, after `RetrieveResponse` ~line 313)

```ts
export interface IndexProjectDocsRequest {
  include_docs?: boolean
  include_prps?: boolean
  include_root?: boolean
}
export interface ProjectDocResult {
  source_path: string
  status: 'indexed' | 'updated' | 'unchanged' | 'failed'
  chunks_created: number
  error: string | null
}
export interface IndexProjectDocsResponse {
  results: ProjectDocResult[]
  total_files: number
  indexed: number
  updated: number
  unchanged: number
  failed: number
  total_chunks: number
  duration_ms: number
}
```

### Backend service (`app/features/rag/service.py`)

Add two module-level constants (after the imports, before `class RAGService`) and
two methods on `RAGService`.

```python
# Module-level — the allow-listed project-doc roots.
_PROJECT_ROOT_FILES: tuple[str, ...] = ("README.md", "AGENTS.md", "CHANGELOG.md")

class RAGService:
    ...
    def _discover_project_doc_files(
        self, request: IndexProjectDocsRequest
    ) -> list[tuple[Path, str]]:
        """Discover bundled markdown under allow-listed roots. Pure + sync.

        Returns a deterministically sorted list of (absolute_path, category)
        where category is "docs" | "prp" | "root".
        """
        found: list[tuple[Path, str]] = []
        if request.include_docs:
            found += [(p, "docs") for p in (self._base_dir / "docs").rglob("*.md")]
        if request.include_prps:
            found += [(p, "prp") for p in (self._base_dir / "PRPs").rglob("*.md")]
        if request.include_root:
            for name in _PROJECT_ROOT_FILES:
                candidate = self._base_dir / name
                if candidate.is_file():
                    found.append((candidate, "root"))
        # GOTCHA: rglob order is filesystem-dependent — sort for stable results.
        return sorted(found, key=lambda pair: str(pair[0]))

    async def index_project_docs(
        self, db: AsyncSession, request: IndexProjectDocsRequest
    ) -> IndexProjectDocsResponse:
        """Bulk-index discovered project docs via index_document. Idempotent."""
        start = time.time()
        logger.info("rag.index_project_docs_started",
                    include_docs=request.include_docs,
                    include_prps=request.include_prps,
                    include_root=request.include_root)

        results: list[ProjectDocResult] = []
        for abs_path, category in self._discover_project_doc_files(request):
            # abs_path came from globbing UNDER self._base_dir → relative_to is safe.
            rel = abs_path.relative_to(self._base_dir).as_posix()
            try:
                content = abs_path.read_text(encoding="utf-8")
                index_response = await self.index_document(
                    db,
                    IndexRequest(
                        source_type="markdown",
                        source_path=rel,                       # clean relative DB id
                        content=content,
                        metadata={"category": category},
                    ),
                )
                results.append(ProjectDocResult(
                    source_path=rel,
                    status=index_response.status,              # narrower Literal → wider: OK
                    chunks_created=index_response.chunks_created,
                    error=None,
                ))
            except (OSError, ValueError) as exc:
                # FileNotFoundError ⊂ OSError ; UnicodeDecodeError ⊂ ValueError.
                # EmbeddingError / SQLAlchemyError are NOT caught → batch-fatal.
                logger.warning("rag.index_project_docs_file_failed",
                               source_path=rel, error=str(exc),
                               error_type=type(exc).__name__)
                results.append(ProjectDocResult(
                    source_path=rel, status="failed",
                    chunks_created=0, error=str(exc)))

        duration_ms = (time.time() - start) * 1000
        summary = IndexProjectDocsResponse(
            results=results,
            total_files=len(results),
            indexed=sum(r.status == "indexed" for r in results),
            updated=sum(r.status == "updated" for r in results),
            unchanged=sum(r.status == "unchanged" for r in results),
            failed=sum(r.status == "failed" for r in results),
            total_chunks=sum(r.chunks_created for r in results),
            duration_ms=duration_ms,
        )
        logger.info("rag.index_project_docs_completed",
                    total_files=summary.total_files, indexed=summary.indexed,
                    updated=summary.updated, unchanged=summary.unchanged,
                    failed=summary.failed, total_chunks=summary.total_chunks,
                    duration_ms=duration_ms)
        return summary
```

IMPORTS to add to `service.py`: extend the existing
`from app.features.rag.schemas import (...)` block (lines 29-38) with
`IndexProjectDocsRequest`, `IndexProjectDocsResponse`, `ProjectDocResult`. `time`,
`Path`, `IndexRequest`, `AsyncSession`, `logger` are already imported.

### Backend route (`app/features/rag/routes.py`)

Add `IndexProjectDocsRequest, IndexProjectDocsResponse` to the schema import block
(lines 12-19), then append after the `index_document` route:

```python
@router.post(
    "/index/project-docs",
    response_model=IndexProjectDocsResponse,
    summary="Index bundled project documentation",
    description="Discover and index docs/**, PRPs/**, and selected root markdown. "
                "Idempotent via content hash; per-file + aggregate summary.",
)
async def index_project_docs(
    request: IndexProjectDocsRequest,
    db: AsyncSession = Depends(get_db),
) -> IndexProjectDocsResponse:
    logger.info("rag.index_project_docs_request_received",
                include_docs=request.include_docs,
                include_prps=request.include_prps,
                include_root=request.include_root)
    service = RAGService()
    try:
        response = await service.index_project_docs(db=db, request=request)
        logger.info("rag.index_project_docs_request_completed",
                    total_files=response.total_files,
                    total_chunks=response.total_chunks, failed=response.failed)
        return response
    except EmbeddingError as e:                      # mirror index_document route
        logger.error("rag.index_project_docs_request_failed", error=str(e),
                     error_type=type(e).__name__, exc_info=True)
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY,
                            detail=f"Embedding generation failed: {e}") from e
    except SQLAlchemyError as e:
        logger.error("rag.index_project_docs_request_failed", error=str(e),
                     error_type=type(e).__name__, exc_info=True)
        raise DatabaseError(message="Failed to index project docs",
                            details={"error": str(e)}) from e
```

NO explicit `status_code` → default `200` (this is a mixed, idempotent batch — not a
single-resource create). `/index/project-docs` and `/index` are distinct static
paths — no route-ordering conflict. Do NOT add a `FileNotFoundError` handler: the
service swallows per-file read errors as `status="failed"` and never raises it.

### Frontend hook (`frontend/src/hooks/use-rag-sources.ts`) — mirror `useIndexDocument`

```ts
// extend the type import with IndexProjectDocsRequest, IndexProjectDocsResponse
export function useIndexProjectDocs() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (body: IndexProjectDocsRequest) =>
      api<IndexProjectDocsResponse>('/rag/index/project-docs', { method: 'POST', body }),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['rag-sources'] })
    },
  })
}
```

### Admin button (`frontend/src/pages/admin.tsx` → `RagSourcesPanel`)

- Add `Library` to the lucide-react import (admin.tsx:4-21).
- In `RagSourcesPanel`, call `const indexProjectDocs = useIndexProjectDocs()`.
- Add a handler:

```tsx
const handleIndexProjectDocs = async () => {
  try {
    const r = await indexProjectDocs.mutateAsync({})            // {} → all roots
    const summary =
      `Indexed ${r.indexed}, updated ${r.updated}, unchanged ${r.unchanged}, ` +
      `${r.failed} failed — ${r.total_chunks} chunks`
    if (r.failed > 0) toast.warning(summary)
    else toast.success(summary)
  } catch (err) {
    toast.error(err instanceof Error ? err.message : 'Project-docs indexing failed')
  }
}
```

- In the `CardHeader`, wrap the existing "Index Document" `<Dialog>` and a new
  `<Button>` in a `<div className="flex gap-2">`:

```tsx
<Button variant="outline" size="sm"
        onClick={handleIndexProjectDocs} disabled={indexProjectDocs.isPending}>
  {indexProjectDocs.isPending
    ? <Loader2 className="h-4 w-4 mr-2 animate-spin" />
    : <Library className="h-4 w-4 mr-2" />}
  Index Project Docs
</Button>
```

Do NOT restructure the existing "Index Document" dialog — only wrap + add beside it.
No confirm dialog — indexing is additive and idempotent.

### list of tasks (in execution order)

```yaml
Task 0 — PRECONDITION:
  - Find or open a GitHub issue (promote docs/optional-features/01-rag-corpus-manager.md).
  - VERIFY: gh issue view <N> --json state  → "OPEN".
  - git switch -c feat/rag-index-project-docs   (off an up-to-date dev).

Task 1 — MODIFY app/features/rag/tests/conftest.py:
  - FIND:    DocumentSource.source_path.like("test-%")        # line 46
  - REPLACE: DocumentSource.source_path.like("%test-%")
  - Use the Edit tool (preserve CRLF). git diff --stat → 1 line changed.

Task 2 — MODIFY app/features/rag/schemas.py:
  - APPEND IndexProjectDocsRequest, ProjectDocResult, IndexProjectDocsResponse
    after DeleteResponse. MIRROR IndexRequest/IndexResponse style.

Task 3 — MODIFY app/features/rag/service.py:
  - ADD module constant _PROJECT_ROOT_FILES after the imports.
  - EXTEND the rag.schemas import block with the 3 new names.
  - ADD RAGService._discover_project_doc_files (pure/sync) and
    RAGService.index_project_docs (async orchestrator).

Task 4 — MODIFY app/features/rag/routes.py:
  - EXTEND the rag.schemas import block with IndexProjectDocsRequest/Response.
  - ADD the POST /rag/index/project-docs route after index_document.

Task 5 — MODIFY app/features/rag/tests/test_schemas.py:
  - ADD cases: empty IndexProjectDocsRequest() defaults all True;
    model_validate({}) ok; unknown field → ValidationError (extra="forbid");
    ProjectDocResult rejects an out-of-Literal status; IndexProjectDocsResponse
    round-trips a populated payload.

Task 6 — MODIFY app/features/rag/tests/test_service.py:
  - ADD a UNIT test for _discover_project_doc_files: build a tmp_path tree
    (docs/test-a.md, docs/sub/test-b.md, PRPs/test-c.md, README.md, notes.txt),
    RAGService(base_dir=str(tmp_path)), assert discovery counts, category tags,
    .md-only filtering, root allow-list, and include_* toggles. No DB, no mocks.

Task 7 — MODIFY app/features/rag/tests/test_routes.py:
  - ADD @pytest.mark.integration TestIndexProjectDocsEndpoint (see pseudocode).

Task 8 — MODIFY frontend/src/types/api.ts:
  - ADD the 3 interfaces in the // === RAG === block.

Task 9 — MODIFY frontend/src/hooks/use-rag-sources.ts:
  - ADD useIndexProjectDocs (extend the type import).

Task 10 — MODIFY frontend/src/pages/admin.tsx:
  - ADD Library to the lucide import; ADD the button + handler in RagSourcesPanel.

Task 11 — MODIFY docs/_base/API_CONTRACTS.md:
  - ADD a rag row:
    | rag | POST | /rag/index/project-docs | Bulk-index bundled docs/, PRPs/, and root markdown; per-file + aggregate summary; idempotent via content hash |

Task 12 — Run the full Validation Loop (Levels 1-4); fix until green.
```

### Per-task pseudocode (highest-risk task)

```python
# Task 7 — app/features/rag/tests/test_routes.py — the integration test.
# IMPORTS to add: `from functools import partial`,
#   `from app.features.rag.service import RAGService`,
#   `from app.features.rag.embeddings import EmbeddingError`  (EmbeddingService already imported).

@pytest.mark.integration
class TestIndexProjectDocsEndpoint:
    @pytest.mark.asyncio
    async def test_indexes_discovered_docs(self, client, tmp_path):
        # fixture files — NON-EMPTY, names contain `test-` so conftest cleanup catches them
        (tmp_path / "docs").mkdir()
        (tmp_path / "PRPs").mkdir()
        (tmp_path / "docs" / "test-proj-1.md").write_text("# A\n\nAlpha content.")
        (tmp_path / "PRPs" / "test-proj-2.md").write_text("# B\n\nBeta content.")
        mock = create_mock_embedding_service()
        with patch("app.features.rag.routes.RAGService",
                   partial(RAGService, base_dir=str(tmp_path))), \
             patch("app.features.rag.service.get_embedding_service", return_value=mock):
            r1 = await client.post("/rag/index/project-docs", json={})
            assert r1.status_code == 200
            d1 = r1.json()
            assert d1["total_files"] == 2 and d1["indexed"] == 2
            assert d1["total_chunks"] >= 2 and d1["failed"] == 0
            # idempotent re-run
            r2 = await client.post("/rag/index/project-docs", json={})
            assert r2.json()["unchanged"] == 2

    @pytest.mark.asyncio
    async def test_empty_roots_returns_zero(self, client, tmp_path):
        mock = create_mock_embedding_service()
        with patch("app.features.rag.routes.RAGService",
                   partial(RAGService, base_dir=str(tmp_path))), \
             patch("app.features.rag.service.get_embedding_service", return_value=mock):
            r = await client.post("/rag/index/project-docs", json={})
        assert r.status_code == 200 and r.json()["total_files"] == 0

    @pytest.mark.asyncio
    async def test_unknown_field_rejected(self, client):
        r = await client.post("/rag/index/project-docs", json={"bogus": True})
        assert r.status_code == 422                       # extra="forbid"

    @pytest.mark.asyncio
    async def test_embedding_failure_returns_502(self, client, tmp_path):
        (tmp_path / "docs").mkdir()
        (tmp_path / "docs" / "test-proj-3.md").write_text("# C\n\nGamma content.")
        mock = create_mock_embedding_service()
        mock.embed_texts = AsyncMock(side_effect=EmbeddingError("no key"))
        with patch("app.features.rag.routes.RAGService",
                   partial(RAGService, base_dir=str(tmp_path))), \
             patch("app.features.rag.service.get_embedding_service", return_value=mock):
            r = await client.post("/rag/index/project-docs", json={})
        assert r.status_code == 502
```

### Integration Points

```yaml
DATABASE:
  - migration: NONE — no schema change (category rides in DocumentSource.metadata_ JSONB).
ROUTES:
  - app/features/rag/routes.py — new route on the EXISTING `/rag` APIRouter.
  - app/main.py — NO change (rag router already wired at main.py:142).
CONFIG:
  - NONE — `_PROJECT_ROOT_FILES` is a code constant, not a Settings field. No .env.example change.
FRONTEND:
  - frontend/src/hooks/use-rag-sources.ts — new hook beside useIndexDocument.
  - frontend/src/pages/admin.tsx — button in RagSourcesPanel; invalidates ['rag-sources'].
DOCS:
  - docs/_base/API_CONTRACTS.md — one new rag endpoint row.
```

## Validation Loop

### Level 1: Syntax & Style

```bash
# Run from the repo root. Fix every error before proceeding.
uv run ruff check . --fix
uv run ruff format .
git diff --stat        # CRLF guard: confirm NO whole-file churn on the .py edits
```

### Level 2: Type Checks + Unit Tests

```bash
uv run mypy app/ && uv run pyright app/          # both --strict — both gate merge
uv run pytest app/features/rag/ -v -m "not integration"
uv run pytest app/core/tests/test_strict_mode_policy.py -v   # must still pass
```

Watch: the `index_response.status` (3-Literal) → `ProjectDocResult.status`
(4-Literal) assignment, and `sum(r.status == "..." for r in results)` returning
`int`, are the most likely strict-mode snags — both are fine, but verify.

### Level 3: Integration Tests

```bash
docker compose up -d
uv run alembic upgrade head
uv run pytest app/features/rag/tests/test_routes.py -v -m integration
# If they fail on a stale local Postgres:
#   docker compose down -v && docker compose up -d && uv run alembic upgrade head
```

### Level 4: Frontend + Manual / Browser QA

```bash
cd frontend && pnpm tsc --noEmit && pnpm lint && pnpm test --run
```

Manual dogfood (per `.claude/rules/ui-design.md` — use the `webapp-testing` skill):

```bash
# Backend MUST run from the repo root so Path.cwd() == repo root.
uv run uvicorn app.main:app --reload --port 8123
cd frontend && ./node_modules/.bin/vite --host 0.0.0.0
```

1. `curl -s -X POST localhost:8123/rag/index/project-docs -H 'content-type: application/json' -d '{}' | head -c 400`
   → `200`, a JSON summary with `total_files` ≈ 110+.
2. Open `/admin` → "RAG Sources" tab → on a fresh DB it shows `0 sources • 0 chunks`.
3. Click **Index Project Docs** → spinner → toast summary → the source list +
   counts populate (the `['rag-sources']` invalidation).
4. Open `/knowledge` → the empty state is gone; "N sources • M chunks" reflects
   the corpus; a semantic search ("How does backtesting prevent leakage?") returns
   cited chunks.
5. Click **Index Project Docs** again → toast shows all `unchanged` (idempotency).

## Final validation Checklist

- [ ] `uv run ruff check .` and `uv run ruff format --check .` — clean.
- [ ] `uv run mypy app/` and `uv run pyright app/` — clean (`--strict`).
- [ ] `uv run pytest app/features/rag/ -v -m "not integration"` — green.
- [ ] `uv run pytest app/features/rag/tests/test_routes.py -v -m integration` — green;
      no `document_source` row with `source_path` containing `test-` remains.
- [ ] `uv run pytest app/core/tests/test_strict_mode_policy.py -v` — still green.
- [ ] `cd frontend && pnpm tsc --noEmit && pnpm lint && pnpm test --run` — green.
- [ ] `git diff --stat` shows small, line-level diffs on the `.py` files — NO
      whole-file CRLF→LF churn.
- [ ] Manual: Index Project Docs populates the corpus; a re-run is all `unchanged`;
      Knowledge search returns cited chunks.
- [ ] `docs/_base/API_CONTRACTS.md` lists `POST /rag/index/project-docs`.
- [ ] Commit `feat(rag,ui): index bundled project docs into the RAG corpus (#<issue>)`
      — references the open issue, NO AI co-author / "Generated with" trailer; PR
      into `dev`.

---

## Anti-Patterns to Avoid

- ❌ Don't re-implement chunking / embedding / hashing — orchestrate
  `index_document`.
- ❌ Don't add an Alembic migration — there is no schema change.
- ❌ Don't touch `app/main.py` — the `rag` router is already wired.
- ❌ Don't "fix" `index_document`'s `if request.content:` branch — it is shared
  with `POST /rag/index`; the empty-file edge is already handled by the per-file
  `OSError` catch.
- ❌ Don't store absolute paths as `source_path` — use the clean relative POSIX id.
- ❌ Don't rewrite existing `.py` files with the Write tool — CRLF will flip to LF.
  Use Edit; verify with `git diff --stat`.
- ❌ Don't widen scope into the "Full Version" (chunk preview, re-index, stale
  detection, Knowledge filters) — that is a separate, deferred PR.
- ❌ Don't catch `EmbeddingError` / `SQLAlchemyError` per file — they are
  batch-fatal and must reach the route's `502` / `problem+json` handlers.
- ❌ Don't claim the UI works on a green `tsc` alone — dogfood it in a browser.

## Confidence Score

**8.5 / 10** for one-pass implementation success.

The feature is almost entirely additive on a mature, well-tested slice; every
endpoint shape, schema field, and pattern is pinned to a verified source line. The
residual risks are all identified and mitigated in-PRP: (1) CRLF EOL churn on the
`.py` edits — mitigated by the explicit Edit-tool + `git diff --stat` gotcha;
(2) integration-test DB cleanup of nested fixture paths — mitigated by the Task-1
`LIKE` widening + `test-`-token fixture names; (3) the `RAGService` `base_dir`
injection in the route test — mitigated by the documented `partial(...)` patch
point; (4) the empty-file / falsy-`content` interaction — mitigated by non-empty
fixtures + the `OSError` safety net. The half-point deduction is for the manual
browser-QA step, which depends on a live embedding provider being configured and
reachable in the implementer's environment.
