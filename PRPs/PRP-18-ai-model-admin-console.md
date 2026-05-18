name: "PRP-18 — AI Model Admin Console (runtime-editable, Ollama-capable)"
description: |
  Add an "AI Models" admin surface that lets an operator view and **change**
  the agent LLM model, the RAG embedding model, and provider API keys at
  runtime — including running the chat agent fully local via Ollama. Changes
  persist in a new `app_config` DB table and take effect live (no restart) by
  mutating the in-process `Settings` singleton and invalidating the agent /
  embedding caches.

## Purpose

One-pass implementation of a full-stack feature: a new `config` vertical slice
(backend) + an "AI Models" tab on the existing `/admin` page (frontend). The PRP
carries every file path, code snippet, library URL, and gotcha needed.

## Core Principles

1. **Context is King** — all referenced files/snippets are in this document.
2. **Validation Loops** — executable gates in the Validation section.
3. **Follow CLAUDE.md** — vertical slices, RFC 7807, Pydantic v2, strict typing,
   `type(scope): description (#issue)` commits, branch off `dev`.
4. **Progressive Success** — backend slice → cache wiring → Ollama agent → routes
   → frontend. Each step has a gate.

---

## Goal

Ship `http://localhost:5173/admin` → **AI Models** tab that can:

- Display the **effective** AI-model configuration (agent LLM + RAG embeddings).
- **Edit and persist** those values; edits apply live without a backend restart.
- Add **Ollama as a first-class agent LLM provider** (`ollama:<model>`), not just
  a RAG embedding option.
- Show **provider connectivity** (Ollama reachable + its local model list; cloud
  key presence) and let the operator **set/replace API keys** from the UI.

End state: an operator can switch the chat agent from `anthropic:claude-sonnet-4-5`
to `ollama:llama3.1`, hit Save, open `/chat`, and the next message runs locally —
no process restart, no `.env` edit.

## Why

- **User value** — the system currently requires hand-editing `.env` + restarting
  uvicorn to change a model. An operator-facing console removes that friction.
- **Portfolio value** — "swap any AI model, including a fully-local Ollama path,
  from a dashboard" is a strong demo of the agentic + RAG layers.
- **Integration** — extends the existing `/admin` page (RAG / Aliases / Seeder
  tabs) and the existing Ollama embedding support (`app/features/rag/embeddings.py`).

## What

### User-visible behavior

- `/admin` gains a 4th tab **AI Models** with four cards: Agent LLM, RAG
  Embeddings, API Keys, Provider Health.
- Editing a field + Save persists it and applies it immediately.
- The Agent LLM provider dropdown includes `ollama`; when `ollama` is picked the
  model field is a dropdown populated from the host's pulled Ollama models.
- Provider Health shows Ollama reachability + local models, and cloud key presence.

### Technical requirements

- New `config` vertical slice: `app/features/config/{models,schemas,service,routes,tests}.py`.
- New `app_config` table (Alembic migration) — key/value override store.
- A startup hook applies persisted overrides onto the `Settings` singleton.
- A save path validates → upserts DB → mutates `Settings` → resets agent +
  embedding caches.
- `ollama` added to the agent provider allow-list; PydanticAI agent built via an
  Ollama-aware model factory.
- All errors RFC 7807; request bodies Pydantic v2; `mypy --strict` + `pyright --strict` clean.

### Success Criteria

- [ ] `GET /config/ai` returns the effective AI config; API keys are **masked**, never raw.
- [ ] `PATCH /config/ai` persists changes to `app_config`, mutates `Settings`, resets caches.
- [ ] `GET /config/providers/health` reports Ollama + cloud provider status.
- [ ] `GET /config/ollama/models` lists the host's pulled Ollama models.
- [ ] Setting `agent_default_model` to `ollama:<model>` makes `/chat` run via Ollama with **no restart**.
- [ ] Persisted overrides survive a backend restart (re-applied on startup).
- [ ] `/admin` → AI Models tab edits and saves all four cards.
- [ ] All validation gates green (ruff, mypy, pyright, pytest unit + integration, frontend tsc/lint/test, `alembic upgrade head`).

