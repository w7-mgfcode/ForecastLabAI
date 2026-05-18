"""FastAPI routes for runtime AI-model configuration.

Provides the ``/config`` surface backing the dashboard "AI Models" admin tab:
read the effective config, edit it (applied live), and probe provider health.
"""

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.logging import get_logger
from app.features.config import schemas, service

router = APIRouter(prefix="/config", tags=["config"])
logger = get_logger(__name__)


@router.get(
    "/ai",
    response_model=schemas.AIModelConfig,
    summary="Get effective AI-model configuration",
    description=(
        "Return the live agent LLM + RAG embedding configuration. API keys are "
        "masked — the raw value is never returned."
    ),
)
async def get_ai_config(
    db: AsyncSession = Depends(get_db),
) -> schemas.AIModelConfig:
    """Return the effective AI-model configuration with masked secrets."""
    return await service.get_effective_config(db)


@router.patch(
    "/ai",
    response_model=schemas.AIModelConfig,
    summary="Update AI-model configuration",
    description=(
        "Persist and immediately apply changes to the agent LLM, RAG embedding "
        "model, or provider API keys. Changes take effect with no restart. "
        "Returns 409 if an embedding-dimension change would break indexed RAG "
        "chunks (resend with force=true to override)."
    ),
)
async def update_ai_config(
    payload: schemas.AIModelConfigUpdate,
    db: AsyncSession = Depends(get_db),
) -> schemas.AIModelConfig:
    """Persist + apply an AI-model configuration change.

    Raises:
        HTTPException: 400 (no fields), 409 (dimension-change guard), or 422
            (invalid model identifier — raised at the schema boundary).
    """
    return await service.update_config(db, payload)


@router.get(
    "/providers/health",
    response_model=list[schemas.ProviderHealth],
    summary="Check AI provider connectivity",
    description=(
        "Report connectivity for each provider: Ollama is probed live, cloud "
        "providers report API-key presence."
    ),
)
async def get_providers_health() -> list[schemas.ProviderHealth]:
    """Return connectivity status for every AI provider."""
    return await service.get_provider_health()


@router.get(
    "/ollama/models",
    response_model=list[schemas.OllamaModel],
    summary="List local Ollama models",
    description="List the models pulled on the configured Ollama host.",
)
async def get_ollama_models() -> list[schemas.OllamaModel]:
    """List the Ollama host's pulled models.

    Raises:
        HTTPException: 502 if the Ollama host is unreachable.
    """
    return await service.list_ollama_models()
