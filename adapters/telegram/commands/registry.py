"""Command registry: unified context, self-registering decorator, AST discovery.

A command handler has the signature ``async def(ctx: CommandContext) -> str``,
returning the reply text. The framework handles: ensure_user_state, argument
parsing, logging, and rich-text reply — so command bodies are pure logic.

Commands self-register via ``@command`` when their module is imported.
``discover()`` imports every module under this package that declares one, so
adding a command is just adding a file (no manual import list to maintain).
"""

from __future__ import annotations

import ast
import importlib
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Awaitable, Callable

from telegram import Update
from telegram.ext import ContextTypes

from domain.services.refresh import ensure_user_state

logger = logging.getLogger(__name__)

Handler = Callable[["CommandContext"], Awaitable[str]]


@dataclass
class CommandContext:
    """Everything a command handler needs, pre-resolved."""

    update: Update
    user_id: int
    chat_id: int
    message: object
    args: list[str] = field(default_factory=list)
    arg_text: str = ""
    log_ctx: str = ""

    @property
    def subcommand(self) -> str:
        """First arg lowercased, or '' — for ``/skill list``-style commands."""
        return (self.args[0].lower() if self.args else "").strip()


@dataclass(frozen=True)
class Command:
    name: str
    handler: Handler
    usage: str = ""
    help: str = ""
    refresh_state: bool = True  # run ensure_user_state before the handler

    @property
    def display_usage(self) -> str:
        return self.usage or self.name


_REGISTRY: dict[str, Command] = {}
_ORDER: list[str] = []


def command(name: str, *, usage: str = "", help: str = "", refresh_state: bool = True):
    """Register a command. Handler: ``async def(ctx) -> str``."""

    def decorate(handler: Handler) -> Handler:
        if name in _REGISTRY:
            _ORDER.remove(name)
        _REGISTRY[name] = Command(name=name, handler=handler, usage=usage, help=help, refresh_state=refresh_state)
        _ORDER.append(name)
        return handler

    return decorate


def all_commands() -> list[Command]:
    return [_REGISTRY[name] for name in _ORDER]


def get_command(name: str) -> Command | None:
    return _REGISTRY.get(name)


def _declares_command(path: Path) -> bool:
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    except (OSError, SyntaxError):
        return False
    for stmt in tree.body:
        if not isinstance(stmt, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        for dec in stmt.decorator_list:
            target = dec.func if isinstance(dec, ast.Call) else dec
            if isinstance(target, ast.Name) and target.id == "command":
                return True
    return False


def discover() -> list[str]:
    """Import every command module under this package (side-effect registers)."""
    package_dir = Path(__file__).resolve().parent
    imported: list[str] = []
    for path in sorted(package_dir.glob("*.py")):
        if path.name in {"__init__.py", "registry.py"}:
            continue
        if not _declares_command(path):
            continue
        module = f"adapters.telegram.commands.{path.stem}"
        try:
            importlib.import_module(module)
            imported.append(module)
        except Exception as exc:
            logger.warning("Could not import command module %s: %s", module, exc)
    return imported


async def _invoke(cmd: Command, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    from adapters.telegram.handlers.common import get_log_context
    from adapters.telegram.rich_text import reply_rich_text

    user_id = update.effective_user.id
    chat_id = update.effective_chat.id if update.effective_chat else user_id
    args = list(context.args or [])
    log_ctx = get_log_context(update)
    logger.info("%s /%s %s", log_ctx, cmd.name, " ".join(args))
    if cmd.refresh_state:
        await ensure_user_state(user_id)
    ctx = CommandContext(
        update=update,
        user_id=user_id,
        chat_id=chat_id,
        message=update.effective_message,
        args=args,
        arg_text=" ".join(args),
        log_ctx=log_ctx,
    )
    reply = await cmd.handler(ctx)
    if reply:
        await reply_rich_text(update.effective_message, reply)


def make_handler(cmd: Command):
    """Wrap a Command into a python-telegram-bot handler ``(update, context)``."""

    async def handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        await _invoke(cmd, update, context)

    return handler