## All Needed Context

### Documentation & References

```yaml
- url: https://ai.pydantic.dev/models/openai/#ollama
  why: Canonical pattern for running a PydanticAI Agent against Ollama via the
       OpenAI-compatible endpoint. Shows OpenAIChatModel + OllamaProvider usage.
  critical: Ollama's OpenAI-compatible base is "<ollama_base_url>/v1". The agent
            model object is passed to Agent(model=...) instead of a "provider:model" string.

- url: https://ai.pydantic.dev/api/providers/
  why: OllamaProvider constructor signature (base_url kwarg). Verify with context7
       (resolve-library-id "pydantic-ai" → query-docs) if the import path differs.

- url: https://ai.pydantic.dev/api/models/openai/
  why: OpenAIChatModel signature. In pydantic-ai 1.96 the class is OpenAIChatModel
       (OpenAIModel is a deprecated alias). Import: from pydantic_ai.models.openai import OpenAIChatModel

- url: https://github.com/ollama/ollama/blob/main/docs/api.md#list-local-models
  why: GET /api/tags response shape — {"models":[{"name","model","size","details":{...}}]}.
       Used for both the health check and the model picker.

- url: https://github.com/ollama/ollama/blob/main/docs/openai.md
  why: Confirms Ollama's /v1/embeddings + /v1/chat/completions OpenAI-compat surface.

- url: https://tanstack.com/query/latest/docs/framework/react/guides/mutations
  why: useMutation + queryClient.invalidateQueries pattern (mirror use-seeder.ts).

- file: app/features/seeder/routes.py
  why: THE slice to mirror — a control-plane slice with no DB models of its own,
       APIRouter(prefix=..., tags=...), HTTPException for RFC 7807, get_db dependency.

- file: app/features/seeder/schemas.py
  why: Pydantic v2 request/response schema patterns, field_validator usage.

- file: app/features/rag/embeddings.py
  why: Ollama HTTP client pattern (httpx.AsyncClient base_url + timeout), the
       module-global _embedding_provider singleton + get_embedding_service().

- file: app/features/agents/agents/base.py
  why: get_model_identifier / get_model_settings / validate_api_key_for_model —
       the exact functions to extend for Ollama.

- file: app/features/agents/agents/experiment.py
  why: create_experiment_agent() builds Agent(model=...); _experiment_agent global
       singleton + get_experiment_agent(). rag_assistant.py mirrors this.

- file: app/core/config.py
  why: Settings model + the agent_default_model/agent_fallback_model field_validator
       whose provider allow-list must gain "ollama".

- file: alembic/versions/d6e0f2g3h456_create_agent_session_table.py
  why: Migration template — revision id style, upgrade/downgrade, JSONB column.

- file: frontend/src/pages/admin.tsx
  why: The existing Tabs structure to extend (add a 4th TabsTrigger/TabsContent).

- file: frontend/src/hooks/use-seeder.ts
  why: TanStack Query hook pattern to mirror exactly (useQuery/useMutation/invalidate).

- file: frontend/src/lib/api.ts
  why: api<T>() fetch wrapper + ApiError — how every endpoint is called.

- file: frontend/src/lib/constants.ts
  why: ROUTES / NAV_ITEMS — no new route needed (/admin exists), no edit expected here.

- file: app/features/seeder/tests/test_routes.py
  why: Route-test pattern — TestClient, patch get_settings/get_db, patch service fns.

- file: app/features/rag/tests/test_embeddings.py
  why: How to unit-test httpx/Ollama calls with patched get_settings (no live calls).

- file: app/core/tests/test_strict_mode_policy.py
  why: AST invariant — a ConfigDict(strict=True) request model may not have a bare
       date/datetime/time/UUID/Decimal field. Our config schemas use only
       str/int/float/bool, so they pass — keep it that way.
```

### Current Codebase tree (relevant subset)

