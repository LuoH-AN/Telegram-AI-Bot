"""Shared runtime helpers used by OneBot / WeChat platforms."""

from .dispatch import make_bounded_dispatcher

__all__ = ["make_bounded_dispatcher"]
