"""Usage / token stats API routes."""

from fastapi import APIRouter, Depends

from cache import cache
from services import (
    get_token_limit,
    get_total_tokens_all_personas,
    get_remaining_tokens,
    get_usage_percentage,
)
from web.auth import get_current_user

router = APIRouter(prefix="/api/usage", tags=["usage"])


@router.get("")
async def get_usage(user_id: int = Depends(get_current_user)):
    """Return token usage statistics."""
    token_limit = get_token_limit(user_id)
    total = get_total_tokens_all_personas(user_id)
    remaining = get_remaining_tokens(user_id)
    percentage = get_usage_percentage(user_id)

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
        })

    return {
        "token_limit": token_limit,
        "total_all_personas": total,
        "remaining": remaining,
        "usage_percentage": percentage,
        "per_persona": per_persona,
    }