```bash
app/
  core/
    config.py            # Settings + get_settings() @lru_cache  ← EDIT (allow-list, validator extraction)
    database.py          # get_db / engine / async_session
    problem_details.py   # RFC 7807 envelope (HTTPException auto-converts)
  main.py                # router wiring + lifespan  ← EDIT (wire config router + startup hook)
  features/
    agents/
      agents/base.py     # model helpers  ← EDIT (build_agent_model, ollama in validate)
      agents/experiment.py   # _experiment_agent singleton  ← EDIT (use build_agent_model + reset hook)
      agents/rag_assistant.py# _rag_assistant_agent singleton  ← EDIT (same)
      service.py
    rag/
      embeddings.py      # _embedding_provider singleton  ← EDIT (add reset_embedding_service())
    seeder/              # control-plane slice — MIRROR THIS
alembic/versions/        # 8 migrations  ← ADD one
frontend/src/
  pages/admin.tsx        # Tabs(rag|aliases|seeder)  ← EDIT (+models tab)
  hooks/use-seeder.ts    # hook pattern to mirror
  lib/api.ts
  types/api.ts           # ← EDIT (+config types)
  components/            # demo/ chat/ ... (no admin/ dir yet)
```

### Desired Codebase tree (files added)

```bash
app/features/config/
  __init__.py
  models.py              # AppConfig ORM (app_config table)
  schemas.py             # AIModelConfig, AIModelConfigUpdate, ProviderHealth, OllamaModel, ApiKeyStatus
  service.py             # load/save overrides, apply to Settings, cache resets, connectivity tests
  routes.py              # APIRouter(prefix="/config", tags=["config"])
  tests/
    __init__.py
    conftest.py
    test_schemas.py
    test_service.py
    test_routes.py
alembic/versions/<rev>_create_app_config_table.py
frontend/src/
  hooks/use-config.ts                      # useAIConfig, useUpdateAIConfig, useProviderHealth, useOllamaModels
  components/admin/ai-models-panel.tsx     # the "AI Models" tab UI
```

### Known Gotchas & Library Quirks

```python
# CRITICAL: get_settings() is @lru_cache'd — ONE Settings object lives for the
#   process. Mutating its attributes (settings.agent_default_model = "x") is the
#   intended override mechanism here. BaseSettings is NOT frozen and
#   validate_assignment is False — assignment will NOT re-run field validators,
#   so the config SERVICE must validate BEFORE setattr.

# CRITICAL: Agents are module-global singletons:
#   experiment.py:_experiment_agent, rag_assistant.py:_rag_assistant_agent.
#   embeddings.py:_embedding_provider is likewise a module global.
#   After any model/key change you MUST null these out or the change is invisible.
#   Add reset functions; the config service calls them on every successful save.

# CRITICAL: app/core/config.py has a field_validator on agent_default_model /
#   agent_fallback_model with valid_providers = ["anthropic","openai",
#   "google-gla","google-vertex"]. Ollama as an AGENT provider REQUIRES adding
#   "ollama" to that list, else Settings() / setattr-validation rejects it.

# CRITICAL: PydanticAI cloud providers accept a plain "provider:model" STRING as
#   Agent(model=...). Ollama does NOT — you must pass a model OBJECT:
#   OpenAIChatModel(model_name, provider=OllamaProvider(base_url=f"{url}/v1")).
#   So introduce build_agent_model(identifier) -> str | Model.

# GOTCHA: validate_api_key_for_model() exports keys to os.environ ONLY IF the var
#   is absent ("if 'OPENAI_API_KEY' not in os.environ"). When the operator
#   REPLACES a key via the UI, the save path must overwrite os.environ[...]
#   unconditionally, or PydanticAI keeps using the stale key.
#   Ollama needs NO key — skip validate_api_key_for_model for provider == "ollama".

# GOTCHA: Ollama's OpenAI-compatible endpoints live under /v1
#   (/v1/chat/completions, /v1/embeddings). The model-list endpoint is the NATIVE
#   /api/tags (NOT under /v1). ollama_base_url default is http://localhost:11434.

# GOTCHA: rag_embedding_dimension is load-bearing — rag_chunk.embedding is a fixed
#   pgvector dimension (see migration c5d9e1f2g345). Changing provider/model/
#   dimension while rag_chunk rows exist breaks retrieval. The PATCH handler MUST
#   guard: if the change alters rag_embedding_dimension AND chunks exist, return
#   409 application/problem+json unless an explicit force=true is passed.

# GOTCHA: NEVER return raw API keys in any GET response and NEVER log key values
#   (.claude/rules/security-patterns.md). Return ApiKeyStatus { is_set: bool,
#   masked: "sk-ant-…" + last 4 }. Storing keys in app_config is the documented
#   tradeoff the operator chose (Q4) — keep them out of logs and out of GETs.

# GOTCHA: Pydantic v2 strict mode — request bodies KEEP ConfigDict(strict=True).
#   All config fields are str/int/float/bool (JSON-native) so NO Field(strict=False)
#   override is needed and test_strict_mode_policy.py stays green. Do not add a
#   date/UUID/Decimal field to a strict request model.

# GOTCHA: The startup hook reads app_config via the DB. On a brand-new DB the
#   table may not exist yet — wrap the load in try/except, log a warning, and let
#   the app boot on env defaults. Never let a missing table crash startup.
```

