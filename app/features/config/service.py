"""Service layer for the runtime configuration slice.

Responsibilities:
- Read the *effective* AI-model configuration (Settings + which keys come from
  the ``app_config`` override store), with secrets masked.
- Persist operator edits to ``app_config``, apply them onto the cached
  ``Settings`` singleton, and invalidate the agent / embedding caches so the
  change takes effect live (no process restart).
- Re-apply persisted overrides on startup.
- Probe provider connectivity (Ollama reachability + cloud key presence).

CRITICAL: API key values are NEVER returned in a GET response and NEVER logged
(only key names + booleans). See ``.claude/rules/security-patterns.md``.
"""

from __future__ import annotations

import os
from typing import Any

import httpx
from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.logging import get_logger
from app.features.agents.agents.base import reset_agent_caches
from app.features.config.models import AppConfig
from app.features.config.schemas import (
    ALLOWED_OVERRIDE_KEYS,
    SECRET_ENV_NAMES,
    SECRET_KEYS,
    AIModelConfig,
    AIModelConfigUpdate,
    ApiKeyStatus,
    OllamaModel,
    ProviderHealth,
)
from app.features.rag.embeddings import reset_embedding_service
from app.features.rag.models import DocumentChunk

logger = get_logger(__name__)

# Scalar types an ``app_config`` override value may hold.
OverrideValue = str | int | float | bool


# =============================================================================
# Helpers
# =============================================================================


def _mask_secret(value: str) -> str | None:
    """Return a masked preview of a secret, or None when it is unset.

    Shows a short prefix and the last 4 characters so an operator can confirm
    *which* key is configured without the value ever leaving the server intact.
    """
    if not value:
        return None
    if len(value) <= 11:
        return f"…{value[-4:]}"
    return f"{value[:7]}…{value[-4:]}"


def _key_status(provider: str, value: str) -> ApiKeyStatus:
    """Build an :class:`ApiKeyStatus` for one provider key."""
    return ApiKeyStatus(provider=provider, is_set=bool(value), masked=_mask_secret(value))


async def _load_overrides(db: AsyncSession) -> dict[str, Any]:
    """Load all persisted overrides as a ``{key: scalar}`` mapping."""
    result = await db.execute(select(AppConfig))
    return {row.key: row.value.get("v") for row in result.scalars().all()}


async def _count_rag_chunks(db: AsyncSession) -> int:
    """Count indexed RAG chunks (used by the embedding-dimension-change guard)."""
    result = await db.execute(select(func.count()).select_from(DocumentChunk))
    return int(result.scalar_one())


async def _upsert_app_config(db: AsyncSession, key: str, value: OverrideValue) -> None:
    """Insert-or-update one override row (parameter-bound ``ON CONFLICT``)."""
    stmt = pg_insert(AppConfig).values(key=key, value={"v": value})
    stmt = stmt.on_conflict_do_update(
        index_elements=["key"],
        set_={"value": stmt.excluded.value, "updated_at": func.now()},
    )
    await db.execute(stmt)


async def _fetch_ollama_models() -> list[OllamaModel]:
    """Query the Ollama host's native ``/api/tags`` endpoint.

    Returns:
        The host's pulled models.

    Raises:
        httpx.HTTPError: If the host is unreachable or returns an error.
    """
    settings = get_settings()
    base_url = settings.ollama_base_url.rstrip("/")
    async with httpx.AsyncClient(timeout=httpx.Timeout(10.0, connect=5.0)) as client:
        response = await client.get(f"{base_url}/api/tags")
        response.raise_for_status()
        data = response.json()

    models: list[OllamaModel] = []
    for entry in data.get("models", []):
        details = entry.get("details") or {}
        models.append(
            OllamaModel(
                name=entry.get("name") or entry.get("model") or "unknown",
                size_bytes=entry.get("size"),
                family=details.get("family"),
            )
        )
    return models


# =============================================================================
# Public service functions
# =============================================================================


async def get_effective_config(db: AsyncSession) -> AIModelConfig:
    """Return the effective AI-model configuration with secrets masked.

    Args:
        db: Async database session.

    Returns:
        The live configuration plus which keys are sourced from ``app_config``.
    """
    settings = get_settings()
    overrides = await _load_overrides(db)

    return AIModelConfig(
        agent_default_model=settings.agent_default_model,
        agent_fallback_model=settings.agent_fallback_model,
        agent_temperature=settings.agent_temperature,
        agent_max_tokens=settings.agent_max_tokens,
        agent_thinking_budget=settings.agent_thinking_budget,
        agent_max_tool_calls=settings.agent_max_tool_calls,
        agent_timeout_seconds=settings.agent_timeout_seconds,
        agent_retry_attempts=settings.agent_retry_attempts,
        agent_session_ttl_minutes=settings.agent_session_ttl_minutes,
        agent_require_approval=list(settings.agent_require_approval),
        rag_embedding_provider=settings.rag_embedding_provider,
        rag_embedding_model=settings.rag_embedding_model,
        rag_embedding_dimension=settings.rag_embedding_dimension,
        ollama_base_url=settings.ollama_base_url,
        ollama_embedding_model=settings.ollama_embedding_model,
        api_keys=[
            _key_status("openai", settings.openai_api_key),
            _key_status("anthropic", settings.anthropic_api_key),
            _key_status("google", settings.google_api_key),
        ],
        overridden_keys=sorted(k for k in overrides if k in ALLOWED_OVERRIDE_KEYS),
    )


