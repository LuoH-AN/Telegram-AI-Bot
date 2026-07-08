"""Subcommand framework: unified default/help/unknown handling for management commands.

Mirrors the ``@command`` + ``CommandContext`` pattern in
``adapters/telegram/commands/registry.py``. A management command (``/chat``,
``/persona``, ``/skill`` ...) builds a ``Subcommands`` registry once and calls
``dispatch`` per request with a fresh ``SubContext``.

Normalization rules enforced everywhere:
- **no-arg** → the subcommand marked ``default`` (``list`` for management commands)
- **``<cmd> help``** → render every subcommand verb + one-line help
- **unknown verb** → error message + help, **never** a silent switch
- **aliases** → alternate verbs mapping to the same handler (back-compat)

Handlers may be sync or async; both are awaited transparently.
"""

from __future__ import annotations

import inspect
from dataclasses import dataclass, field
from typing import Awaitable, Callable

SubHandler = Callable[["SubContext"], Awaitable[str] | str]


@dataclass
class SubContext:
    """Per-request context handed to every subcommand handler."""

    user_id: int
    command_prefix: str
    args: list[str] = field(default_factory=list)  # full list; verb at index 0
    persona_name: str = ""

    @property
    def rest(self) -> list[str]:
        """Tokens after the verb (``args[1:]``)."""
        return self.args[1:]

    @property
    def rest_text(self) -> str:
        return " ".join(self.rest).strip()


@dataclass
class _SubSpec:
    verb: str
    aliases: tuple[str, ...]
    usage: str
    help: str


async def _invoke(handler: SubHandler, subctx: SubContext) -> str:
    result = handler(subctx)
    if inspect.isawaitable(result):
        result = await result
    return result


class Subcommands:
    """Declarative subcommand registry with unified dispatch behavior."""

    def __init__(self, name: str, *, help_intro: str = ""):
        self.name = name
        self.help_intro = help_intro
        self._specs: list[_SubSpec] = []
        self._handlers: dict[str, SubHandler] = {}
        self._default: SubHandler | None = None

    def subcommand(
        self,
        verb: str,
        *aliases: str,
        usage: str = "",
        help: str = "",
        default: bool = False,
    ):
        """Register a subcommand. Handler: ``(SubContext) -> str | await str``."""

        def decorate(handler: SubHandler) -> SubHandler:
            self._specs.append(_SubSpec(verb, aliases, usage or verb, help))
            self._handlers[verb] = handler
            for alias in aliases:
                self._handlers[alias] = handler
            if default:
                self._default = handler
            return handler

        return decorate

    async def dispatch(
        self,
        args: list[str],
        *,
        user_id: int,
        command_prefix: str,
        persona_name: str = "",
    ) -> str:
        subctx = SubContext(
            user_id=user_id,
            command_prefix=command_prefix,
            args=list(args),
            persona_name=persona_name,
        )
        if not args:
            if self._default is None:
                return self.help_text(command_prefix)
            return await _invoke(self._default, subctx)

        verb = args[0].lower().strip()
        if verb in ("help", "?"):
            return self.help_text(command_prefix)

        handler = self._handlers.get(verb)
        if handler is None:
            return self._unknown_text(verb, command_prefix)
        return await _invoke(handler, subctx)

    def help_text(self, command_prefix: str) -> str:
        lines: list[str] = []
        if self.help_intro:
            lines.append(f"{self.help_intro}\n")
        lines.append("**Subcommands:**")
        for spec in self._specs:
            names = "/".join((spec.verb, *spec.aliases))
            lines.append(f"• `{command_prefix}{self.name} {spec.usage}` — {spec.help}  (`{names}`)")
        lines.append(f"• `{command_prefix}{self.name} help` — show this help")
        return "\n".join(lines)

    def _unknown_text(self, verb: str, command_prefix: str) -> str:
        return f"❌ **Unknown subcommand:** `{verb}`.\n\n" + self.help_text(command_prefix)
