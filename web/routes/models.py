"""Model listing API route."""

import asyncio

from fastapi import APIRouter, Depends, HTTPException, Query

from ai.openai_client import create_openai_client
from services import get_user_settings
from services.log_service import record_web_action
from web.auth import get_current_user

router = APIRouter(prefix="/api/models", tags=["models"])


def _resolve_provider(settings: dict, provider: str | None) -> tuple[str, str, str]:
    """Resolve provider configuration.

    Returns (resolved_name, api_key, base_url).
    """
    if not provider:
        return "current", settings.get("api_key", ""), settings.get("base_url", "")

    presets = settings.get("api_presets", {}) or {}
    if provider in presets:
        preset = presets[provider]
        return provider, preset.get("api_key", ""), preset.get("base_url", "")

    lowered = provider.lower()
    for name, preset in presets.items():
        if name.lower() == lowered:
            return name, preset.get("api_key", ""), preset.get("base_url", "")

    raise HTTPException(status_code=404, detail="Provider not found")


@router.get("")
async def list_models(
    provider: str | None = Query(None, description="Provider preset name; omit for current config"),
    user_id: int = Depends(get_current_user),
):
    """List models from OpenAI-compatible /models endpoint."""
    settings = get_user_settings(user_id)
    resolved_name, api_key, base_url = _resolve_provider(settings, provider)
    if not api_key:
        raise HTTPException(status_code=400, detail="API key is empty")
    if not base_url:
        raise HTTPException(status_code=400, detail="Base URL is empty")

    loop = asyncio.get_running_loop()
    try:
        models = await loop.run_in_executor(
            None,
            lambda: create_openai_client(api_key=api_key, base_url=base_url).list_models(),
        )
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Failed to fetch models: {exc}") from exc

    record_web_action(
        user_id,
        "models.list",
        {"provider": resolved_name, "count": len(models)},
    )
    return {
        "provider": resolved_name,
        "models": models,
        "count": len(models),
        "current_model": settings.get("model", ""),
    }