## Implementation Blueprint

### Data models and structure

```python
# app/features/config/models.py  — mirror agents/models.py ORM style (Mapped[], mapped_column)
from datetime import datetime
from sqlalchemy import String, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column
from app.core.database import Base   # confirm Base import path from agents/models.py

class AppConfig(Base):
    """Key/value override store for runtime-editable settings."""
    __tablename__ = "app_config"
    key: Mapped[str] = mapped_column(String(100), primary_key=True)
    value: Mapped[dict] = mapped_column(JSONB, nullable=False)  # {"v": <scalar>}
    updated_at: Mapped[datetime] = mapped_column(
        server_default=func.now(), onupdate=func.now()
    )

# app/features/config/schemas.py  — Pydantic v2, ConfigDict(strict=True) on request body
ALLOWED_OVERRIDE_KEYS = {
    "agent_default_model", "agent_fallback_model", "agent_temperature",
    "agent_max_tokens", "agent_thinking_budget",
    "rag_embedding_provider", "rag_embedding_model", "rag_embedding_dimension",
    "ollama_base_url", "ollama_embedding_model",
    "openai_api_key", "anthropic_api_key", "google_api_key",   # secret keys
}
SECRET_KEYS = {"openai_api_key", "anthropic_api_key", "google_api_key"}

class ApiKeyStatus(BaseModel):       # response only
    provider: str                   # "openai" | "anthropic" | "google"
    is_set: bool
    masked: str | None               # e.g. "sk-ant-…3f9a"  (never the full value)

class AIModelConfig(BaseModel):      # GET /config/ai response
    agent_default_model: str
    agent_fallback_model: str
    agent_temperature: float
    agent_max_tokens: int
    agent_thinking_budget: int | None
    rag_embedding_provider: str
    rag_embedding_model: str
    rag_embedding_dimension: int
    ollama_base_url: str
    ollama_embedding_model: str
    api_keys: list[ApiKeyStatus]
    overridden_keys: list[str]       # which keys currently come from app_config (not env)

class AIModelConfigUpdate(BaseModel):  # PATCH /config/ai request
    model_config = ConfigDict(strict=True)   # repo policy; all fields JSON-native
    agent_default_model: str | None = None
    agent_fallback_model: str | None = None
    agent_temperature: float | None = Field(default=None, ge=0.0, le=2.0)
    agent_max_tokens: int | None = Field(default=None, ge=1)
    agent_thinking_budget: int | None = None
    rag_embedding_provider: Literal["openai", "ollama"] | None = None
    rag_embedding_model: str | None = None
    rag_embedding_dimension: int | None = Field(default=None, ge=1)
    ollama_base_url: str | None = None
    ollama_embedding_model: str | None = None
    openai_api_key: str | None = None
    anthropic_api_key: str | None = None
    google_api_key: str | None = None
    force: bool = False              # bypass the dimension-change guard

class OllamaModel(BaseModel):
    name: str
    size_bytes: int | None = None
    family: str | None = None

class ProviderHealth(BaseModel):
    provider: str                    # "ollama" | "openai" | "anthropic" | "google"
    reachable: bool
    detail: str
    models: list[str] = []           # populated for ollama
```

