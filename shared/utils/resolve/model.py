"""Provider:model resolution utility.

Shared logic for resolving a ``"provider:model"`` specification against
a user's API presets, used by session title generation and cron task
execution.
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


def resolve_provider_model(
    model_spec: str,
    api_presets: dict,
    default_api_key: str,
    default_base_url: str,
    default_model: str,
) -> tuple[str, str, str]:
    """Resolve a ``"provider:model"`` string into concrete credentials.

    Returns ``(api_key, base_url, model)``.

    If *model_spec* contains ``":"``, the part before the colon is looked up
    (case-insensitively) in *api_presets*.  If the provider is not found a
    :class:`ValueError` is raised so the caller can decide how to handle it.

    If *model_spec* has no colon it is treated as a plain model name and the
    supplied defaults are returned unchanged except for the model.
    """
    if not model_spec:
        return default_api_key, default_base_url, default_model

    if ":" not in model_spec:
        return default_api_key, default_base_url, model_spec

    provider_name, model_name = model_spec.split(":", 1)
    preset = None
    for k, v in api_presets.items():
        if k.lower() == provider_name.lower():
            preset = v
            break

    if preset is None:
        raise ValueError(f"Provider '{provider_name}' not found in presets")

    return (
        preset["api_key"],
        preset["base_url"],
        model_name or preset.get("model", default_model),
    )
