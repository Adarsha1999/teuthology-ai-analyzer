"""Config endpoint — returns the provider catalog and app settings for the frontend."""
from __future__ import annotations

from fastapi import APIRouter

from app.core.llm_config import get_settings
from app.models.schemas import ConfigOut
from app.services.connection_service import build_config_providers

router = APIRouter(tags=["Config"])


@router.get("/config", response_model=ConfigOut)
def get_config() -> ConfigOut:
    """Return the full application config including all available LLM providers.

    The frontend uses this to populate the provider/model selector dropdown.
    """
    settings = get_settings()
    return ConfigOut(
        default_provider=settings.llm_default_provider,
        providers=build_config_providers(),
        pulpito_base=settings.pulpito_base,
    )
