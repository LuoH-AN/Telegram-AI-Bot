"""Usage / token stats API routes."""

from fastapi import APIRouter, Depends

from cache import cache
from services import (
    get_token_limit,
    get_total_tokens_all_personas,
    get_remaining_tokens,
    get_usage_percentage,
    get_current_persona_name,
)
from web.auth import get_current_user

router = APIRouter(prefix="/api/usage", tags=["usage"])


@router.get("")
async def get_usage(user_id: int = Depends(get_current_user)):
    """Return token usage statistics."""
    persona_name = get_current_persona_name(user_id)
    total_all = get_total_tokens_all_personas(user_id)

    # Current persona stats
    current_limit = get_token_limit(user_id, persona_name)
    current_remaining = get_remaining_tokens(user_id, persona_name)
    current_percentage = get_usage_percentage(user_id, persona_name)

    # Per-persona breakdown
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

    return {
        "current_persona": persona_name,
        "token_limit": current_limit,
        "remaining": current_remaining,
        "usage_percentage": current_percentage,
        "total_all_personas": total_all,
        "per_persona": per_persona,
    }
