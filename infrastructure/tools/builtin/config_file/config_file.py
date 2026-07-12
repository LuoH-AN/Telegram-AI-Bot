"""config_file tool — inspect and edit ordinary repository config files."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Annotated, Any, Literal
from urllib.parse import urlparse

from infrastructure.tools.core import ToolContext, ToolResult, tool

CONFIG_FILE_INSTRUCTION = (
    "\nconfig_file usage (admin toolset):\n"
    "- Use it instead of terminal for reading/changing ordinary repository config files.\n"
    "- action=inspect lists config files + known env keys; get/set/delete read/write/remove.\n"
    "- Skill installation and MCP lifecycle are managed by their own interfaces, not by special file paths here.\n"
)

_SENSITIVE_PARTS = (
    "api_key", "token", "secret", "password", "credential", "private_key",
    "database_url", "connection_string", "authorization", "env_text", "env_content",
)


def _redact(value: Any, key: str = "") -> Any:
    if any(part in key.lower() for part in _SENSITIVE_PARTS):
        return "<redacted>" if value not in (None, "") else value
    if isinstance(value, dict):
        return {item_key: _redact(item_value, str(item_key)) for item_key, item_value in value.items()}
    if isinstance(value, list):
        return [_redact(item) for item in value]
    if isinstance(value, str) and "://" in value:
        parsed = urlparse(value)
        if parsed.username or parsed.password:
            return "<redacted>"
    return value


def _run_file(action: str, path_raw: str, key: str, value: Any, format_hint: str) -> ToolResult:
    from infrastructure.tools.builtin.config_file.files import detect_format, discover_config_files, discover_env_keys, ensure_supported_config_target, resolve_config_path
    from infrastructure.tools.builtin.config_file.formats import delete_env_key, delete_value, dump_data, get_value, load_data, render_value, set_env_key, set_value

    if action == "inspect":
        files = discover_config_files()
        keys = discover_env_keys()
        body = "Config files:\n" + ("\n".join(f"- {f}" for f in files[:120]) or "(none found)")
        body += "\n\nKnown env keys:\n" + ("\n".join(f"- {k}" for k in keys[:200]) or "(none found)")
        return ToolResult.text(body)

    path = resolve_config_path(path_raw, must_exist=action == "get")
    file_format = detect_format(path, format_hint)
    ensure_supported_config_target(path, file_format)

    if action == "delete" and not key and path.exists():
        return ToolResult.error("whole_file_delete_denied", "whole-file deletion is not supported")

    data = load_data(path, file_format)
    if action == "get":
        selected = get_value(data, file_format, key or None)
        return ToolResult.text(render_value(_redact(selected, key)))
    if action == "set":
        if file_format == "env":
            if not key:
                return ToolResult.error("env_key_required", "set on .env requires a specific key so comments and formatting are preserved")
            set_env_key(path, key, value)
            return ToolResult.text(f"Updated {path.name} key {key}.")
        updated = set_value(data, file_format, key or None, value)
        dump_data(path, file_format, updated)
        return ToolResult.text(f"Updated {path.name} ({file_format}).")
    if action == "delete":
        if file_format == "env":
            if not key:
                return ToolResult.error("env_key_required", "delete on .env requires a specific key")
            deleted = delete_env_key(path, key)
            return ToolResult.text(f"Deleted {key} from {path.name}." if deleted else "Nothing deleted.")
        if not delete_value(data, file_format, key or None):
            return ToolResult.text("Nothing deleted.")
        if path.exists():
            dump_data(path, file_format, data)
        return ToolResult.text(f"Deleted value from {path.name}.")
    return ToolResult.error("invalid_action", "Use one of: inspect, get, set, delete.")


@tool(toolset="admin", skill="project_config", side_effects=True, instruction=CONFIG_FILE_INSTRUCTION, description="Inspect and modify supported repository config files. Secret values are redacted and whole-file deletion is denied.")
async def config_file(
    ctx: ToolContext,
    action: Literal["inspect", "get", "set", "delete"],
    path: Annotated[str, "Repository config path."] = "",
    key: Annotated[str, "Key path for structured configs. SECTION.key for INI."] = "",
    value: Annotated[Any, "Value to set."] = None,
    format_hint: Literal["auto", "env", "json", "ini", "text"] = "auto",
) -> ToolResult:
    try:
        return await asyncio.to_thread(_run_file, action, (path or "").strip(), (key or "").strip(), value, format_hint)
    except (ValueError, FileNotFoundError) as exc:
        return ToolResult.error("bad_request", str(exc))
    except Exception as exc:
        return ToolResult.error("operation_failed", f"config_file failed: {exc}")
