name: "PRP — Reliability E1: reject doubled provider prefixes in agent model ids"
description: |
  Foundation epic of umbrella #380 (platform reliability hardening).
  Issue: #334 · Branch: `fix/config-reject-doubled-provider-prefix` off `dev` · Commit scope: `api`
  (allow-list has no `config` scope; `app/core/*` + cross-feature config wiring = `api`,
  precedent: `test(api)` 24ed5cd, `feat(api,ui)` db530d5 — both touched `app/features/config/`).

---

## Goal

Harden `validate_model_identifier` (`app/core/config.py:20`) so an agent model identifier whose
model-name part *starts with another known provider prefix* — e.g.
`google-gla:google-gla:gemini-3-flash-preview` — is **rejected at config time** (Pydantic
`ValueError` → RFC 7807 422 at the HTTP boundary, `ValidationError` at `Settings` boot), while
legitimate multi-colon Ollama tag identifiers (`ollama:llama3.1:8b`, `ollama:gemma4:e2b`) keep
validating. Additionally, `apply_overrides_on_startup` must *skip-and-warn* (never crash, never
apply) a malformed model-id override already persisted in the `app_config` table.

**Deliverable:** one modified validator, one guarded startup loader, and regression tests at all
three layers the issue demands (schema-level, route-level 422, Settings-level) plus a
service-level startup-skip test.

**Success definition:** every test in the Final Validation Checklist passes; the exact failure
from the issue (`PATCH /config/ai` returning 200 for a doubled-prefix id, then a Gemini 404 at
agent-run time) is impossible to reproduce.

## Why