async def apply_overrides_on_startup(db: AsyncSession) -> None:
    """Re-apply persisted overrides onto the ``Settings`` singleton at startup.

    Safe by design: if the ``app_config`` table does not exist yet (brand-new
    database) the load is caught and the app boots on environment defaults.

    Args:
        db: Async database session.
    """
    try:
        overrides = await _load_overrides(db)
    except Exception as exc:  # never let config crash startup
        logger.warning(
            "config.overrides_load_failed",
            error=str(exc),
            error_type=type(exc).__name__,
        )
        return

    if not overrides:
        return

    settings = get_settings()
    applied: list[str] = []
    for key, value in overrides.items():
        if key not in ALLOWED_OVERRIDE_KEYS:
            continue
        setattr(settings, key, value)
        if key in SECRET_KEYS and isinstance(value, str):
            os.environ[SECRET_ENV_NAMES[key]] = value
        applied.append(key)

    # Drop cached singletons so the first agent / embedding build uses overrides.
    reset_agent_caches()
    reset_embedding_service()
    logger.info("config.overrides_applied", keys=sorted(applied))


async def update_config(db: AsyncSession, payload: AIModelConfigUpdate) -> AIModelConfig:
    """Persist + apply an AI-model configuration change.

    Validates (model identifiers are checked at the schema boundary), guards
    against breaking RAG retrieval, persists to ``app_config``, mutates the
    live ``Settings`` singleton, and invalidates the agent / embedding caches.

    Args:
        db: Async database session.
        payload: The partial update; only non-null fields are applied.

    Returns:
        The effective configuration after the change.

    Raises:
        HTTPException: 400 if no fields were supplied; 409 if the embedding
            dimension change would break existing RAG chunks (without force).
    """
    settings = get_settings()
    changes: dict[str, Any] = payload.model_dump(exclude_none=True, exclude={"force"})

    if not changes:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No configuration fields provided to update.",
        )

    # Guard: changing the embedding dimension orphans every existing chunk.
    new_dim = changes.get("rag_embedding_dimension")
    if new_dim is not None and new_dim != settings.rag_embedding_dimension and not payload.force:
        chunk_count = await _count_rag_chunks(db)
        if chunk_count > 0:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=(
                    f"Changing the embedding dimension with {chunk_count} indexed "
                    "RAG chunk(s) breaks retrieval. Delete the RAG sources first, "
                    "or resend the request with force=true."
                ),
            )

    # Persist every override (parameter-bound upsert).
    for key, value in changes.items():
        await _upsert_app_config(db, key, value)
    await db.commit()

    # Apply onto the live (cached) Settings singleton; mirror secrets to env.
    for key, value in changes.items():
        setattr(settings, key, value)
        if key in SECRET_KEYS and isinstance(value, str):
            # Unconditional overwrite — a replaced key must evict the stale one.
            os.environ[SECRET_ENV_NAMES[key]] = value

    # CRITICAL: invalidate caches so the change is visible on the next request.
    reset_agent_caches()
    reset_embedding_service()

    logger.info(
        "config.updated",
        keys=sorted(changes),
        secrets=sorted(k for k in changes if k in SECRET_KEYS),
    )
    return await get_effective_config(db)


async def get_provider_health() -> list[ProviderHealth]:
    """Report connectivity for every AI provider.

    Ollama is probed live (``/api/tags``); cloud providers report API-key
    presence (a cheap, offline proxy for usability).

    Returns:
        One :class:`ProviderHealth` per provider.
    """
    settings = get_settings()
    health: list[ProviderHealth] = []

    # Ollama — live probe.
    try:
        models = await _fetch_ollama_models()
        health.append(
            ProviderHealth(
                provider="ollama",
                reachable=True,
                detail=(f"Reachable at {settings.ollama_base_url} ({len(models)} model(s) pulled)"),
                models=[m.name for m in models],
            )
        )
    except httpx.HTTPError as exc:
        health.append(
            ProviderHealth(
                provider="ollama",
                reachable=False,
                detail=f"Not reachable at {settings.ollama_base_url}: {exc}",
            )
        )

    # Cloud providers — key presence.
    for provider, key in (
        ("openai", settings.openai_api_key),
        ("anthropic", settings.anthropic_api_key),
        ("google", settings.google_api_key),
    ):
        is_set = bool(key)
        health.append(
            ProviderHealth(
                provider=provider,
                reachable=is_set,
                detail="API key configured" if is_set else "API key not set",
            )
        )

    return health


async def list_ollama_models() -> list[OllamaModel]:
    """List the Ollama host's pulled models.

    Returns:
        The host's pulled models.

    Raises:
        HTTPException: 502 if the Ollama host is unreachable.
    """
    try:
        return await _fetch_ollama_models()
    except httpx.HTTPError as exc:
        settings = get_settings()
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=(
                f"Could not reach Ollama at {settings.ollama_base_url}: {exc}. "
                "Ensure 'ollama serve' is running."
            ),
        ) from exc
