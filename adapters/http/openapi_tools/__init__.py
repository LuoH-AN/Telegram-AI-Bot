"""OpenAPI tool server exposing internal plugins to OpenWebUI."""

from .app import build_app

__all__ = ["build_app"]
