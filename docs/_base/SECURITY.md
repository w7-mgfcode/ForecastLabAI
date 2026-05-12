# ForecastLabAI Security
> Source: `.claude/rules/security-patterns.md` (authoritative), `app/core/config.py`, `app/main.py`, `.github/workflows/`. [ASSUMPTION] compliance scope is **none** (portfolio repo).

## Threat Model (Scope)

ForecastLabAI is a **single-tenant, single-host** portfolio demo. There is no auth, no RBAC, no multi-tenancy. The threat surface is:

1. Untrusted query input flowing through SQLAlchemy → could enable SQLi without parameter binding.
2. LLM-controlled tool calls (PydanticAI agents) → could mutate registry/aliases without HITL approval.
3. RAG retrieval echoing untrusted document content → potential prompt-injection vector into agent context.
4. External provider API keys in `.env` → could leak via logs or commit.
5. Frontend CORS misconfiguration → could expose dev-only endpoints to attacker-controlled origins.

## Hard Rules (from `.claude/rules/security-patterns.md`)

These are enforced on every PR. Violations must be fixed before merge.

- **Forbidden:** `eval` / `exec` / `compile` on user input; `subprocess(shell=True, …user_input)`; raw SQL concat; `pickle.loads` on untrusted data; `verify=False` on httpx/openai clients; hardcoded secrets; credentials in git URLs; logging full prompts/responses; path traversal via `..`.
- **Required:** Pydantic v2 validation at every boundary; SQLAlchemy 2.0 parameter binding; `pathlib.Path.resolve()` for file ops; `yaml.safe_load`; RFC 7807 error shape; structured logging without secret values.

## Secrets Management

| Item | Storage | Loaded By | Rotation |
|------|---------|-----------|----------|
| `OPENAI_API_KEY` | `.env` (not committed) | `app.core.config.Settings` | Manual; edit `.env`, restart uvicorn |
| `ANTHROPIC_API_KEY` | `.env` | `Settings` | Manual |
| `GOOGLE_API_KEY` | `.env` (optional) | `Settings` | Manual |
| `DATABASE_URL` | `.env` or default localhost | `Settings` | N/A (local docker-compose) |

Two-file model (mandatory):
- `.env.example` — committed schema with placeholders, every new var added here first.
- `.env` — real values, **NEVER** committed (`.gitignore`d).

Never log decrypted values, even at DEBUG. Log key NAMES only (`openai_api_key_set=bool(s.openai_api_key)`).

## Input Validation

- Every FastAPI endpoint validates input via Pydantic v2 — no raw `Body(Any)`.
- Every agent tool input validated by Pydantic before execution (`app/features/agents/tools/`).
- LLM **responses** are not trusted: structured outputs parsed via Pydantic; freeform text never executed.
- Allow-lists over deny-lists (e.g., `model_type ∈ {naive, seasonal_naive, moving_average, lightgbm}`; embedding provider ∈ `{openai, ollama}`; model identifier provider ∈ `{anthropic, openai, google-gla, google-vertex}`).

## Network Security

- Backend binds `0.0.0.0:8123` by default (`api_host` / `api_port` in `Settings`, `app/core/config.py:32-33`; the `# noqa: S104` is intentional for single-host LAN demo). Fine on a personal LAN; would need a reverse proxy + TLS for any public exposure.
- CORS allow-list in `app/main.py`: dev permits `localhost`/`127.0.0.1`/private LAN ranges via regex; **production sets explicit origins via empty list + no regex** — review before any non-dev deploy.
- No TLS at the app layer; rely on `docker-compose` private network for DB. Postgres password is the dev default `forecastlab/forecastlab` — change if exposing the host.

## LLM / Agent Security

- Token budget cap per session (`agent_max_tokens=4096` default).
- Tool-call cap per session (`agent_max_tool_calls=10` default).
- Timeout wrap around `agent.run()` / `agent.run_stream()` (`agent_timeout_seconds=120`).
- HITL approval required for mutating tools — `agent_require_approval=["create_alias","archive_run"]`. Never widen the agent's mutation surface without adding the new tool name to that list.
- Never log full prompts/responses at INFO; DEBUG only with explicit operator opt-in.

## External Integrations Security

| Integration | Auth | Data Sent | Note |
|-------------|------|-----------|------|
| OpenAI embeddings | API key | Document chunks (markdown / openapi) | No PII in indexed corpus — corpus is project's own docs |
| OpenAI / Anthropic / Gemini agent LLM | API key | User chat messages + tool descriptions + tool results | Chat messages may contain user-supplied text |
| Ollama embeddings | none (LAN) | Document chunks | Local; preferred for keeping data off external services |

## CI / Workflow Security

| Workflow | Pinning | Notes |
|----------|---------|-------|
| `ci.yml` | `actions/checkout@v6`, `astral-sh/setup-uv@v7` | First-party `actions/*` may use major-version per rule |
| `cd-release.yml` | `actions/checkout@v6`, `actions/upload-artifact@v7` (first-party, major-pin OK) **+** `googleapis/release-please-action@v5`, `astral-sh/setup-uv@v7` (**third-party, major-pinned**) | ⚠️ The two third-party actions violate `security-patterns.md` ("Pin third-party GitHub Actions by full 40-char SHA"). Open issue to SHA-pin both, with the `# vX.Y.Z` comment trailer per rule. |
| `dependency-check.yml`, `phase-snapshot.yml`, `schema-validation.yml` | Same first-party `actions/*` + `astral-sh/setup-uv@v7` pattern as the others | Same third-party major-pin gap on `astral-sh/setup-uv@v7` — covered by the same SHA-pin issue |

Dependabot watches `.github/workflows/` weekly (`.github/dependabot.yml`) — keep its PRs current.

## Scanning & Compliance

| Check | Tool | Frequency | Blocks Merge? |
|-------|------|-----------|---------------|
| Lint + format | ruff | every PR | Yes |
| Type check | mypy --strict + pyright --strict | every PR | Yes |
| Unit tests | pytest | every PR | Yes |
| Integration tests | pytest -m integration against Postgres service | every PR | Yes |
| Migration apply check | alembic upgrade head on fresh DB | every PR | Yes |
| Dependency audit | `.github/workflows/dependency-check.yml` | Weekly cron (Sun 00:00 UTC) + manual dispatch | No (out-of-band; not a per-PR gate) — but `fail_on_vulnerabilities` input defaults `true` |
| Secrets detection | partial — `detect-private-key` hook in `.pre-commit-config.yaml` catches private SSH/TLS keys; no broader gitleaks/trufflehog scanner is wired in | every commit (pre-commit) | No — local hook only, not a CI gate |

## Compliance Constraints

| Framework | Applies | Note |
|-----------|---------|------|
| PCI-DSS | No | No card data |
| SOC 2 | No | Portfolio repo |
| GDPR / PII | No | Seeded synthetic data only |
| HIPAA | No | No health data |

[ASSUMPTION] confirmed via Phase 2 question. Re-evaluate if scope changes.
