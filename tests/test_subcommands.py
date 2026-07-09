"""Tests for the Subcommands dispatch framework."""

from __future__ import annotations

import asyncio

import pytest

from shared.utils.subcommands import Subcommands, SubContext


def _make_registry() -> Subcommands:
    reg = Subcommands("test", help_intro="intro")

    @reg.subcommand("list", "ls", "show", help="list items", default=True)
    async def _list(subctx: SubContext) -> str:
        return "LIST"

    @reg.subcommand("add", usage="add <name>", help="add one")
    def _add(subctx: SubContext) -> str:
        return f"ADD:{subctx.rest_text}"

    return reg


def _run(coro):
    return asyncio.run(coro)


def test_no_args_invokes_default():
    reg = _make_registry()
    out = _run(reg.dispatch([], user_id=1, command_prefix="/"))
    assert out == "LIST"


def test_explicit_verb():
    reg = _make_registry()
    out = _run(reg.dispatch(["add", "foo", "bar"], user_id=1, command_prefix="/"))
    assert out == "ADD:foo bar"


def test_alias_resolves():
    reg = _make_registry()
    assert _run(reg.dispatch(["ls"], user_id=1, command_prefix="/")) == "LIST"
    assert _run(reg.dispatch(["show"], user_id=1, command_prefix="/")) == "LIST"


def test_help_verb_renders_all():
    reg = _make_registry()
    out = _run(reg.dispatch(["help"], user_id=1, command_prefix="/"))
    assert "add" in out and "list" in out
    assert "Subcommands" in out


def test_question_mark_is_help():
    reg = _make_registry()
    assert "Subcommands" in _run(reg.dispatch(["?"], user_id=1, command_prefix="/"))


def test_unknown_verb_is_error_not_default():
    reg = _make_registry()
    out = _run(reg.dispatch(["bogus"], user_id=1, command_prefix="/"))
    assert out.startswith("❌")
    assert "bogus" in out


def test_verb_is_case_insensitive():
    reg = _make_registry()
    assert _run(reg.dispatch(["LIST"], user_id=1, command_prefix="/")) == "LIST"


def test_rest_and_rest_text():
    subctx = SubContext(user_id=1, command_prefix="/", args=["add", "a", "b"])
    assert subctx.rest == ["a", "b"]
    assert subctx.rest_text == "a b"


def test_default_absent_falls_back_to_help():
    reg = Subcommands("n")

    @reg.subcommand("x")
    def _x(subctx: SubContext) -> str:
        return "X"

    out = _run(reg.dispatch([], user_id=1, command_prefix="/"))
    assert "Subcommands" in out
