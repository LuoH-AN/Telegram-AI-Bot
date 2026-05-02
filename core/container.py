"""Dependency injection container for application services."""

from __future__ import annotations

import threading
from typing import Any, Callable, TypeVar

T = TypeVar("T")

Provider = Callable[["Container"], T]


class Container:
    """Thread-safe dependency injection container.

    Supports both singleton instances and factory providers.
    """

    def __init__(self) -> None:
        self._instances: dict[str, Any] = {}
        self._providers: dict[str, Provider] = {}
        self._lock = threading.RLock()

    def register_instance(self, name: str, instance: Any) -> None:
        """Register an existing instance as a singleton."""
        with self._lock:
            self._instances[name] = instance

    def register_provider(self, name: str, provider: Provider) -> None:
        """Register a factory provider.

        The provider will be called once on first access, then cached.
        """
        with self._lock:
            self._providers[name] = provider

    def get(self, name: str) -> Any:
        """Get a service by name.

        Creates instance from provider if not already cached.
        Raises KeyError if service not registered.
        """
        with self._lock:
            if name in self._instances:
                return self._instances[name]
            if name in self._providers:
                instance = self._providers[name](self)
                self._instances[name] = instance
                return instance
            raise KeyError(f"Service '{name}' not registered")

    def has(self, name: str) -> bool:
        """Check if a service is registered."""
        with self._lock:
            return name in self._instances or name in self._providers

    def clear(self) -> None:
        """Clear all registered services (for testing)."""
        with self._lock:
            self._instances.clear()
            self._providers.clear()


# Global container - the only global singleton allowed
_container: Container | None = None
_container_lock = threading.Lock()


def get_container() -> Container:
    """Get the global container instance.

    Creates container on first call.
    """
    global _container
    if _container is None:
        with _container_lock:
            if _container is None:
                _container = Container()
    return _container


def init_container() -> Container:
    """Initialize and return a new container.

    Replaces any existing container.
    """
    global _container
    with _container_lock:
        _container = Container()
    return _container


def reset_container() -> None:
    """Reset the container (for testing)."""
    global _container
    with _container_lock:
        _container = None