### List of tasks (in order)

```yaml
Task 0 — Issue + branch:
  - Create a GitHub issue: feat(api,ui): AI model admin console with Ollama support.
  - git switch -c feat/config-ai-model-admin-console  (off up-to-date dev)
  - Every commit references that issue number.

Task 1 — MODIFY app/core/config.py:
  - EXTRACT the body of the agent_default_model/agent_fallback_model validator into
    a module-level function `validate_model_identifier(v: str) -> str` so the
    config service can reuse it. The @field_validator delegates to it.
  - ADD "ollama" to valid_providers list.
  - KEEP the existing behavior identical for cloud providers.

Task 2 — MODIFY .env.example:
  - Document that AGENT_DEFAULT_MODEL now also accepts ollama:<model>
    (e.g. AGENT_DEFAULT_MODEL=ollama:llama3.1). Add a commented example.
  - No new env vars are required (app_config is the override store).

Task 3 — CREATE alembic/versions/<rev>_create_app_config_table.py:
  - MIRROR alembic/versions/d6e0f2g3h456_create_agent_session_table.py.
  - upgrade(): create table app_config(key VARCHAR(100) PK, value JSONB NOT NULL,
    updated_at TIMESTAMP server_default now()).
  - downgrade(): drop table app_config.
  - down_revision = current head (run `uv run alembic heads` to find it).

Task 4 — CREATE app/features/config/__init__.py + models.py:
  - AppConfig ORM as in the blueprint. Confirm Base import path against
    app/features/agents/models.py.

Task 5 — CREATE app/features/config/schemas.py:
  - All schemas from the blueprint. ConfigDict(strict=True) on AIModelConfigUpdate.

Task 6 — MODIFY app/features/rag/embeddings.py:
  - ADD `def reset_embedding_service() -> None:` that sets the module global
    `_embedding_provider = None` (so the next get_embedding_service() rebuilds).

Task 7 — MODIFY app/features/agents/agents/experiment.py + rag_assistant.py:
  - ADD `def reset_experiment_agent()` / `reset_rag_assistant_agent()` that null
    the module-global singleton.
  - CHANGE `model = get_model_identifier()` → `model = build_agent_model(get_model_identifier())`.

Task 8 — MODIFY app/features/agents/agents/base.py:
  - ADD build_agent_model(identifier: str) -> "str | Model":
      * provider, name = identifier.split(":", 1)
      * if provider == "ollama": return OpenAIChatModel(name,
          provider=OllamaProvider(base_url=settings.ollama_base_url.rstrip("/") + "/v1"))
      * else: return identifier  (string, unchanged cloud path)
  - MODIFY validate_api_key_for_model: if provider == "ollama" → return early
    (no key needed).
  - ADD reset_agent_caches() convenience that calls reset_experiment_agent()
    + reset_rag_assistant_agent()  (import locally to avoid cycles).
  - Imports: from pydantic_ai.models.openai import OpenAIChatModel
             from pydantic_ai.providers.ollama import OllamaProvider
    (both verified available in pydantic-ai 1.96.0; if an import fails, confirm
     the path via context7 query-docs for "pydantic-ai").

Task 9 — CREATE app/features/config/service.py:
  - get_effective_config(db) -> AIModelConfig: read Settings + which keys are in
    app_config (overridden_keys); mask secrets.
  - apply_overrides_on_startup(db) -> None: load all app_config rows, setattr onto
    get_settings(), export secret keys to os.environ. Try/except-safe.
  - update_config(db, payload: AIModelConfigUpdate) -> AIModelConfig:
      1. Validate model identifiers via validate_model_identifier (incl. ollama).
      2. If rag_embedding_dimension changes AND rag_chunk rows exist AND not force
         → raise HTTPException(409, "embedding dimension change requires re-index").
      3. Upsert each provided non-None field into app_config (ON CONFLICT DO UPDATE).
      4. setattr onto get_settings() singleton; for secret keys also set
         os.environ[KEY] unconditionally.
      5. reset_agent_caches() + reset_embedding_service().
      6. Return get_effective_config(db).
  - get_provider_health() -> list[ProviderHealth]: ollama → httpx GET /api/tags
    (reachable + model names); openai/anthropic/google → key-presence (+ optional
    cheap GET /v1/models behind a short timeout, swallow errors → reachable=False).
  - list_ollama_models() -> list[OllamaModel]: httpx GET {ollama_base_url}/api/tags,
    parse {"models":[...]}. Raise HTTPException(502) on connection failure.
  - NEVER log key values; log key NAMES + bool only.

Task 10 — CREATE app/features/config/routes.py:
  - router = APIRouter(prefix="/config", tags=["config"])  (mirror seeder/routes.py)
  - GET  /config/ai                 -> AIModelConfig
  - PATCH /config/ai                -> AIModelConfig          (body AIModelConfigUpdate)
  - GET  /config/providers/health   -> list[ProviderHealth]
  - GET  /config/ollama/models      -> list[OllamaModel]
  - db: AsyncSession = Depends(get_db). HTTPException for errors (RFC 7807 auto).

Task 11 — MODIFY app/main.py:
  - import config router; app.include_router(config_router).
  - In lifespan() AFTER configure_logging(), open an async session and call
    config.service.apply_overrides_on_startup(db) inside try/except (warn-and-continue).

Task 12 — CREATE app/features/config/tests/ (conftest, test_schemas, test_service, test_routes):
  - Mirror seeder/tests/test_routes.py + rag/tests/test_embeddings.py patterns.
  - Unit: mask logic, validate_model_identifier accepts "ollama:llama3.1" rejects
    "ollama:" and "bad:x"; build_agent_model returns OpenAIChatModel for ollama,
    str for cloud; update_config resets caches (assert globals nulled); httpx
    Ollama /api/tags mocked. Mark DB-touching tests @pytest.mark.integration.

Task 13 — CREATE frontend/src/types/api.ts additions:
  - AIModelConfig, AIModelConfigUpdate, ProviderHealth, OllamaModel, ApiKeyStatus
    mirroring the Pydantic schemas.

Task 14 — CREATE frontend/src/hooks/use-config.ts:
  - useAIConfig()        -> useQuery(['config','ai'], () => api('/config/ai'))
  - useProviderHealth()  -> useQuery(['config','health'], ...)
  - useOllamaModels()    -> useQuery(['config','ollama-models'], ...) enabled on demand
  - useUpdateAIConfig()  -> useMutation(PATCH /config/ai) onSuccess invalidate
                            ['config',*]. MIRROR use-seeder.ts exactly.

Task 15 — CREATE frontend/src/components/admin/ai-models-panel.tsx:
  - <AIModelsPanel/> with 4 cards (Agent LLM, RAG Embeddings, API Keys, Provider
    Health). Use existing shadcn ui: Card, Select, Input, Button, Badge, Slider
    via Input type=range (matches SeederPanel), toast on save. Provider select
    includes ollama; when provider==ollama, model field is a Select fed by
    useOllamaModels(). API key inputs are type="password"; show ApiKeyStatus badge.
  - Follow webapp-testing / ui-design rule: verify in a real browser before
    declaring done (see Validation Level 4).

Task 16 — MODIFY frontend/src/pages/admin.tsx:
  - Add a 4th <TabsTrigger value="models"> (icon: Bot or Cpu from lucide-react)
    and <TabsContent value="models"><AIModelsPanel/></TabsContent>.

Task 17 — MODIFY docs:
  - docs/_base/API_CONTRACTS.md: add the 4 /config/* endpoints.
  - README.md: one line on the AI Models admin tab + Ollama-as-agent option.
  - docs/rag-ollama-setup.md: note Ollama can now also back the chat agent.
```

