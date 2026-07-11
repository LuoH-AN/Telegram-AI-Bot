"""config_file tool — inspect/read/write/delete repo config files and SKILL.md manifests.

Split out of the old project_config god-tool (file half). Writing a valid
runtime/plugins/<name>/SKILL.md hot-loads and registers it for the user.
"""

from __future__ import annotations

import asyncio
import json
import tempfile
from pathlib import Path
from typing import Annotated, Any, Literal
from urllib.parse import urlparse

from infrastructure.tools.core import ToolContext, ToolResult, tool

CONFIG_FILE_INSTRUCTION = (
    "\nconfig_file usage (admin toolset):\n"
    "- Use it instead of terminal for reading/changing repo config files and prompt-only agent plugins.\n"
    "- action=inspect lists config files + known env keys; get/set/delete read/write/remove.\n"
    "- To create an external prompt plugin, write the full markdown with action='set', format_hint='text', no key.\n"
    "- External plugins live at `/data/plugins/<name>/SKILL.md` and need frontmatter: name, version, description.\n"
    "- Writing a valid external SKILL.md auto hot-loads and registers it so /skill list shows it.\n"
    "- Third-party CLI skill installers do not register this agent's plugins; run the CLI via terminal, then write SKILL.md here.\n"
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


def _reload_mcp_if_needed(path: Path) -> str:
    from infrastructure.tools.mcp.config import DEFAULT_CONFIG_PATH

    if path.resolve() != DEFAULT_CONFIG_PATH.expanduser().resolve():
        return ""
    from infrastructure.tools.mcp.registry import reload_mcp

    try:
        outcome = reload_mcp()
    except Exception as exc:
        return f" MCP config saved, but runtime reload failed: {exc}."
    failures = outcome["failures"]
    note = f" MCP reloaded: {outcome['registered_tools']} tool(s) from {outcome['servers']} server(s)."
    if failures:
        note += " Unreachable: " + ", ".join(sorted(failures)) + "."
    return note


def _run_file(action: str, path_raw: str, key: str, value: Any, format_hint: str, user_id: int) -> ToolResult:
    from infrastructure.tools.builtin.config_file.files import detect_format, discover_config_files, discover_env_keys, ensure_supported_config_target, is_external_skill_manifest, resolve_config_path
    from infrastructure.tools.builtin.config_file.formats import delete_env_key, delete_value, dump_data, get_value, load_data, render_value, set_env_key, set_value
    from infrastructure.tools.skills.agent_plugins import register_external_skill_manifest, unregister_external_skill_manifest

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
        if not is_external_skill_manifest(path):
            return ToolResult.error("whole_file_delete_denied", "whole-file deletion is only supported for managed SKILL.md manifests")
        note = unregister_external_skill_manifest(user_id, path)
        path.unlink()
        return ToolResult.text(f"Deleted file: {path.name}.{note}")

    data = load_data(path, file_format)
    if action == "get":
        selected = get_value(data, file_format, key or None)
        return ToolResult.text(render_value(_redact(selected, key)))
    if action == "set":
        if file_format == "env":
            if not key:
                return ToolResult.error("env_key_required", "set on .env requires a specific key so comments and formatting are preserved")
            set_env_key(path, key, value)
            return ToolResult.text(f"Updated {path.name} key {key}." + _reload_mcp_if_needed(path))
        if is_external_skill_manifest(path):
            from infrastructure.tools.skills.manifest import load_manifest

            if key or not isinstance(value, str):
                return ToolResult.error("bad_manifest", "SKILL.md must be written as complete text with no key")
            path.parent.mkdir(parents=True, exist_ok=True)
            with tempfile.NamedTemporaryFile("w", encoding="utf-8", suffix=".md", dir=path.parent, delete=False) as handle:
                handle.write(value)
                validation_path = Path(handle.name)
            try:
                manifest = load_manifest(validation_path, is_builtin=False)
            finally:
                validation_path.unlink(missing_ok=True)
            if not manifest:
                return ToolResult.error("bad_manifest", "SKILL.md frontmatter is invalid")
            if manifest.name != path.parent.name:
                return ToolResult.error("bad_manifest", "SKILL.md name must match its parent directory")
        updated = set_value(data, file_format, key or None, value)
        from infrastructure.tools.mcp.config import DEFAULT_CONFIG_PATH, validate_servers_payload

        if path.resolve() == DEFAULT_CONFIG_PATH.expanduser().resolve():
            errors = validate_servers_payload(updated)
            if errors:
                return ToolResult.error("invalid_mcp_config", "; ".join(errors))
        existed_before = path.exists()
        dump_data(path, file_format, updated)
        try:
            note = register_external_skill_manifest(user_id, path)
        except Exception:
            if existed_before:
                dump_data(path, file_format, data)
            else:
                path.unlink(missing_ok=True)
            raise
        note += _reload_mcp_if_needed(path)
        return ToolResult.text(f"Updated {path.name} ({file_format}).{note}")
    if action == "delete":
        if file_format == "env":
            if not key:
                return ToolResult.error("env_key_required", "delete on .env requires a specific key")
            deleted = delete_env_key(path, key)
            note = _reload_mcp_if_needed(path) if deleted else ""
            return ToolResult.text((f"Deleted {key} from {path.name}." if deleted else "Nothing deleted.") + note)
        if not delete_value(data, file_format, key or None):
            return ToolResult.text("Nothing deleted.")
        from infrastructure.tools.mcp.config import DEFAULT_CONFIG_PATH, validate_servers_payload

        if path.resolve() == DEFAULT_CONFIG_PATH.expanduser().resolve():
            errors = validate_servers_payload(data)
            if errors:
                return ToolResult.error("invalid_mcp_config", "; ".join(errors))
        if path.exists():
            dump_data(path, file_format, data)
        return ToolResult.text(f"Deleted value from {path.name}." + _reload_mcp_if_needed(path))
    return ToolResult.error("invalid_action", "Use one of: inspect, get, set, delete.")


@tool(toolset="admin", skill="project_config", side_effects=True, instruction=CONFIG_FILE_INSTRUCTION, description="Inspect and modify supported repository config files and /data/plugins/<name>/SKILL.md manifests. Secret values are redacted and whole-file deletion is restricted.")
async def config_file(
    ctx: ToolContext,
    action: Literal["inspect", "get", "set", "delete"],
    path: Annotated[str, "Repository config path or /data/plugins/<name>/SKILL.md."] = "",
    key: Annotated[str, "Key path for structured configs. SECTION.key for INI."] = "",
    value: Annotated[Any, "Value to set."] = None,
    format_hint: Literal["auto", "env", "json", "ini", "text"] = "auto",
) -> ToolResult:
    try:
        return await asyncio.to_thread(_run_file, action, (path or "").strip(), (key or "").strip(), value, format_hint, ctx.user_id)
    except (ValueError, FileNotFoundError) as exc:
        return ToolResult.error("bad_request", str(exc))
    except Exception as exc:
        return ToolResult.error("operation_failed", f"config_file failed: {exc}")
