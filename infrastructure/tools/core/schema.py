"""Derive OpenAI function schema from a handler signature and validate arguments."""

from __future__ import annotations

import inspect
import typing
from typing import Annotated

_SCALARS = {str: "string", int: "integer", float: "number", bool: "boolean"}
_INJECTED = {"self", "ctx", "context"}


def _strip_optional(annotation):
    if typing.get_origin(annotation) is typing.Union:
        args = [a for a in typing.get_args(annotation) if a is not type(None)]
        if len(args) == 1:
            return args[0]
    return annotation


def _type_info(annotation):
    """Return (json_type, enum, description) for an annotation."""
    description = None
    if typing.get_origin(annotation) is Annotated:
        metas = typing.get_args(annotation)
        annotation = metas[0]
        for meta in metas[1:]:
            if isinstance(meta, str):
                description = meta
    base = _strip_optional(annotation)
    if typing.get_origin(base) is typing.Literal:
        return "string", list(typing.get_args(base)), description
    if typing.get_origin(base) is list:
        return "array", None, description
    return _SCALARS.get(base), None, description


def _hints(func) -> dict:
    try:
        return typing.get_type_hints(func, include_extras=True)
    except Exception:
        return {}


def build_schema(func, *, name: str, description: str) -> dict:
    sig = inspect.signature(func)
    hints = _hints(func)
    properties: dict = {}
    required: list[str] = []
    for pname, param in sig.parameters.items():
        if pname in _INJECTED:
            continue
        annotation = hints.get(pname, param.annotation)
        json_type, enum, desc = _type_info(annotation) if annotation is not inspect.Parameter.empty else (None, None, None)
        schema: dict = {}
        if json_type:
            schema["type"] = json_type
        if enum is not None:
            schema["enum"] = enum
        if desc:
            schema["description"] = desc
        properties[pname] = schema
        if param.default is inspect.Parameter.empty and annotation is not inspect.Parameter.empty:
            required.append(pname)
    parameters = {"type": "object", "properties": properties}
    if required:
        parameters["required"] = required
    return {"type": "function", "function": {"name": name, "description": description, "parameters": parameters}}


def _coerce(value, annotation) -> tuple[object, str | None]:
    base = annotation
    if typing.get_origin(base) is Annotated:
        base = typing.get_args(base)[0]
    base = _strip_optional(base)
    if typing.get_origin(base) is typing.Literal:
        allowed = list(typing.get_args(base))
        return (value, None) if value in allowed else (value, f"value must be one of {allowed}")
    if base is int and isinstance(value, str):
        try:
            return int(value), None
        except ValueError:
            return value, None
    if base is float and isinstance(value, str):
        try:
            return float(value), None
        except ValueError:
            return value, None
    if base is bool and isinstance(value, str):
        return value.lower() in ("true", "1", "yes"), None
    return value, None


def validate(func, args: dict) -> tuple[dict, str | None]:
    sig = inspect.signature(func)
    hints = _hints(func)
    clean: dict = {}
    for pname, param in sig.parameters.items():
        if pname in _INJECTED:
            continue
        if pname not in args:
            if param.default is inspect.Parameter.empty:
                return clean, f"missing required parameter: {pname}"
            continue
        value, err = _coerce(args[pname], hints.get(pname, param.annotation))
        if err:
            return clean, f"parameter '{pname}': {err}"
        clean[pname] = value
    return clean, None