### Per-task pseudocode (critical details only)

```python
# Task 8 — base.py
from pydantic_ai.models import Model
from pydantic_ai.models.openai import OpenAIChatModel
from pydantic_ai.providers.ollama import OllamaProvider

def build_agent_model(identifier: str) -> str | Model:
    # PATTERN: cloud providers keep the plain-string path (unchanged behavior)
    provider = identifier.split(":", 1)[0]
    if provider != "ollama":
        return identifier
    settings = get_settings()
    _, model_name = identifier.split(":", 1)
    # CRITICAL: Ollama OpenAI-compat base ends in /v1
    base = settings.ollama_base_url.rstrip("/") + "/v1"
    return OpenAIChatModel(model_name, provider=OllamaProvider(base_url=base))

# Task 9 — service.update_config (the load-bearing path)
async def update_config(db: AsyncSession, payload: AIModelConfigUpdate) -> AIModelConfig:
    settings = get_settings()
    changes = payload.model_dump(exclude_none=True, exclude={"force"})

    # 1. validate model identifiers (reuses config.validate_model_identifier — ollama OK)
    for k in ("agent_default_model", "agent_fallback_model"):
        if k in changes:
            validate_model_identifier(changes[k])   # raises ValueError → 422 via handler

    # 2. dimension-change guard (GOTCHA above)
    if "rag_embedding_dimension" in changes and not payload.force:
        if changes["rag_embedding_dimension"] != settings.rag_embedding_dimension:
            chunk_count = await _count_rag_chunks(db)
            if chunk_count > 0:
                raise HTTPException(409, detail=(
                    f"Changing embedding dimension with {chunk_count} indexed "
                    "chunks breaks retrieval. Delete RAG sources first or pass force=true."))

    # 3. persist (ON CONFLICT DO UPDATE — SQLAlchemy pg insert, parameter-bound)
    for key, val in changes.items():
        await _upsert_app_config(db, key, val)
    await db.commit()

    # 4. apply to the live Settings singleton (+ os.environ for secrets)
    for key, val in changes.items():
        setattr(settings, key, val)
        if key in SECRET_KEYS:
            os.environ[_ENV_NAME[key]] = val      # unconditional overwrite

    # 5. CRITICAL: invalidate caches so the change is visible immediately
    reset_agent_caches()          # nulls _experiment_agent + _rag_assistant_agent
    reset_embedding_service()     # nulls _embedding_provider

    logger.info("config.updated", keys=sorted(changes), secrets=sorted(
        k for k in changes if k in SECRET_KEYS))   # NAMES only, never values
    return await get_effective_config(db)
```

