name: "PRP — Reliability E2: surface fallback model failures with classified, actionable details"
description: |
  Parallel epic of umbrella #380 (platform reliability hardening), after Foundation E1 (#334).
  Issue: #335 · Branch: `fix/agents-surface-fallback-failures` off `dev` · Commit scope: `agents,api`
  (primary surface is `app/features/agents/`; the additive RFC 7807 extension plumbing touches
  `app/core/{exceptions,problem_details}.py` = `api`, mirroring E1's scope reasoning).

---

## Goal

When every model in the PydanticAI `FallbackModel` chain fails (or a single configured model
fails with a provider error), the client must receive a **classified, secret-safe summary of
each per-model failure** — `{model_name, status_code, reason, detail}` — instead of today's
generic `Stream error: All models from FallbackModel failed (2 sub-exceptions)`:

- **WebSocket `/agents/stream`** — one `error` StreamEvent with `error_type="fallback_exhausted"`,
  a human-actionable `error` summary string, and a structured `failures` list.
- **REST `POST /agents/sessions/{id}/chat`** — a **502** `application/problem+json` with
  `code="AGENT_FALLBACK_EXHAUSTED"` and a `failures` extension member.

**Deliverable:** one new classifier module (`app/features/agents/failures.py`), one new schema
(`ModelFailureDetail`), two new `except` arms in `AgentService.chat` / `stream_chat`, one new
core exception (`AgentFallbackExhaustedError`) riding a new additive `extensions` pass-through
in the RFC 7807 helpers, plus tests at classifier / service / route levels.

**Success definition:** the exact failure from the issue (primary `404` model-not-found +
fallback `429` quota-exhausted) renders in the chat UI as a readable two-leg diagnosis with
zero frontend changes, and a route test proves the REST 502 carries both classified legs.
No secret-like material (API keys, bearer tokens) can appear in any surfaced payload.

## Why

- **Diagnosability from the UI.** The 2026-06-01 incident (issue #335) required reading
  container logs to learn that the primary leg was a 404 (bad model name) and the fallback leg
  a 429 (free-tier quota). Both causes were sitting in `agents.websocket_stream_error`; the
  client got an opaque one-liner.
- **E1 (#334) stabilized the surface.** The doubled-prefix 404 class is now rejected at config
  time (PR #382), so the classification matrix built here tests against a stable failure
  surface (umbrella #380 Foundation ordering).
- **Zero-frontend-change win.** `frontend/src/pages/chat.tsx:95-108` renders
  `Error: ${event.data.error}` verbatim — making the backend's `error` string itself the
  classified human summary upgrades the UI for free; the structured `failures` list is the
  additive machine-readable layer for future UI work.

## What

### Behavior change

| Surface | Today | After |
|---------|-------|-------|
| WS `error` event, both models fail | `error="Stream error: All models from FallbackModel failed (2 sub-exceptions)"`, `error_type="ExceptionGroup"`-ish class name (from `websocket.py` generic catch) | `error_type="fallback_exhausted"`, `error="All configured agent models failed — google-gla:gemini-3-flash-preview: model not found / invalid model name (HTTP 404); google-gla:gemini-2.5-flash: quota or rate limit exhausted (HTTP 429)"`, `failures=[{model_name, status_code, reason, detail}, …]`, `recoverable=true` |
| REST chat, both models fail | uncaught `FallbackExceptionGroup` → generic 500 `INTERNAL_ERROR` problem+json | **502** problem+json, `code="AGENT_FALLBACK_EXHAUSTED"`, `type="/errors/agent-fallback-exhausted"`, `detail=<same human summary>`, `failures=[…]` extension |
| Single-model config (no fallback wired), provider error | same generic surfaces | same classified treatment (a bare `ModelAPIError` is classified as a 1-element `failures` list) |
| Model misbehavior (`UnexpectedModelBehavior`) | salvage → friendly message / `error_type="model_behavior_error"` | **unchanged** — the new arm catches only provider-API failures |
| Secrets in provider response bodies | `str(ModelHTTPError)` embeds `body` verbatim (leak risk if echoed) | surfaced `detail` is extracted → scrubbed (`AIza…`, `sk-…`, `Bearer …`, `api_key=…`) → truncated to 300 chars |

### Reason classification (exact)

| Evidence | `reason` |
|----------|----------|
| `ModelHTTPError.status_code == 404` | `model_not_found` |
| `status_code == 429` | `quota_exhausted` |
| `status_code in (401, 403)` | `auth_error` |
| `status_code >= 500` | `provider_unavailable` |
| any other `ModelHTTPError` | `provider_error` |
| non-HTTP `ModelAPIError` (connection, etc.) | `provider_error` (status_code `null`) |
| `pydantic_ai.models.fallback.ResponseRejected` member | `response_rejected` |
| anything else inside the group | `unknown` |

### Success Criteria

- [ ] `classify_model_failures` maps 404/429/401/403/5xx/other-HTTP/non-HTTP/`ResponseRejected`/unknown and recurses into nested `ExceptionGroup`s
- [ ] Stream path: a `FallbackExceptionGroup(404 + 429)` raised by `agent.run_stream` yields exactly ONE `error` event with `error_type="fallback_exhausted"`, `recoverable=True`, a 2-entry `failures` list, and a summary naming both models — and the raw group string (`"sub-exceptions"`) does NOT appear
- [ ] REST path: the same failure → 502 `application/problem+json` with `code="AGENT_FALLBACK_EXHAUSTED"` and `failures` extension (route test covers both legs — umbrella #380 criterion)
- [ ] A planted secret (`AIzaFakeKey123…` / `sk-fake…` / `Bearer xyz`) in `ModelHTTPError.body` never appears in any serialized event/response payload (regression test asserts on the full JSON dump)
- [ ] Single bare `ModelAPIError` (no FallbackModel) gets the same classified treatment
- [ ] Existing `model_behavior_error` behavior and tests untouched (only extended)
- [ ] All five validation gates green; `docs/_base/API_CONTRACTS.md` updated additively

## All Needed Context

### Documentation & References

```yaml
# ── Where the failures escape today (the two catch points to add) ────────────
- file: app/features/agents/service.py
  lines: 24-26, 295-354, 520-570, 693-771
  why: |
    Imports (line 25 already pulls UnexpectedModelBehavior from pydantic_ai.exceptions —
    extend it). chat(): the try at 298-308 wraps agent.run; excepts at 309 (TimeoutError)
    and 313 (UnexpectedModelBehavior) — the NEW arm slots between them. stream_chat():
    try at 525 wraps run_stream (533, streaming) AND agent.run (560-568, #342 ollama
    non-streaming fallback) — one new arm covers both; excepts at 693/697; the
    misbehavior error-yield at 759-770 is the EXACT yield pattern to mirror
    (data dict with error/error_type/recoverable, datetime.now(UTC) timestamp,
    session.last_activity update + db.flush() before yielding, then `return`).

# ── The generic backstop that produced the bad UX (do NOT remove — keep as backstop)
- file: app/features/agents/websocket.py
  lines: 96-123, 132-158
  why: |
    The `except Exception` at 109-123 is what stringified the group today
    (f"Stream error: {e}", error_type=type(e).__name__) and logged
    "agents.websocket_stream_error". After this PRP the service yields the classified
    event BEFORE the exception reaches here; the handler stays as the backstop for
    everything else. NO changes in this file.

# ── Schema home for the new detail model + additive ErrorEvent field ─────────
- file: app/features/agents/schemas.py
  lines: 145-163, 229-248, 304-316
  why: |
    ChatResponse (no error field — REST errors go through problem+json, NOT this model),
    StreamEvent (data is dict[str, Any] — the failures list rides inside data),
    ErrorEvent (error/error_type/recoverable) — add Optional `failures` here so the
    documented event shape matches what the service emits. Define ModelFailureDetail
    in this file (schemas.py is the slice's schema home).

# ── FallbackModel construction (read-only — explains when a group vs bare error escapes)
- file: app/features/agents/agents/base.py
  lines: 168-176, 201-249
  why: |
    build_agent_model_with_fallback returns a bare primary model when no distinct
    key-backed fallback exists (→ bare ModelAPIError escapes, no group) and
    FallbackModel(primary, fallback) otherwise (→ FallbackExceptionGroup escapes when
    BOTH legs fail). reset_agent_caches (168) is why PATCH /config/ai applies live —
    used by the Level-3 plan.

# ── RFC 7807 plumbing: the precedent and the two additive core edits ─────────
- file: app/core/exceptions.py
  lines: 27-61, 227-254, 262-290
  why: |
    ForecastLabError base (gains optional `extensions` kwarg; note `details` is
    LOG-ONLY — the handler at 279-288 drops it from the response body, which is WHY
    the new extensions channel exists). EmbeddingProviderAuthError (227-254) is the
    EXACT precedent to mirror for AgentFallbackExhaustedError: module-level code
    constant, error_type_uri from ERROR_TYPES, fixed status 502, narrow __init__.
    forecastlab_exception_handler (262-290) passes title=exc.title (derived from code:
    "AGENT_FALLBACK_EXHAUSTED" → "Agent Fallback Exhausted") — add extensions pass-through.
- file: app/core/problem_details.py
  lines: 28-46, 54-114, 135-199
  why: |
    EMBEDDING_AUTH_CODE constant pattern (30) + ERROR_TYPES dict (32-46) — add
    AGENT_FALLBACK_EXHAUSTED. ProblemDetail has ConfigDict(extra="allow") (RFC 7807
    extension members are sanctioned). problem_response (169-199) serializes via
    model_dump(exclude_none=True) — merge extensions into the serialized dict there
    (NOT via ProblemDetail(**extensions); see gotcha on the mypy/pydantic-plugin trap).

# ── Test patterns to mirror (extend, never weaken) ───────────────────────────
- file: app/features/agents/tests/test_service.py
  lines: 426-480
  why: |
    test_stream_chat_model_misbehavior_yields_error_event — THE pattern for the new
    stream test: AgentService() + monkeypatch settings.agent_default_model to
    "anthropic:claude-test" (line 444 — pins the run_stream path, #342), mock_db AsyncMock with
    scalar_one_or_none → sample_active_session fixture, _RaisingStream async CM that
    raises on __aenter__, patch.object(service, "_get_agent"), collect events, assert
    on events[0].data. Note it asserts the LITERAL "model_behavior_error" (line 478) —
    error_type strings are load-bearing; pick "fallback_exhausted" once and keep it stable.
- file: app/features/agents/tests/test_routes.py
  lines: 1-60
  why: |
    Route tests are @pytest.mark.integration (real Postgres via conftest `client`
    fixture). Pattern: create a session via POST /agents/sessions with the agent
    factory patched, then exercise the endpoint. The new 502 test patches
    AgentService.chat (or _get_agent with an agent whose run raises the group) and
    asserts status/content-type/code/failures on the problem+json body.
- file: app/features/agents/tests/conftest.py
  why: sample_active_session fixture used by the service tests; client fixture for routes.

# ── Frontend consumer (READ-ONLY — proves no frontend change is needed) ──────
- file: frontend/src/pages/chat.tsx
  lines: 95-108
  why: |
    case 'error' renders `Error: ${event.data.error}` verbatim into the transcript.
    The human summary string IS the UI improvement. AgentStreamEvent.data is
    Record<string, unknown> (frontend/src/types/api.ts:601-605) so the additive
    failures key needs no type change.

# ── External references (verified against installed pydantic-ai 1.96.0, 2026-06-11)
- url: https://pydantic.dev/docs/ai/models/overview/
  section: "Fallback Model"
  why: FallbackModel semantics — falls back on ModelAPIError; raises FallbackExceptionGroup when all legs fail
- url: https://pydantic.dev/docs/ai/api/pydantic-ai/exceptions/
  why: ModelHTTPError / ModelAPIError / FallbackExceptionGroup API reference
- url: https://docs.python.org/3/library/exceptions.html#exception-groups
  why: |
    ExceptionGroup.exceptions is a TUPLE; sub-groups can nest — the classifier must
    recurse. A plain `except FallbackExceptionGroup:` works (it subclasses Exception);
    `except*` syntax is NOT needed and would complicate the single-yield contract.
```

### Current Codebase tree (relevant subset)

```
app/core/
  exceptions.py                     # ForecastLabError + handler                ← MODIFY (additive)
  problem_details.py                # ERROR_TYPES + problem_response            ← MODIFY (additive)
  tests/                            # (no problem_details test file today)      ← ADD test file
app/features/agents/
  agents/base.py                    # FallbackModel construction                (read-only)
  service.py                        # chat() / stream_chat() except arms        ← MODIFY
  websocket.py                      # generic backstop                          (no change)
  schemas.py                        # StreamEvent / ErrorEvent                  ← MODIFY (additive)
  routes.py                         # chat endpoint                             (no change — global handler covers 502)
  tests/
    test_service.py                 # stream/chat error tests                   ← EXTEND
    test_routes.py                  # integration route tests                   ← EXTEND
docs/_base/API_CONTRACTS.md         # WS ErrorEvent + chat endpoint docs        ← EXTEND
```

### Desired Codebase tree

```
app/features/agents/failures.py            # NEW — classify_model_failures / summarize_model_failures / _sanitize
app/features/agents/tests/test_failures.py # NEW — classification matrix + secret-scrub + summary tests
app/core/tests/test_problem_details.py     # NEW — extensions merge + reserved-key guard + no-extensions unchanged
```

No migration (nothing persisted changes). No frontend changes. No new dependencies.

### Known Gotchas & Library Quirks

```python
# ── VERIFIED LIBRARY CLAIM #1: the exception family (pydantic-ai 1.96.0) ──────────────
#   uv run python -c "
#   from pydantic_ai.exceptions import FallbackExceptionGroup, ModelHTTPError, ModelAPIError
#   print(FallbackExceptionGroup.__mro__)   # → ExceptionGroup → BaseExceptionGroup → Exception
#   print(ModelHTTPError.__mro__)           # → ModelAPIError → AgentRunError → RuntimeError
#   import inspect; print(inspect.signature(ModelHTTPError.__init__))"
#   # → (self, status_code: 'int', model_name: 'str', body: 'object | None' = None)
# ModelHTTPError IS a ModelAPIError → FallbackModel's default fallback_on=(ModelAPIError,)
# catches it per-leg; the group only escapes when ALL legs fail. Re-verify on upgrade.

# ── VERIFIED LIBRARY CLAIM #2: group anatomy ──────────────────────────────────────────
#   uv run python -c "
#   from pydantic_ai.exceptions import FallbackExceptionGroup, ModelHTTPError
#   g = FallbackExceptionGroup('All models from FallbackModel failed',
#                              [ModelHTTPError(404, 'm1'), ModelHTTPError(429, 'm2')])
#   print(type(g.exceptions), g.message)"
#   # → <class 'tuple'> All models from FallbackModel failed
# .exceptions is an immutable TUPLE (not list). The constructor REJECTS an empty list.
# The message literal 'All models from FallbackModel failed' is what users saw — assert
# it does NOT leak into the new surfaced error string.

# ── VERIFIED LIBRARY CLAIM #3: str(ModelHTTPError) embeds body VERBATIM ───────────────
#   uv run python -c "
#   from pydantic_ai.exceptions import ModelHTTPError
#   print(str(ModelHTTPError(404, 'gemini-x', body={'error': {'message': 'nope'}})))"
#   # → status_code: 404, model_name: gemini-x, body: {'error': {'message': 'nope'}}
# NEVER put str(exc) or exc.body raw into a client payload. Extract the provider message
# (Google/OpenAI shape body['error']['message'], else str(body)), scrub, truncate (300).
# Issue #335 hard constraint: no API keys / Bearer tokens / AIza… values, ever.

# ── VERIFIED LIBRARY CLAIM #4: ResponseRejected can be a group member ─────────────────
#   uv run python -c "
#   from pydantic_ai.models.fallback import ResponseRejected; print(str(ResponseRejected(2)))"
#   # → 2 model response(s) rejected by fallback_on handler
# It carries NO model_name → classify with model_name="(response rejected)" or similar
# deterministic placeholder, reason="response_rejected".

# ── GOTCHA: classification arm placement & non-overlap ────────────────────────────────
# UnexpectedModelBehavior is NOT a ModelAPIError (separate AgentRunError branches), so
# `except (FallbackExceptionGroup, ModelAPIError) as e:` cannot shadow the existing
# misbehavior arm. Place the new arm AFTER TimeoutError, BEFORE UnexpectedModelBehavior
# in BOTH chat() and stream_chat(). Do NOT attempt _salvage_* in the new arm — nothing
# ran, there is nothing to salvage.

# ── GOTCHA: inner `except Exception` at service.py:545 ───────────────────────────────
# stream_text() iteration errors are swallowed by an inner handler (structured-output
# agents can't stream deltas); a mid-stream provider failure re-raises from
# result.get_output() and still hits the OUTER except arms. Put the new arm on the
# OUTER try only — do not touch the inner handler.

# ── GOTCHA: forecastlab_exception_handler DROPS exc.details from the response ─────────
# app/core/exceptions.py:279-288 logs details but problem_response never receives them.
# That is BY DESIGN (details may carry internals). Do NOT stuff failures into details —
# add the parallel `extensions` channel (default None ⇒ zero behavior change for every
# existing raiser) and pass it through explicitly.

# ── GOTCHA: merge extensions on the SERIALIZED dict, not via ProblemDetail(**ext) ──────
# ProblemDetail has extra="allow", but unpacking arbitrary **dict[str, Any] into a
# pydantic-plugin-checked constructor risks mypy/pyright --strict errors. problem_response
# already does problem.model_dump(exclude_none=True) — update THAT dict, guarded by a
# reserved-key frozenset {type,title,status,detail,instance,errors,code,request_id}.

# ── GOTCHA: error_type strings are load-bearing test/UI contracts ─────────────────────
# test_service.py:477 asserts the literal "model_behavior_error". The new literal is
# "fallback_exhausted" — used in service.py, asserted in tests, documented in
# API_CONTRACTS.md. Pick once; never rename casually.

# ── GOTCHA: StreamEvent.data must stay JSON-serializable ─────────────────────────────
# websocket.py sends event.model_dump(mode="json"). Put PLAIN DICTS in data:
# failures=[f.model_dump(mode="json") for f in details] — not BaseModel instances.

# ── GOTCHA: .env bleed + settings singleton (only if a test touches Settings) ─────────
# Service tests monkeypatch service.settings fields (see test_service.py:443) — that
# pattern self-restores. If any new test constructs Settings(...), pass _env_file=None
# (RUNBOOKS incident class).

# ── GOTCHA: Level-3 mutates the operator's persisted config — snapshot/restore ────────
# PATCH /config/ai persists to app_config AND applies live (reset_agent_caches,
# config/service.py:214-216). The local operator override is agent_default_model=
# ollama:gemma4-agent — GET /config/ai first, restore the exact values after the curl
# matrix (E1 session precedent).

# ── GOTCHA: repo has mixed CRLF/LF line endings ───────────────────────────────────────
# Check `git diff --stat` after editing: if a file shows ~all lines changed, your editor
# rewrote line endings — re-edit preserving the file's existing endings.
```

## Implementation Blueprint

### Data models and structure

```python
# app/features/agents/schemas.py — new model + additive ErrorEvent field

FailureReason = Literal[
    "model_not_found", "quota_exhausted", "auth_error",
    "provider_unavailable", "provider_error", "response_rejected", "unknown",
]

class ModelFailureDetail(BaseModel):
    """One classified per-model failure from a FallbackModel chain (issue #335)."""
    model_name: str
    status_code: int | None = None
    reason: FailureReason
    detail: str = ""          # sanitized + truncated provider message — NEVER raw body

class ErrorEvent(BaseModel):
    error: str
    error_type: str
    recoverable: bool = True
    failures: list[ModelFailureDetail] | None = None   # additive (issue #335)
```

```python
# app/features/agents/failures.py — NEW module (pure functions, fully unit-testable)

_SECRET_PATTERNS = (
    re.compile(r"AIza[0-9A-Za-z_\-]{10,}"),                      # Google API keys
    re.compile(r"sk-[A-Za-z0-9_\-]{10,}"),                        # OpenAI/Anthropic-style keys
    re.compile(r"(?i)bearer\s+[A-Za-z0-9._\-]+"),                 # Authorization bearer tokens
    re.compile(r"(?i)(api[_-]?key|token|authorization)[=:]\s*\S+"),
)
_MAX_DETAIL_LEN = 300

def _sanitize(text: str) -> str:
    # sub each pattern with "[redacted]", then truncate to _MAX_DETAIL_LEN

def _provider_message(body: object | None) -> str:
    # dict with Google/OpenAI shape → body["error"]["message"]; str → as-is;
    # anything else → str(body) or "" — ALWAYS through _sanitize at the call site

def classify_model_failures(exc: BaseException) -> list[ModelFailureDetail]:
    # ExceptionGroup (incl. FallbackExceptionGroup): recurse over exc.exceptions (tuple)
    # ModelHTTPError: status map per the reason table; detail=_sanitize(_provider_message(body))
    # ResponseRejected: reason="response_rejected", model_name placeholder
    # other ModelAPIError: reason="provider_error", status None, detail=_sanitize(str(exc))
    # fallback: reason="unknown", detail=_sanitize(str(exc))

def summarize_model_failures(failures: list[ModelFailureDetail]) -> str:
    # deterministic (tests match substrings):
    # 1 failure  → "The configured agent model failed — {leg}"
    # n failures → "All configured agent models failed — {leg}; {leg}; …"
    # leg = "{model_name}: {human label} (HTTP {status_code})" (omit HTTP part when None)
    # labels: model_not_found→"model not found / invalid model name",
    #         quota_exhausted→"quota or rate limit exhausted",
    #         auth_error→"authentication/permission error",
    #         provider_unavailable→"provider unavailable",
    #         provider_error→"provider error", response_rejected→"response rejected",
    #         unknown→"unexpected failure"
```

```python
# app/core/problem_details.py — additive
AGENT_FALLBACK_EXHAUSTED_CODE = "AGENT_FALLBACK_EXHAUSTED"          # next to EMBEDDING_AUTH_CODE
ERROR_TYPES[AGENT_FALLBACK_EXHAUSTED_CODE] = f"{ERROR_TYPE_BASE}/agent-fallback-exhausted"

_RESERVED_PROBLEM_KEYS = frozenset(
    {"type", "title", "status", "detail", "instance", "errors", "code", "request_id"}
)

def problem_response(..., extensions: dict[str, Any] | None = None) -> ProblemDetailResponse:
    content = problem.model_dump(exclude_none=True)
    if extensions:
        content.update({k: v for k, v in extensions.items() if k not in _RESERVED_PROBLEM_KEYS})
    return ProblemDetailResponse(status_code=status, content=content)
```

```python
# app/core/exceptions.py — additive
class ForecastLabError(Exception):
    def __init__(self, message, code=..., status_code=..., details=None,
                 extensions: dict[str, Any] | None = None) -> None:
        ...
        self.extensions = extensions or {}   # RESPONSE-VISIBLE (details stays log-only)

# handler: problem_response(..., extensions=exc.extensions or None)

class AgentFallbackExhaustedError(ForecastLabError):
    """502 — every model in the agent's fallback chain failed (issue #335).

    Mirrors EmbeddingProviderAuthError: machine-readable code so clients can
    classify; carries the per-model failures as an RFC 7807 extension member.
    """
    error_type_uri = ERROR_TYPES[AGENT_FALLBACK_EXHAUSTED_CODE]
    def __init__(self, message: str, failures: list[dict[str, Any]]) -> None:
        super().__init__(message=message, code=AGENT_FALLBACK_EXHAUSTED_CODE,
                         status_code=502, extensions={"failures": failures})
```

### Tasks (in order)

```yaml
Task 1:
MODIFY app/features/agents/schemas.py:
  - ADD FailureReason Literal alias + ModelFailureDetail near ErrorEvent (line ~304)
  - ADD `failures: list[ModelFailureDetail] | None = None` to ErrorEvent
  - PRESERVE every existing field and Literal value on StreamEvent/ErrorEvent

Task 2:
CREATE app/features/agents/failures.py:
  - Pure module: _SECRET_PATTERNS, _sanitize, _provider_message,
    classify_model_failures, summarize_model_failures per blueprint
  - Imports: pydantic_ai.exceptions (ModelAPIError, ModelHTTPError),
    pydantic_ai.models.fallback (ResponseRejected), app.features.agents.schemas
  - Recursion guard: ExceptionGroup members may nest — recurse; classify leaves only

Task 3:
MODIFY app/core/problem_details.py:
  - ADD AGENT_FALLBACK_EXHAUSTED_CODE constant next to EMBEDDING_AUTH_CODE (line 30)
  - ADD ERROR_TYPES entry "/errors/agent-fallback-exhausted"
  - ADD optional `extensions` param to problem_response; merge on the serialized dict
    guarded by _RESERVED_PROBLEM_KEYS (see gotcha — do NOT ProblemDetail(**extensions))
  - PRESERVE the no-extensions output byte-for-byte (default None)

Task 4:
MODIFY app/core/exceptions.py:
  - ADD optional `extensions` kwarg on ForecastLabError.__init__ (stored attribute)
  - ADD AgentFallbackExhaustedError mirroring EmbeddingProviderAuthError (lines 227-254)
  - MODIFY forecastlab_exception_handler: pass extensions=exc.extensions or None
  - PRESERVE: details stays log-only; every existing subclass signature unchanged

Task 5:
MODIFY app/features/agents/service.py:
  - EXTEND import line 25: from pydantic_ai.exceptions import (
      FallbackExceptionGroup, ModelAPIError, UnexpectedModelBehavior)
  - ADD import: classify_model_failures, summarize_model_failures from .failures;
    AgentFallbackExhaustedError from app.core.exceptions
  - chat(): NEW arm between TimeoutError (309) and UnexpectedModelBehavior (313):
      except (FallbackExceptionGroup, ModelAPIError) as e:
          failures = classify_model_failures(e)
          logger.warning("agents.chat_fallback_exhausted", session_id=session_id,
                         failure_count=len(failures),
                         reasons=[f.reason for f in failures])   # safe fields only
          raise AgentFallbackExhaustedError(
              summarize_model_failures(failures),
              failures=[f.model_dump(mode="json") for f in failures]) from e
  - stream_chat(): NEW arm between TimeoutError (693) and UnexpectedModelBehavior (697),
    mirroring the misbehavior tail at 759-770:
      except (FallbackExceptionGroup, ModelAPIError) as e:
          failures = classify_model_failures(e)
          logger.warning("agents.stream_chat_fallback_exhausted", ...)  # same safe fields
          now = datetime.now(UTC); session.last_activity = now; await db.flush()
          yield StreamEvent(event_type="error", data={
              "error": summarize_model_failures(failures),
              "error_type": "fallback_exhausted",
              "recoverable": True,
              "failures": [f.model_dump(mode="json") for f in failures],
          }, timestamp=now)
          return
  - PRESERVE: no _salvage_* calls in the new arms; misbehavior arms byte-identical

Task 6:
CREATE app/features/agents/tests/test_failures.py:
  - Classification matrix: parametrize ModelHTTPError statuses
    (404→model_not_found, 429→quota_exhausted, 401/403→auth_error,
     500/503→provider_unavailable, 418→provider_error)
  - Group of (404 + 429) → 2 details preserving model_name order
  - Nested group (group inside group) → flattened leaves
  - Bare ModelAPIError (construct a minimal subclass or ModelHTTPError-free instance)
    → provider_error, status None
  - ResponseRejected member → response_rejected
  - Unknown exception → unknown
  - Secret scrub: body={"error": {"message": "key AIzaFakeKey1234567890abcdef leaked"}}
    → "[redacted]" in detail, "AIza" not in detail; same for "sk-fake…" and "Bearer x.y.z"
  - Truncation: 1000-char provider message → len(detail) <= 300
  - summarize_model_failures: exact-substring asserts for 1-leg and 2-leg shapes

Task 7:
EXTEND app/features/agents/tests/test_service.py:
  - TestAgentServiceStreamChat.test_stream_chat_fallback_exhausted_yields_classified_error:
      MIRROR test_stream_chat_model_misbehavior_yields_error_event (426-480) exactly,
      but _RaisingStream.__aenter__ raises FallbackExceptionGroup(
        "All models from FallbackModel failed",
        [ModelHTTPError(404, "google-gla:gemini-3-flash-preview",
                        body={"error": {"message": "models/... is not found"}}),
         ModelHTTPError(429, "gemini-2.5-flash",
                        body={"error": {"message": "RESOURCE_EXHAUSTED ... AIzaFakeKey123456789"}})])
      ASSERT: len(events)==1; event_type=="error"; data["error_type"]=="fallback_exhausted";
      data["recoverable"] is True; len(data["failures"])==2;
      failures[0]["reason"]=="model_not_found"; failures[1]["reason"]=="quota_exhausted";
      "sub-exceptions" not in data["error"];
      "AIza" not in json.dumps(events[0].model_dump(mode="json"))
  - TestAgentServiceStreamChat.test_stream_chat_bare_model_api_error_classified:
      same harness, __aenter__ raises ModelHTTPError(401, "anthropic:claude-test") →
      1 error event, failures==1, reason=="auth_error"
  - TestAgentServiceChat.test_chat_fallback_exhausted_raises_classified_error:
      MIRROR the chat misbehavior test harness; agent.run = AsyncMock(side_effect=<group>);
      pytest.raises(AgentFallbackExhaustedError) → exc.status_code==502,
      exc.code=="AGENT_FALLBACK_EXHAUSTED", len(exc.extensions["failures"])==2

Task 8:
EXTEND app/features/agents/tests/test_routes.py (integration):
  - test_chat_fallback_exhausted_returns_502_problem_json:
      create session (patched agent factory, existing pattern), then patch the service
      agent so run raises the 404+429 group; POST /agents/sessions/{id}/chat →
      ASSERT status 502; headers content-type startswith "application/problem+json";
      body["code"]=="AGENT_FALLBACK_EXHAUSTED";
      body["type"].endswith("/errors/agent-fallback-exhausted");
      len(body["failures"])==2 with both reasons; "request_id" present

Task 9:
CREATE app/core/tests/test_problem_details.py:
  - test_problem_response_without_extensions_unchanged: no extensions → body has no
    "failures" key; code/type/status as before
  - test_problem_response_merges_extensions: extensions={"failures":[{"a":1}]} → in body
  - test_problem_response_extensions_cannot_override_reserved:
    extensions={"status": 200, "code": "HACK"} → body keeps the real status/code

Task 10 (docs, same PR):
EXTEND docs/_base/API_CONTRACTS.md:
  - WS `/agents/stream` error bullet: document `error_type="fallback_exhausted"` and the
    additive Optional `failures: [{model_name, status_code, reason, detail}]` data key
  - agents chat row: note the 502 AGENT_FALLBACK_EXHAUSTED problem+json (additive)
```

### Integration Points

```yaml
DATABASE:  none — nothing persisted changes; no migration
ROUTES:    none — REST surface comes via the global ForecastLabError handler (502)
WEBSOCKET: service-level yield only; websocket.py generic handler untouched (backstop)
CONFIG:    none — no new settings; no change to agent_require_approval (no new mutation surface)
FRONTEND:  none — chat.tsx renders the summary string as-is; failures key is additive
DOCS:      docs/_base/API_CONTRACTS.md (Task 10)
```

## Validation Loop

### Level 1: Syntax & Style

```bash
uv run ruff check app/features/agents/ app/core/ && uv run ruff format --check .
uv run mypy app/ && uv run pyright app/        # both --strict; zero new errors
```

### Level 2: Unit tests (no DB)

```bash
uv run pytest -v \
  app/features/agents/tests/test_failures.py \
  app/features/agents/tests/test_service.py \
  app/core/tests/test_problem_details.py
# Full unit gate — proves misbehavior/salvage paths and every other consumer untouched:
uv run pytest -v -m "not integration"
```

### Level 3: Integration (live API; snapshot config FIRST — see gotcha)

```bash
docker compose up -d
uv run pytest -v -m integration app/features/agents/tests/test_routes.py

# Live REST leg (fresh uvicorn; snapshot + restore the operator's persisted config!):
curl -s http://localhost:8123/config/ai          # SNAPSHOT current model ids
curl -si -X PATCH http://localhost:8123/config/ai -H 'Content-Type: application/json' \
  -d '{"agent_default_model":"openai:gpt-nonexistent-e2","agent_fallback_model":"openai:gpt-also-nonexistent"}'
SID=$(curl -s -X POST http://localhost:8123/agents/sessions \
  -H 'Content-Type: application/json' -d '{"agent_type":"experiment"}' | python3 -c 'import sys,json;print(json.load(sys.stdin)["session_id"])')
curl -si -X POST http://localhost:8123/agents/sessions/$SID/chat \
  -H 'Content-Type: application/json' -d '{"message":"hello"}' | head -30
#   expect: HTTP/1.1 502, application/problem+json, code AGENT_FALLBACK_EXHAUSTED,
#           failures[] with reason "model_not_found" on both legs
curl -si -X PATCH http://localhost:8123/config/ai -H 'Content-Type: application/json' \
  -d '{"agent_default_model":"<snapshot>","agent_fallback_model":"<snapshot>"}'   # RESTORE
```

### Level 4 (optional dogfood): chat UI over WebSocket

With the broken model pair patched in, open `/chat` (localhost:5173), send a message →
the transcript should show the classified two-leg summary (`model not found … (HTTP 404); …`)
instead of `Stream error: All models from FallbackModel failed`. Restore config after.

## Final Validation Checklist

- [ ] `uv run ruff check . && uv run ruff format --check .` clean
- [ ] `uv run mypy app/ && uv run pyright app/` clean (strict)
- [ ] `uv run pytest -v -m "not integration"` green — including the untouched
      `model_behavior_error` and salvage tests
- [ ] New tests cover: status matrix, nested group, bare ModelAPIError, ResponseRejected,
      secret scrub (AIza/sk-/Bearer), truncation, summary shapes, stream 404+429 event,
      stream bare-401 event, chat raise, route 502 (both legs), extensions merge + guard
- [ ] `uv run pytest -v -m integration app/features/agents/tests/test_routes.py` green
- [ ] Level-3 curl matrix matches; operator config snapshot RESTORED and re-verified
- [ ] No secret-like string in any serialized payload (asserted on full JSON dumps)
- [ ] `git diff --stat` shows surgical diffs (no whole-file line-ending churn)
- [ ] Commits: `fix(agents,api): surface fallback model failures with classified details (#335)`
      (+ `docs(docs): …` for API_CONTRACTS if split); no AI trailers
- [ ] PR into `dev` from `fix/agents-surface-fallback-failures`; CI green

---

## Out of Scope (this PRP)

- **Frontend failure-detail rendering** (chips/expandable list from the `failures` key) —
  the summary string already lands in the transcript; promote to its own `feat(ui)` issue
  if dogfood demands richer rendering.
- **Retry/circuit-breaker middleware or metrics** — explicitly rejected in umbrella #380
  (violates the no-external-observability / single-host principle).
- **Classifying `UsageLimitExceeded` / `ConcurrencyLimitExceeded`** — pydantic-ai usage-cap
  errors, not provider failures; today's behavior (generic backstop) stands.
- **Surfacing agent-BUILD failures** (missing API key → `ValueError` in
  `build_agent_model_with_fallback`) — a config-time failure class, already log-visible;
  separate concern from run-time provider failure.
- **E6 release-gate dogfood** — umbrella #380's own closing epic.

## Anti-Patterns to Avoid

- ❌ Don't put `str(exception)` or `exc.body` raw into any client payload — sanitize-then-truncate only.
- ❌ Don't stuff failures into `ForecastLabError.details` — the handler drops it by design; use `extensions`.
- ❌ Don't use `except*` — a plain `except FallbackExceptionGroup` keeps the single-yield contract simple.
- ❌ Don't touch `websocket.py` — the generic handler is the deliberate backstop.
- ❌ Don't salvage (`_salvage_*`) in the new arms — no model ran; there is nothing to salvage.
- ❌ Don't rename `model_behavior_error` or weaken its tests — extend alongside.
- ❌ Don't widen `agent_require_approval` or any mutation surface — this is read-path-only hardening.
- ❌ Don't forget to RESTORE the operator's persisted `ollama:gemma4-agent` override after Level 3.

---

**One-pass confidence score: 8/10** — every catch point, schema, and precedent is
runtime-verified with exact line anchors, and the classifier is a pure module with a mirrored
test harness. Deductions: the stream-test async-CM mocking is fiddly (mitigated by mirroring
test_service.py:426-480 verbatim), and the `extensions` merge must dodge the
pydantic-plugin/strict-mypy trap (mitigated by the serialized-dict merge decision).
