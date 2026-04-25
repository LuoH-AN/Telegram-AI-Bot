"""Model listing helpers for OpenAI client."""

from __future__ import annotations

import logging
import time

logger = logging.getLogger(__name__)


def list_models_with_logging(*, client, ctx_prefix: str, request_id: str, request_start: float) -> list[str]:
    try:
        models = client.models.list()
        model_ids = sorted([model.id for model in models.data])
        logger.info(
            "%sAI response done req=%s endpoint=models.list count=%d latency_ms=%d",
            ctx_prefix,
            request_id,
            len(model_ids),
            int((time.monotonic() - request_start) * 1000),
        )
        return model_ids
    except Exception:
        logger.exception(
            "%sAI request failed req=%s endpoint=models.list latency_ms=%d",
            ctx_prefix,
            request_id,
            int((time.monotonic() - request_start) * 1000),
        )
        return []
