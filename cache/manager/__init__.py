"""In-memory cache manager."""

from .cache import CacheManager

cache = CacheManager()

__all__ = ["CacheManager", "cache"]
