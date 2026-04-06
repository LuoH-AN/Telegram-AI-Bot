"""Human-friendly tool status text helpers."""

from __future__ import annotations

import json
from typing import Any


_HIDDEN_ARG_KEYS = {"content_b64", "text"}


def build_tool_status_text(event: dict[str, Any]) -> str | None:
    event_type = str(event.get("type") or "").strip()
    tool_name = str(event.get("tool_name") or "tool").strip() or "tool"
    if event_type == "tool_batch_start":
        count = int(event.get("count") or 0)
        return f"Preparing {count} tool call(s)..."
    if event_type == "tool_start":
        detail = _tool_detail_preview(tool_name, event.get("arguments"))
        return f"Running {tool_name}: {detail}" if detail else f"Running {tool_name}..."
    if event_type == "tool_progress":
        message = str(event.get("message") or "").strip()
        if not message:
            return None
        if str(event.get("stage") or "").strip() == "start":
            return f"Running {tool_name}: {message}" if tool_name else message
        return f"{tool_name}: {message}" if tool_name else message
    if event_type == "tool_error":
        return f"{tool_name} failed. Retrying next step..."
    if event_type == "tool_end":
        ok = bool(event.get("ok", True))
        elapsed_ms = int(event.get("elapsed_ms") or 0)
        cost = f"{elapsed_ms / 1000:.1f}s" if elapsed_ms > 0 else "done"
        return f"{tool_name} {'finished' if ok else 'failed'} ({cost})."
    if event_type == "tool_batch_end":
        return "Tool execution completed. Generating final response..."
    return None


def _tool_detail_preview(tool_name: str, arguments: Any) -> str:
    args = arguments if isinstance(arguments, dict) else {}
    if tool_name == "terminal":
        return _terminal_preview(args)
    if tool_name == "hf_sync":
        return _hf_sync_preview(args)
    return _json_preview(args)


def _terminal_preview(args: dict[str, Any]) -> str:
    if args.get("bg_list"):
        return "bg_list=true"
    if args.get("bg_check") is not None:
        return f"bg_check={args.get('bg_check')}"
    command = str(args.get("command") or "").strip()
    if not command:
        return ""
    background = bool(args.get("background"))
    cwd = str(args.get("cwd") or "").strip()
    suffix = " (background)" if background else ""
    if cwd:
        suffix += f" [cwd={_trim(cwd, 50)}]"
    return _trim(command, 120) + suffix


def _hf_sync_preview(args: dict[str, Any]) -> str:
    action = str(args.get("action") or "").strip()
    if action in {"copy", "move"}:
        src = str(args.get("src_key") or args.get("source") or args.get("src") or "").strip()
        dst = str(args.get("dst_key") or args.get("target") or args.get("dst") or "").strip()
        text = f"{action} {src} -> {dst}".strip()
        return _trim(text, 120)
    key = str(args.get("key") or args.get("name") or args.get("path") or args.get("prefix") or "").strip()
    if action and key:
        return _trim(f"{action} {key}", 120)
    if action:
        return _trim(action, 120)
    return _json_preview(args)


def _json_preview(args: dict[str, Any]) -> str:
    if not args:
        return ""
    sanitized: dict[str, Any] = {}
    for key, value in args.items():
        if key in _HIDDEN_ARG_KEYS:
            text = str(value or "")
            sanitized[key] = f"<omitted:{len(text)} chars>"
            continue
        if isinstance(value, str):
            sanitized[key] = _trim(value, 80)
        else:
            sanitized[key] = value
    try:
        raw = json.dumps(sanitized, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
    except Exception:
        raw = str(sanitized)
    return _trim(raw, 160)


def _trim(text: str, max_len: int) -> str:
    value = str(text or "").strip()
    if len(value) <= max_len:
        return value
    return value[: max(0, max_len - 3)] + "..."

