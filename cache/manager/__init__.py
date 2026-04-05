"""In-memory cache manager."""

from .core import CacheManager

cache = CacheManager()

__all__ = ["CacheManager", "cache"]
