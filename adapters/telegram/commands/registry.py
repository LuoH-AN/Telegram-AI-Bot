"""Command registry — single source of truth for Telegram commands.

Each command self-registers via the ``@command`` decorator when its module is
imported (``adapters.telegram.commands`` imports them all at package load).
``app_builder`` builds ``CommandHandler``s from this registry and ``/help``
renders its command list from it, so adding a command is a single change: write
the handler with the decorator.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Command:
    name: str
    usage: str
    help: str
    handler: object


_REGISTRY: list[Command] = []


def command(name: str, *, usage: str = "", help: str = ""):
    def decorate(handler):
        _REGISTRY.append(Command(name=name, usage=usage or name, help=help, handler=handler))
        return handler

    return decorate


def all_commands() -> list[Command]:
    return list(_REGISTRY)
