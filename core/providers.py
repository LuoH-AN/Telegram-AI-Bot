"""Service providers for dependency injection."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from core.container import Container


def provide_cache(container: "Container"):
    """Provide the CacheManager singleton."""
    from cache.manager import CacheManager
    return CacheManager()


def provide_embedding_client(container: "Container"):
    """Provide the embedding client."""
    from services.embedding import EmbeddingClient
    return EmbeddingClient()


def provide_plugin_registry(container: "Container"):
    """Provide the plugin registry."""
    from core.plugins.registry import PluginRegistry
    return PluginRegistry()


def register_providers(container: "Container") -> None:
    """Register all service providers with the container."""
    container.register_provider("cache", provide_cache)
    container.register_provider("embedding_client", provide_embedding_client)
    container.register_provider("plugin_registry", provide_plugin_registry)