- **Root cause removal.** A doubled prefix persisted via `PATCH /config/ai` produced
  `404 NOT_FOUND — models/google-gla:gemini-3-flash-preview is not found` from Google *at
  agent-run time* — the failure surfaced far from its cause and required hand-correcting the id
  (issue #334).
- **Foundation for E2 (#335).** The fallback-failure-surfacing epic builds an error-classification
  matrix; this fix removes one whole failure class first so E2 tests against a stable surface
  (umbrella #380, Foundation ordering).
- **Upstream will never catch it.** Verified against installed pydantic-ai 1.96.0:
  `parse_model_id` does `model.split(':', maxsplit=1)` and passes everything after the first
  colon **verbatim** as the model name to the provider class. The validation burden is entirely
  on this repo's config layer.

## What

### Behavior change

| Input | Today | After |
|-------|-------|-------|
| `google-gla:google-gla:gemini-3-flash-preview` | PASS (bug) | **REJECT** — ValueError naming the nested prefix + suggesting `google-gla:gemini-3-flash-preview` |
| `anthropic:anthropic:claude-sonnet-4-5` | PASS (bug) | **REJECT** |
| `ollama:ollama:llama3.1` | PASS (bug) | **REJECT** |
| `openai:anthropic:claude-x` (mixed prefix) | PASS (bug) | **REJECT** (same malformation class; "Apply to all supported providers" per issue) |
| `ollama:llama3.1:8b` (Ollama `name:tag`) | PASS | PASS (unchanged) |
| `ollama:gemma4:e2b` | PASS | PASS (unchanged) |
| `ollama:openai` (model literally named like a provider, **no** colon after it) | PASS | PASS — narrow rule fires only on `provider:`-shaped *prefixes* inside the model name |
| `anthropic:claude-sonnet-4-5`, `openai:gpt-4o` | PASS | PASS (unchanged) |

**Rejection rule (exact):** after `provider, model_name = v.split(":", 1)` and the existing
checks, reject iff `":" in model_name and model_name.split(":", 1)[0] in VALID_MODEL_PROVIDERS`.

**Design decision — REJECT, not normalize.** The issue allows either. Rejection is chosen
because the real-world bug vector is the Settings UI: `ai-models-panel.tsx` *concatenates*
`${agentProvider}:${agentModel}` on save (`frontend/src/components/admin/ai-models-panel.tsx:99-111`),
so a user pasting a full `provider:model` id into the model field produces the doubled prefix.
Silent normalization would mask that input-bug class forever; a 422 with a "did you mean
`<corrected>`" message surfaces it immediately. (Frontend input sanitization = out of scope,
see below.)

### Startup guard

`apply_overrides_on_startup` (`app/features/config/service.py:166-202`) currently `setattr`s
persisted overrides with **no re-validation**. A doubled-prefix row persisted before this fix
would still go live in memory on every boot. Add a guard for exactly the two model-id keys:
validate, and on `ValueError` skip the key + `logger.warning("config.override_invalid_model_id", …)`
— the env/default value stays in effect. Never raise (the function's "never let config crash
startup" contract at `service.py:176-182` stands).

### Success Criteria

- [ ] `validate_model_identifier` rejects `<p1>:<p2>:rest` for every `p2 ∈ VALID_MODEL_PROVIDERS`, with an error message that names the offending id, identifies the nested prefix, and suggests the corrected id
- [ ] `ollama:llama3.1:8b`, `ollama:gemma4:e2b`, `ollama:openai` still validate
- [ ] `PATCH /config/ai` with `{"agent_default_model": "google-gla:google-gla:x"}` → **422** `application/problem+json` with `code="VALIDATION_ERROR"` and `errors[0].field == "agent_default_model"`; happy-path PATCH still 200
- [ ] `Settings(agent_default_model="anthropic:anthropic:x", _env_file=None)` raises `ValidationError`
- [ ] `apply_overrides_on_startup` with a malformed persisted `agent_default_model` boots clean, leaves the `Settings` value untouched, and logs `config.override_invalid_model_id`
- [ ] All five validation gates green; no existing test modified to weaken (only extended)

## All Needed Context

### Documentation & References

```yaml
# ── The defect and its single fix point ──────────────────────────────────────
- file: app/core/config.py
  lines: 11-17, 20-59, 214-218
  why: |
    VALID_MODEL_PROVIDERS tuple (the allow-list the new rule reuses), the
    validate_model_identifier function to modify (split(":", 1) at line 44; the new check
    slots after the provider check at line 55-58), and the Settings field_validator that
    gives the fix Settings-boot coverage for free. Mirror the existing ValueError message
    style: full offending id + expected format + concrete examples.

# ── Second call site (free coverage, do not duplicate logic) ─────────────────
- file: app/features/config/schemas.py
  lines: 93-125
  why: |
    AIModelConfigUpdate._check_model_identifier delegates to the same function — DO NOT
    add slice-local logic; the fix in app/core/config.py covers PATCH /config/ai
    automatically. Note ConfigDict(strict=True) at line 99: both model fields are
    `str | None` (JSON-native), so NO Field(strict=False) override is needed and
    app/core/tests/test_strict_mode_policy.py stays green.

# ── Startup loader to guard ──────────────────────────────────────────────────
- file: app/features/config/service.py
  lines: 166-202
  why: |
    apply_overrides_on_startup: the setattr loop to guard (only for keys
    agent_default_model / agent_fallback_model). Mirror the existing structlog pattern:
    logger.warning("config.overrides_load_failed", error=str(exc), error_type=...) at
    176-182 and logger.info("config.overrides_applied", keys=...) at 201. Also read
    204-266 (update_config): the service does NOT re-validate — the schema boundary owns
    validation; keep it that way.

# ── Error shape a route test must assert ─────────────────────────────────────
- file: app/core/exceptions.py
  lines: 293-336
  why: |
    RequestValidationError → RFC 7807 handler. Pydantic ValueError inside a field
    validator surfaces as 422 problem+json:
    {type:"/errors/validation", title:"Validation Error", status:422,
     code:"VALIDATION_ERROR", errors:[{field:"agent_default_model",
     message:"Value error, …", type:"value_error"}], request_id:"…"}

# ── Test patterns to mirror (extend, never weaken) ───────────────────────────
- file: app/features/config/tests/test_schemas.py
  lines: 16-95
  why: |
    TestValidateModelIdentifier (direct validator tests via pytest.raises(ValueError,
    match=...)) — add the new cases here. TestAIModelConfigUpdate + the
    test_model_validate_json_path pattern (strict-mode policy: at least one case through
    Model.model_validate({...}) — FastAPI's validate_python path).
- file: app/features/config/tests/test_routes.py
  lines: 90-129
  why: |
    TestUpdateAIConfig.test_patch_rejects_invalid_model — the PATCH→422 pattern + the
    conftest client fixture. Add doubled-prefix 422 case asserting the problem-details
    fields, and keep one 200 happy path.
- file: app/features/agents/tests/test_config_validation.py
  lines: 10-48
  why: |
    TestModelIdentifierValidation — Settings-level coverage pattern:
    Settings(agent_default_model=..., _env_file=None) + pytest.raises(ValidationError,
    match=...). The _env_file=None kwarg is MANDATORY (see gotcha below).
- file: app/features/config/tests/test_service.py
  lines: 139-194
  why: |
    Async service-test pattern (_mock_db style) for the new startup-skip test. ALSO:
    settings-singleton teardown precedent (commit 24ed5cd "test(api): scope teardown
    deletes and restore mutated settings singleton") — any test that mutates the cached
    Settings must restore it.

# ── Consumers that must keep working unchanged (read-only context) ───────────
- file: app/features/agents/agents/base.py
  lines: 132-165, 329
  why: |
    build_agent_model splits provider/model with split(":", 1) — for ollama it passes
    "qwen3:8b"-style names to OpenAIChatModel. The fix changes NOTHING here; these are
    the call sites the validator protects. Fixtures "ollama:qwen3:8b" at
    app/features/agents/tests/test_base.py:458, test_service.py:539/647, and
    app/features/demo/tests/test_pipeline.py:1815 MUST still pass.
- file: frontend/src/components/admin/ai-models-panel.tsx
  lines: 43-58, 99-111
  why: |
    Read-only context — the bug vector. deriveForm splits provider off the stored id;
    saveAgent reconstructs `${provider}:${model}`. No frontend change in this PRP; the
    422 message is what the operator sees.

# ── External references (verified 2026-06-11) ────────────────────────────────
- url: https://pydantic.dev/docs/ai/models/overview/
  section: "Models and Providers"
  why: documents the `<provider>:<model>` identifier contract PydanticAI consumes
- url: https://docs.pydantic.dev/latest/concepts/validators/#field-validators
  why: field_validator semantics — the existing validators run mode="after" on typed str values
- url: https://github.com/ollama/ollama/blob/main/docs/api.md
  section: "Model names"
  why: |
    "Model names follow a model:tag format … tag optional, defaults to latest" — the
    documented reason `ollama:<name>:<tag>` is a LEGITIMATE 2-colon identifier and a
    blanket "no second colon" rule is WRONG.
```

### Current Codebase tree (relevant subset)

```
app/core/config.py                        # validate_model_identifier + Settings  ← MODIFY
app/core/exceptions.py                    # 422 problem-details handler           (read)
app/core/tests/test_config.py             # Settings defaults tests               (read)
app/features/config/
  schemas.py                              # AIModelConfigUpdate (delegates)       (no change)
  service.py                              # apply_overrides_on_startup            ← MODIFY
  routes.py                               # PATCH /config/ai                      (no change)
  tests/
    test_schemas.py                       # TestValidateModelIdentifier           ← EXTEND
    test_routes.py                        # TestUpdateAIConfig                    ← EXTEND
    test_service.py                       # service/startup tests                 ← EXTEND
app/features/agents/tests/
  test_config_validation.py               # Settings-level validator tests        ← EXTEND
```

### Desired Codebase tree

No new files. Four test files extended, two source files modified. No migration (the
`app_config` table schema is untouched; malformed *rows* are handled by skip-and-warn, not
backfill).

### Known Gotchas & Library Quirks

```python
# ── VERIFIED LIBRARY CLAIM #1: pydantic-ai passes the post-colon remainder verbatim ──
# pydantic-ai 1.96.0: parse_model_id does  model.split(':', maxsplit=1)  — provider is
# everything before the FIRST colon; the rest is the model name, sent to the provider
# unchecked. There is NO upstream guard for doubled prefixes (checked pydantic-ai issues;
# none open). Re-verify on pydantic-ai upgrade with:
#   uv run python -c "
#   import inspect, pydantic_ai, pydantic_ai.models as m
#   print(pydantic_ai.__version__)
#   print([l.strip() for l in inspect.getsource(m.parse_model_id).splitlines() if 'split' in l])"
#   # → ["provider_name, model_name = model.split(':', maxsplit=1)"]

# ── VERIFIED BUG REPRO (pre-fix baseline, run 2026-06-11) ────────────────────────────
#   uv run python -c "
#   from app.core.config import validate_model_identifier as v
#   v('google-gla:google-gla:gemini-3-flash-preview')  # currently returns — the bug
#   v('ollama:llama3.1:8b')                            # returns — MUST STAY VALID"
# After the fix the first call must raise ValueError; the second must not.

# ── GOTCHA: Ollama tags make "reject any 2nd colon" WRONG ────────────────────────────
# ollama model ids are name:tag (docs/api.md "Model names"), so ollama:llama3.1:8b and
# ollama:gemma4:e2b are real, working ids used in tests/fixtures TODAY
# (agents/tests/test_base.py:458, agents/tests/test_service.py:539,647,
#  demo/tests/test_pipeline.py:1815). The rule must check whether the FIRST SEGMENT of
# model_name is a KNOWN PROVIDER followed by ':' — nothing broader.

# ── GOTCHA: .env bleed into Settings tests ───────────────────────────────────────────
# Settings() reads .env via SettingsConfigDict(env_file=".env"). Every Settings-level
# test MUST pass _env_file=None (RUNBOOKS "Settings tests fail because they pick up the
# local .env"; existing pattern in agents/tests/test_config_validation.py).

# ── GOTCHA: get_settings() is lru_cached; tests that mutate it must restore it ───────
# Precedent commit 24ed5cd. The startup-skip test mutates/reads the singleton — use the
# existing teardown/fixture pattern in app/features/config/tests/ (conftest.py) so later
# tests see pristine settings.

# ── GOTCHA: strict-mode policy on request bodies ─────────────────────────────────────
# AIModelConfigUpdate keeps ConfigDict(strict=True). Both model-id fields are str|None →
# JSON-native, no Field(strict=False) needed. Include ≥1 new case through
# AIModelConfigUpdate.model_validate({...}) (the validate_python path) per
# .claude/rules/security-patterns.md § strict mode.

# ── GOTCHA: error-message style is load-bearing for UX ───────────────────────────────
# Existing messages embed the full offending id + expected format + examples
# (config.py:38-58). The new message must also tell the operator the LIKELY FIX:
#   "Nested provider prefix 'google-gla:' inside the model name of
#    'google-gla:google-gla:gemini-3-flash-preview'. Did you mean
#    'google-gla:gemini-3-flash-preview'?"
# The suggestion = v with the first duplicated segment dropped (provider + rest after the
# nested prefix). Keep it deterministic — tests match on substrings of this message.

# ── GOTCHA: repo has mixed CRLF/LF line endings ──────────────────────────────────────
# Check `git diff --stat` after editing: if a file shows ~all lines changed, your editor
# rewrote line endings — re-edit preserving the file's existing endings.

# ── GOTCHA: never raise from apply_overrides_on_startup ─────────────────────────────
# Its contract is "config must never crash startup" (service.py docstring + main.py
# lifespan try/except). The guard SKIPS the bad key and warns — it must not raise.
```

## Implementation Blueprint

### Data models and structure

No new models. One pure-function change + one loader guard:

```python
# app/core/config.py — inside validate_model_identifier, AFTER the existing
# unknown-provider check (line 55-58), add:

    # Reject a nested/doubled provider prefix inside the model name
    # (issue #334: 'google-gla:google-gla:gemini-…' → Gemini 404 at run time).
    # Ollama tags ('ollama:llama3.1:8b') stay valid: 'llama3.1' is not a provider.
    if ":" in model_name:
        nested = model_name.split(":", 1)[0]
        if nested in VALID_MODEL_PROVIDERS:
            suggested = f"{provider}:{model_name.split(':', 1)[1]}"
            raise ValueError(
                f"Nested provider prefix '{nested}:' inside the model name of '{v}'. "
                f"Did you mean '{suggested}'? "
                "Expected format: 'provider:model-name' with the provider given once."
            )
```

```python
# app/features/config/service.py — apply_overrides_on_startup, inside the
# `for key, value in overrides.items():` loop, before setattr:

_MODEL_ID_KEYS = frozenset({"agent_default_model", "agent_fallback_model"})  # module level

        if key in _MODEL_ID_KEYS and isinstance(value, str):
            try:
                validate_model_identifier(value)
            except ValueError as exc:
                logger.warning(
                    "config.override_invalid_model_id",
                    key=key,
                    error=str(exc),
                )
                continue  # leave env/default in effect; do NOT crash startup
```

(`validate_model_identifier` is already imported in the slice via `schemas.py`; `service.py`
needs its own import from `app.core.config`.)

### Tasks (in order)

```yaml
Task 1:
MODIFY app/core/config.py:
  - FIND: validate_model_identifier, the `if provider not in VALID_MODEL_PROVIDERS:` block
  - INJECT the nested-prefix check AFTER it (so 'pinecone:pinecone:x' still reports
    "Unknown provider" first — provider validity outranks shape)
  - UPDATE the docstring: add the new ValueError condition + an ollama-tag example
    ("ollama:llama3.1:8b stays valid") so the docstring documents the carve-out

Task 2:
MODIFY app/features/config/service.py:
  - ADD import: from app.core.config import validate_model_identifier
  - ADD module-level _MODEL_ID_KEYS frozenset next to ALLOWED_OVERRIDE_KEYS usage
  - INJECT the skip-and-warn guard in apply_overrides_on_startup per pseudocode
  - PRESERVE: the function must never raise; logger event name
    "config.override_invalid_model_id" (structlog kwargs style, key NAMES only — never
    log secret values, per security-patterns.md)

Task 3:
EXTEND app/features/config/tests/test_schemas.py (class TestValidateModelIdentifier):
  - test_rejects_doubled_provider_prefix:  parametrize over
      "google-gla:google-gla:gemini-3-flash-preview",
      "anthropic:anthropic:claude-sonnet-4-5",
      "openai:openai:gpt-4o",
      "google-vertex:google-vertex:gemini-2.0",
      "ollama:ollama:llama3.1"
    → pytest.raises(ValueError, match="Nested provider prefix")
  - test_rejects_mixed_provider_prefix: "openai:anthropic:claude-x" → same match
  - test_error_message_suggests_correction: match the literal suggested id
    "google-gla:gemini-3-flash-preview" in the message
  - test_accepts_ollama_tag_identifiers: parametrize "ollama:llama3.1:8b",
    "ollama:gemma4:e2b", "ollama:qwen3:8b" → returns input unchanged
  - test_accepts_model_named_like_provider: "ollama:openai" → returns unchanged
  EXTEND class TestAIModelConfigUpdate:
  - test_rejects_doubled_prefix_via_model_validate: AIModelConfigUpdate.model_validate(
      {"agent_default_model": "google-gla:google-gla:x"}) → pydantic.ValidationError
    (this is the strict-mode JSON-path case)
  - test_fallback_model_also_guarded: same via agent_fallback_model

Task 4:
EXTEND app/features/agents/tests/test_config_validation.py (TestModelIdentifierValidation):
  - test_doubled_prefix_rejected_at_settings_boot:
      Settings(agent_default_model="anthropic:anthropic:claude-sonnet-4-5",
               _env_file=None) → pytest.raises(ValidationError, match="Nested provider")
  - test_ollama_tag_accepted_at_settings_boot:
      Settings(agent_default_model="ollama:llama3.1:8b", _env_file=None) constructs

Task 5:
EXTEND app/features/config/tests/test_routes.py (TestUpdateAIConfig):
  - test_patch_rejects_doubled_provider_prefix: PATCH /config/ai
      {"agent_default_model": "google-gla:google-gla:gemini-3-flash-preview"} →
      assert 422; body["code"] == "VALIDATION_ERROR";
      body["errors"][0]["field"] == "agent_default_model";
      "Nested provider prefix" in body["errors"][0]["message"]
    (mirror the existing test_patch_rejects_invalid_model fixture usage exactly)
  - keep/confirm one 200 happy-path PATCH with a valid id in the same class

Task 6:
EXTEND app/features/config/tests/test_service.py:
  - test_startup_skips_invalid_model_id_override:
      mock _load_overrides → {"agent_default_model": "google-gla:google-gla:x",
                              "agent_temperature": 0.5}
      run apply_overrides_on_startup; assert settings.agent_default_model UNCHANGED,
      settings.agent_temperature == 0.5 (valid keys still applied),
      and the warning event fired (capture structlog or patch logger).
      RESTORE the settings singleton in teardown (follow conftest/24ed5cd pattern).

Task 7 (docs, same commit or follow-up in the PR):
  - docs/_base/RUNBOOKS.md gets NO new incident entry (the failure class is now impossible
    at the boundary), but IF the PR reviewer wants operator visibility, add one line to
    the existing agent-incident notes pointing at the 422 message. OPTIONAL — skip by
    default to keep the diff minimal.
```

### Integration Points

```yaml
DATABASE: none — no migration; malformed persisted rows handled by skip-and-warn
ROUTES:   none — PATCH /config/ai unchanged; validation fires in the existing schema boundary
CONFIG:   app/core/config.py validator change propagates to BOTH call sites automatically
FRONTEND: none in this PRP — the 422 problem-details message is the operator surface
```

## Validation Loop

### Level 1: Syntax & Style

```bash
uv run ruff check app/core/config.py app/features/config/ app/features/agents/tests/test_config_validation.py
uv run ruff format --check .
uv run mypy app/ && uv run pyright app/        # both --strict; zero new errors
```

### Level 2: Unit tests (no DB)

```bash
uv run pytest -v \
  app/features/config/tests/test_schemas.py \
  app/features/config/tests/test_routes.py \
  app/features/config/tests/test_service.py \
  app/features/agents/tests/test_config_validation.py
# Then the full unit gate — proves no consumer fixture broke (ollama:qwen3:8b et al.):
uv run pytest -v -m "not integration"
```

### Level 3: Integration (live API)

```bash
docker compose up -d && uv run uvicorn app.main:app --port 8123 &   # or existing stack
# Doubled prefix → 422 problem+json naming the field:
curl -si -X PATCH http://localhost:8123/config/ai \
  -H 'Content-Type: application/json' \
  -d '{"agent_default_model":"google-gla:google-gla:gemini-3-flash-preview"}' \
  | head -20      # expect: HTTP/1.1 422, application/problem+json, "Nested provider prefix"
# Happy path still works:
curl -si -X PATCH http://localhost:8123/config/ai \
  -H 'Content-Type: application/json' \
  -d '{"agent_default_model":"anthropic:claude-sonnet-4-5"}' | head -5   # expect 200
# Ollama tag still accepted:
curl -si -X PATCH http://localhost:8123/config/ai \
  -H 'Content-Type: application/json' \
  -d '{"agent_default_model":"ollama:llama3.1:8b"}' | head -5            # expect 200
```

### Level 4 (optional dogfood): Settings UI

Open `/settings` (AI Models panel), paste a full `google-gla:gemini-…` id into the model field
with provider already selected, save → the UI should surface the 422 with the "Did you mean"
message instead of silently persisting a broken id.

## Final Validation Checklist

- [ ] `uv run ruff check . && uv run ruff format --check .` clean
- [ ] `uv run mypy app/ && uv run pyright app/` clean (strict)
- [ ] `uv run pytest -v -m "not integration"` green — including the pre-existing
      `ollama:qwen3:8b` fixtures in agents/demo tests (untouched)
- [ ] New tests cover: 5 doubled-prefix rejections, mixed-prefix rejection, message
      suggestion, 3 ollama-tag acceptances, `ollama:openai` edge, JSON-path schema case,
      Settings boot rejection + acceptance, route 422 + 200, startup skip-and-warn
- [ ] Level-3 curl matrix matches expected statuses
- [ ] `git diff --stat` shows surgical diffs (no whole-file line-ending churn)
- [ ] Commits: `fix(api): reject doubled provider prefixes in agent model ids (#334)`
      (+ `test(api): …` if tests are split out); no AI trailers
- [ ] PR into `dev` from `fix/config-reject-doubled-provider-prefix`; CI green

---

## Out of Scope (this PRP)

- **Frontend input sanitization** in `ai-models-panel.tsx` (stripping a pasted provider
  prefix client-side) — the 422 message now surfaces the mistake; promote to its own issue
  if dogfood shows operators hitting it often.
- **#335 fallback-failure surfacing** — E2 of umbrella #380, builds on this foundation.
- **Normalization mode** (silently collapsing the prefix) — rejected by design decision above.
- **Backfill/migration of existing malformed `app_config` rows** — skip-and-warn at startup +
  a corrective PATCH is sufficient for a single-host system.

## Anti-Patterns to Avoid

- ❌ Don't reject every id containing a second colon — Ollama tags are legitimate.
- ❌ Don't duplicate the check in `app/features/config/schemas.py` — one source of truth.
- ❌ Don't let `apply_overrides_on_startup` raise — its no-crash contract is load-bearing.
- ❌ Don't log override *values* alongside secrets handling paths — key names + error text only.
- ❌ Don't forget `_env_file=None` in Settings tests — .env bleed is a known incident class.
- ❌ Don't weaken or rewrite existing validator tests — extend the existing classes.

---

**One-pass confidence score: 9/10** — single pure-function change with two pre-wired call
sites, all consumers verified tolerant (`split(":", 1)` everywhere), bug + carve-out both
runtime-verified, test patterns mirrored from named existing classes. The startup-guard test
is the only piece with moderate friction (settings-singleton restore discipline).
