"""Cache module."""

from .manager import cache, CacheManager
from .sync import init_database, sync_to_database

# Container support
def get_cache():
    """Get cache instance (supports container-based access)."""
    from core.container import get_container
    container = get_container()
    if container.has("cache"):
        return container.get("cache")
    return cache

__all__ = [
    "cache",
    "CacheManager",
    "init_database",
    "sync_to_database",
    "get_cache",
]