```typescript
// Task 14 — use-config.ts  (mirror use-seeder.ts)
export function useAIConfig() {
  return useQuery({ queryKey: ['config', 'ai'], queryFn: () => api<AIModelConfig>('/config/ai') })
}
export function useUpdateAIConfig() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (body: AIModelConfigUpdate) =>
      api<AIModelConfig>('/config/ai', { method: 'PATCH', body }),
    onSuccess: () => void qc.invalidateQueries({ queryKey: ['config'] }),
  })
}
```

### Integration Points

```yaml
DATABASE:
  - migration: "create table app_config(key PK, value JSONB, updated_at)"

CONFIG (app/core/config.py):
  - extract validate_model_identifier() module-level fn; add "ollama" to providers.

ROUTES (app/main.py):
  - from app.features.config.routes import router as config_router
  - app.include_router(config_router)

STARTUP (app/main.py lifespan):
  - try: async with async_session() as db: await apply_overrides_on_startup(db)
    except Exception: logger.warning("config.overrides_skipped", ...)

CACHE RESETS:
  - rag/embeddings.py:reset_embedding_service()
  - agents/agents/experiment.py:reset_experiment_agent()
  - agents/agents/rag_assistant.py:reset_rag_assistant_agent()

FRONTEND:
  - admin.tsx: +1 Tab → AIModelsPanel
  - no ROUTES/NAV_ITEMS change (/admin already exists)
```

## Validation Loop

### Level 1: Syntax & Style

```bash
uv run ruff check . --fix
uv run ruff format .
uv run mypy app/
uv run pyright app/
# Expected: zero errors. Both type checkers gate merge.
```

### Level 2: Unit Tests

```bash
uv run pytest -v -m "not integration" \
  app/features/config/tests/ \
  app/core/tests/test_strict_mode_policy.py \
  app/features/agents/tests/
```

