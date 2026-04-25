"""AI client construction for cron/title tasks."""

from __future__ import annotations

import logging

from utils.provider import resolve_provider_model

logger = logging.getLogger(__name__)


def _create_task_client(user_id: int, model_spec: str, settings: dict):
    from ai import get_ai_client
    from ai.openai import create_openai_client

    api_key = settings["api_key"]
    base_url = settings["base_url"]
    model = settings.get("model", "gpt-4o")

    if model_spec:
        try:
            api_key, base_url, model = resolve_provider_model(
                model_spec,
                settings.get("api_presets", {}),
                api_key,
                base_url,
                model,
            )
        except ValueError:
            logger.warning("[user=%d] provider not found in presets: %s", user_id, model_spec)
            return get_ai_client(user_id), model

        client = create_openai_client(
            api_key=api_key,
            base_url=base_url,
            log_context=f"[user={user_id}]",
        )
        return client, model

    return get_ai_client(user_id), model
