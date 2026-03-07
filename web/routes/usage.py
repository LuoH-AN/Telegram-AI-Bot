"""Usage / token stats API routes."""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from cache import cache
from services import (
    get_token_limit,
    get_total_tokens_all_personas,
    get_remaining_tokens,
    get_usage_percentage,
    get_current_persona_name,
    set_token_limit,
    reset_token_usage,
)
from services.log import record_web_action
from web.auth import get_current_user

router = APIRouter(prefix="/api/usage", tags=["usage"])


class UsageResetBody(BaseModel):
    persona: str | None = None


class TokenLimitBody(BaseModel):
    persona: str | None = None
    token_limit: int = Field(..., ge=0)


def _resolve_persona(user_id: int, persona_name: str | None) -> str:
    name = (persona_name or "").strip() or get_current_persona_name(user_id)
    personas = cache.get_personas(user_id)
    if name not in personas:
        raise HTTPException(status_code=404, detail="Persona not found")
    return name


@router.get("")
async def get_usage(user_id: int = Depends(get_current_user)):
    """Return token usage statistics."""
    persona_name = get_current_persona_name(user_id)
    total_all = get_total_tokens_all_personas(user_id)

    current_limit = get_token_limit(user_id, persona_name)
    current_remaining = get_remaining_tokens(user_id, persona_name)
    current_percentage = get_usage_percentage(user_id, persona_name)

    personas = cache.get_personas(user_id)
    per_persona = []
    for name in personas:
        usage = cache.get_token_usage(user_id, name)
        per_persona.append({
            "persona": name,
            "prompt_tokens": usage.get("prompt_tokens", 0),
            "completion_tokens": usage.get("completion_tokens", 0),
            "total_tokens": usage.get("total_tokens", 0),
            "token_limit": usage.get("token_limit", 0),
        })

    per_persona.sort(key=lambda x: (x["persona"] != "default", x["persona"]))
    return {
        "current_persona": persona_name,
        "token_limit": current_limit,
        "remaining": current_remaining,
        "usage_percentage": current_percentage,
        "total_all_personas": total_all,
        "per_persona": per_persona,
    }


@router.post("/reset")
async def reset_usage(
    body: UsageResetBody,
    user_id: int = Depends(get_current_user),
):
    """Reset token usage for a persona (default: current persona)."""
    persona_name = _resolve_persona(user_id, body.persona)
    reset_token_usage(user_id, persona_name)
    record_web_action(user_id, "usage.reset", {"persona": persona_name})
    return {"ok": True, "persona": persona_name}


@router.put("/token-limit")
async def update_token_limit(
    body: TokenLimitBody,
    user_id: int = Depends(get_current_user),
):
    """Set token limit for a persona (default: current persona)."""
    persona_name = _resolve_persona(user_id, body.persona)
    set_token_limit(user_id, int(body.token_limit), persona_name)
    record_web_action(user_id, "usage.token_limit", {"persona": persona_name, "token_limit": int(body.token_limit)})
    return {"ok": True, "persona": persona_name, "token_limit": int(body.token_limit)}