Required cases (mirror seeder/rag test style):
- `test_validate_model_identifier_accepts_ollama` — `"ollama:llama3.1"` passes.
- `test_validate_model_identifier_rejects_blank_ollama` — `"ollama:"` raises.
- `test_build_agent_model_ollama_returns_model_object` — type is OpenAIChatModel.
- `test_build_agent_model_cloud_returns_string` — `"anthropic:…"` unchanged.
- `test_get_effective_config_masks_secrets` — no raw key in the response.
- `test_update_config_resets_caches` — globals nulled after update.
- `test_update_config_dimension_guard` — 409 when chunks exist and dimension changes.
- `test_list_ollama_models_parses_tags` — httpx `/api/tags` response mocked.

### Level 3: Integration + Migration

```bash
docker compose up -d
uv run alembic upgrade head           # app_config table created cleanly
uv run pytest -v -m integration app/features/config/tests/

# Manual API smoke:
uv run uvicorn app.main:app --port 8123 &
curl -s localhost:8123/config/ai | python -m json.tool          # masked keys
curl -s localhost:8123/config/providers/health | python -m json.tool
curl -s -X PATCH localhost:8123/config/ai \
  -H 'Content-Type: application/json' \
  -d '{"agent_temperature": 0.3}'                                # 200, value applied
# Ollama path (requires `ollama serve` + a pulled model):
curl -s localhost:8123/config/ollama/models | python -m json.tool
```

### Level 4: Frontend + Browser Dogfood (ui-design rule — mandatory)

```bash
cd frontend && pnpm tsc --noEmit && pnpm lint && pnpm test --run
```

Then exercise the running UI via the **webapp-testing** / **agent-browser** skill:
navigate to `http://localhost:5173/admin`, open the **AI Models** tab, change the
agent temperature, Save, confirm the toast + that `GET /config/ai` reflects it.
Type-check passing ≠ UI works.

## Final Validation Checklist

- [ ] `uv run ruff check . && uv run ruff format --check .` clean
- [ ] `uv run mypy app/ && uv run pyright app/` clean
- [ ] `uv run pytest -v -m "not integration"` green
- [ ] `docker compose up -d && uv run alembic upgrade head` applies `app_config`
- [ ] `uv run pytest -v -m integration` green
- [ ] `cd frontend && pnpm tsc --noEmit && pnpm lint && pnpm test --run` green
- [ ] `GET /config/ai` returns masked keys (no raw secret anywhere)
- [ ] `PATCH /config/ai` persists + applies live; survives a uvicorn restart
- [ ] Agent set to `ollama:<model>` answers in `/chat` with no restart
- [ ] AI Models tab verified in a real browser (webapp-testing / agent-browser)
- [ ] `docs/_base/API_CONTRACTS.md` + `README.md` + `.env.example` updated
- [ ] Commits: `feat(api,ui): … (#<issue>)`; branch `feat/config-ai-model-admin-console`

## Anti-Patterns to Avoid

- ❌ Don't write a parallel config system — extend `Settings` + the `app_config` table.
- ❌ Don't return or log raw API keys — masked/presence only.
- ❌ Don't forget the cache resets — a saved change that doesn't take effect is the
  #1 failure mode of this feature.
- ❌ Don't pass an `ollama:` string to `Agent(model=...)` — build a model object.
- ❌ Don't let a missing `app_config` table crash startup — warn and continue.
- ❌ Don't change `rag_embedding_dimension` silently when chunks exist.
- ❌ Don't hand-roll the UI — use shadcn components + the ui-design skills, and
  dogfood in a browser.
- ❌ Don't weaken `test_strict_mode_policy.py` — keep config request fields JSON-native.

---

## Confidence Score: 8/10

High context density: every file, snippet, and gotcha for a one-pass build is
here, and the slice-to-mirror (`seeder`) is an exact structural match. The two
points of residual risk: (1) the precise PydanticAI 1.96 import/constructor for
`OpenAIChatModel` + `OllamaProvider` (mitigated — both imports were verified
available; context7 fallback noted), and (2) the live-mutation of the cached
`Settings` singleton + cache-reset wiring, which is novel for this codebase
(mitigated with explicit reset functions and a dedicated unit test). Deduct two
points for those; everything else is a well-trodden path.
