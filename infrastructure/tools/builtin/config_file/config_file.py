"""config_file tool — inspect/read/write/delete repo config files and SKILL.md manifests.

Split out of the old project_config god-tool (file half). Writing a valid
runtime/plugins/<name>/SKILL.md hot-loads and registers it for the user.
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Annotated, Any, Literal

from infrastructure.tools.core import ToolContext, ToolResult, tool

CONFIG_FILE_INSTRUCTION = (
    "\nconfig_file usage (admin toolset):\n"
    "- Use it instead of terminal for reading/changing repo config files and prompt-only agent plugins.\n"
    "- action=inspect lists config files + known env keys; get/set/delete read/write/remove.\n"
    "- To create an external prompt plugin, write the full markdown with action='set', format_hint='text', no key.\n"
    "- External plugins live at `runtime/plugins/<name>/SKILL.md` and need frontmatter: name, version, description.\n"
    "- Writing a valid external SKILL.md auto hot-loads and registers it so /skill list shows it.\n"
    "- Third-party CLI skill installers do not register this agent's plugins; run the CLI via terminal, then write SKILL.md here.\n"
)


def _run_file(action: str, path_raw: str, key: str, value: Any, format_hint: str, user_id: int) -> ToolResult:
    from infrastructure.tools.builtin.config_file.files import detect_format, discover_config_files, discover_env_keys, ensure_supported_config_target, resolve_config_path
    from infrastructure.tools.builtin.config_file.formats import delete_value, dump_data, get_value, load_data, render_value, set_value
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
        note = unregister_external_skill_manifest(user_id, path)
        path.unlink()
        return ToolResult.text(f"Deleted file: {path.name}.{note}")

    data = load_data(path, file_format)
    if action == "get":
        return ToolResult.text(render_value(get_value(data, file_format, key or None)))
    if action == "set":
        updated = set_value(data, file_format, key or None, value)
        dump_data(path, file_format, updated)
        note = register_external_skill_manifest(user_id, path)
        return ToolResult.text(f"Updated {path.name} ({file_format}).{note}")
    if action == "delete":
        if not delete_value(data, file_format, key or None):
            return ToolResult.text("Nothing deleted.")
        if path.exists():
            dump_data(path, file_format, data)
        return ToolResult.text(f"Deleted value from {path.name}.")
    return ToolResult.error("invalid_action", "Use one of: inspect, get, set, delete.")


@tool(toolset="admin", skill="project_config", instruction=CONFIG_FILE_INSTRUCTION, description="Inspect and modify repository config files and runtime/plugins/<name>/SKILL.md prompt-only manifests. Writing a valid SKILL.md hot-loads and registers it for the current user.")
async def config_file(
    ctx: ToolContext,
    action: Literal["inspect", "get", "set", "delete"],
    path: Annotated[str, "Repository-relative config file or runtime/plugins/<name>/SKILL.md."] = "",
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
