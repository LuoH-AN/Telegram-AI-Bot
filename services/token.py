"""Token usage tracking service."""

from cache import cache


def get_token_usage(user_id: int, persona_name: str = None) -> dict:
    """Get token usage for the current or specified persona."""
    return cache.get_token_usage(user_id, persona_name)


def add_token_usage(user_id: int, prompt_tokens: int, completion_tokens: int, persona_name: str = None) -> None:
    """Add token usage for the current or specified persona."""
    cache.add_token_usage(user_id, prompt_tokens, completion_tokens, persona_name)


def get_token_limit(user_id: int, persona_name: str = None) -> int:
    """Get token limit for the current or specified persona."""
    return cache.get_token_limit(user_id, persona_name)


def set_token_limit(user_id: int, limit: int, persona_name: str = None) -> None:
    """Set token limit for the current or specified persona."""
    cache.set_token_limit(user_id, limit, persona_name)


def reset_token_usage(user_id: int, persona_name: str = None) -> None:
    """Reset token usage counters for the current or specified persona."""
    cache.reset_token_usage(user_id, persona_name)


def get_total_tokens_all_personas(user_id: int) -> int:
    """Get total tokens across all personas."""
    return cache.get_total_tokens_all_personas(user_id)


def get_remaining_tokens(user_id: int, persona_name: str = None) -> int | None:
    """Get remaining tokens for the current persona, or None if no limit."""
    limit = cache.get_token_limit(user_id, persona_name)
    if limit == 0:
        return None
    usage = cache.get_token_usage(user_id, persona_name)
    return max(0, limit - usage.get("total_tokens", 0))


def get_usage_percentage(user_id: int, persona_name: str = None) -> float | None:
    """Get usage percentage for the current persona, or None if no limit."""
    limit = cache.get_token_limit(user_id, persona_name)
    if limit == 0:
        return None
    usage = cache.get_token_usage(user_id, persona_name)
    total = usage.get("total_tokens", 0)
    return min(100.0, (total / limit) * 100)
