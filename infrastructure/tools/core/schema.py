"""Derive OpenAI function schema from a handler signature and validate arguments."""

from __future__ import annotations

import inspect
import types
import typing
from typing import Annotated

_SCALARS = {str: "string", int: "integer", float: "number", bool: "boolean"}
_INJECTED = {"self", "ctx", "context"}


def _strip_optional(annotation):
    origin = typing.get_origin(annotation)
    if origin is typing.Union or origin is types.UnionType:
        args = [a for a in typing.get_args(annotation) if a is not type(None)]
        if len(args) == 1:
            return args[0]
    return annotation


def _unwrap(annotation):
    """Peel Optional/Union and Annotated layers -> (base_type, description).

    Handles nesting like Optional[Annotated[bool | None, "..."]] that
    typing.get_type_hints produces for params with a None default.
    """
    description = None
    base = annotation
    for _ in range(5):
        if typing.get_origin(base) is Annotated:
            metas = typing.get_args(base)
            base = metas[0]
            for meta in metas[1:]:
                if isinstance(meta, str) and description is None:
                    description = meta
            continue
        stripped = _strip_optional(base)
        if stripped is base:
            break
        base = stripped
    return base, description


def _type_info(annotation):
    """Return (json_type, enum, description) for an annotation."""
    base, description = _unwrap(annotation)
    if typing.get_origin(base) is typing.Literal:
        return "string", list(typing.get_args(base)), description
    if typing.get_origin(base) is list:
        return "array", None, description
    if base is list:
        return "array", None, description
    if typing.get_origin(base) is dict or base is dict:
        return "object", None, description
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
    parameters = {"type": "object", "properties": properties, "additionalProperties": False}
    if required:
        parameters["required"] = required
    return {"type": "function", "function": {"name": name, "description": description, "parameters": parameters}}


def _allows_none(annotation) -> bool:
    origin = typing.get_origin(annotation)
    return origin in {typing.Union, types.UnionType} and type(None) in typing.get_args(annotation)


def _coerce(value, annotation) -> tuple[object, str | None]:
    if annotation in {inspect.Parameter.empty, typing.Any}:
        return value, None
    if value is None:
        return (None, None) if _allows_none(annotation) else (value, "value may not be null")
    base, _ = _unwrap(annotation)
    if typing.get_origin(base) is typing.Literal:
        allowed = list(typing.get_args(base))
        return (value, None) if value in allowed else (value, f"value must be one of {allowed}")
    origin = typing.get_origin(base)
    if origin is list or base is list:
        if not isinstance(value, list):
            return value, "value must be an array"
        item_type = typing.get_args(base)
        if not item_type or item_type[0] is typing.Any:
            return value, None
        cleaned = []
        for index, item in enumerate(value):
            coerced, err = _coerce(item, item_type[0])
            if err:
                return value, f"item {index}: {err}"
            cleaned.append(coerced)
        return cleaned, None
    if origin is dict or base is dict:
        return (value, None) if isinstance(value, dict) else (value, "value must be an object")
    if base is str:
        return (value, None) if isinstance(value, str) else (value, "value must be a string")
    if base is int:
        if isinstance(value, bool):
            return value, "value must be an integer"
        if isinstance(value, int):
            return value, None
        if isinstance(value, str):
            try:
                return int(value), None
            except ValueError:
                pass
        return value, "value must be an integer"
    if base is float:
        if isinstance(value, bool):
            return value, "value must be a number"
        if isinstance(value, (int, float)):
            return float(value), None
        if isinstance(value, str):
            try:
                return float(value), None
            except ValueError:
                pass
        return value, "value must be a number"
    if base is bool:
        if isinstance(value, bool):
            return value, None
        if isinstance(value, str):
            lowered = value.strip().lower()
            if lowered in {"true", "1", "yes", "on"}:
                return True, None
            if lowered in {"false", "0", "no", "off"}:
                return False, None
        return value, "value must be a boolean"
    return value, None


def validate(func, args: dict) -> tuple[dict, str | None]:
    sig = inspect.signature(func)
    hints = _hints(func)
    allowed = {name for name in sig.parameters if name not in _INJECTED}
    unknown = sorted(set(args) - allowed)
    if unknown:
        return {}, f"unknown parameter(s): {', '.join(unknown)}"
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
