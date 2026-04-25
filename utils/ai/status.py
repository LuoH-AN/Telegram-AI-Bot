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
    if tool_name == "s3":
        return _s3_preview(args)
    if tool_name == "sosearch":
        return _sosearch_preview(args)
    if tool_name == "scrapling":
        return _scrapling_preview(args)
    return _json_preview(args)


def _terminal_preview(args: dict[str, Any]) -> str:
    action = str(args.get("action") or "").strip().lower()
    if action == "bg_list":
        return "action=bg_list"
    if action == "bg_check":
        return f"action=bg_check bg_pid={args.get('bg_pid')}"
    if action == "exec":
        command = str(args.get("command") or "").strip()
        cwd = str(args.get("cwd") or "").strip()
        suffix = ""
        if bool(args.get("background")):
            suffix += " (background)"
        if cwd:
            suffix += f" [cwd={_trim(cwd, 50)}]"
        return _trim(command, 120) + suffix if command else "action=exec"

    if args.get("bg_list"):
        return "bg_list=true"
    if args.get("bg_pid") is not None:
        return f"bg_pid={args.get('bg_pid')}"
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


def _s3_preview(args: dict[str, Any]) -> str:
    action = str(args.get("action") or "").strip()
    bucket = str(args.get("bucket") or "").strip()
    key = str(args.get("key") or "").strip()
    if action == "get_url":
        return f"get_url {bucket}/{key}" if bucket and key else "get_url"
    if action in {"copy_object", "move_object"}:
        src = f"{args.get('src_bucket', '')}/{args.get('src_key', '')}"
        dst = f"{args.get('dst_bucket', '')}/{args.get('dst_key', '')}"
        return f"{action} {src} -> {dst}"
    if action == "put_object" and key:
        size_hint = ""
        if args.get("text"):
            size_hint = f" ({len(str(args['text']))} chars)"
        elif args.get("content_b64"):
            size_hint = " (base64)"
        return f"put {bucket}/{key}{size_hint}" if bucket else f"put {key}{size_hint}"
    if action and bucket:
        return f"{action} {bucket}/{key}" if key else f"{action} {bucket}"
    if action:
        return action
    return _json_preview(args)


def _sosearch_preview(args: dict[str, Any]) -> str:
    action = str(args.get("action") or "").strip().lower()
    query = str(args.get("query") or "").strip()
    if action == "search" and query:
        return _trim(f"search {query}", 120)
    if action:
        return _trim(action, 120)
    return _json_preview(args)


def _scrapling_preview(args: dict[str, Any]) -> str:
    action = str(args.get("action") or "").strip().lower()
    if action == "fetch":
        url = str(args.get("url") or "").strip()
        mode = str(args.get("mode") or "auto").strip().lower()
        if url:
            return _trim(f"fetch[{mode}] {url}", 120)
        return _trim(f"fetch[{mode}]", 120)
    if action == "parse_html":
        selector = str(args.get("selector") or "").strip()
        return _trim(f"parse_html {selector}" if selector else "parse_html", 120)
    if action.startswith("cookie_"):
        site = str(args.get("site") or "").strip()
        return _trim(f"{action} {site}".strip(), 120)
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
