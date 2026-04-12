"""AI tool for repository config inspection and edits."""

from __future__ import annotations

from .files import detect_format, discover_config_files, discover_env_keys, ensure_supported_config_target, resolve_config_path
from .formats import delete_value, dump_data, get_value, load_data, render_value, set_value
from ..core.base import BaseTool


class ProjectConfigTool(BaseTool):
    @property
    def name(self) -> str:
        return "project_config"

    def definitions(self) -> list[dict]:
        return [{"type": "function", "function": {"name": self.name, "description": "Inspect and modify repository config files such as .env, JSON, INI, and text-based config files inside the project.", "parameters": self._parameters()}}]

    def _parameters(self) -> dict:
        return {"type": "object", "properties": {"action": {"type": "string", "enum": ["inspect", "get", "set", "delete"]}, "path": {"type": "string", "description": "Repository-relative config file path."}, "key": {"type": "string", "description": "Nested key path for structured configs. Use SECTION.key for INI."}, "value": {"anyOf": [{"type": "string"}, {"type": "number"}, {"type": "integer"}, {"type": "boolean"}, {"type": "object"}, {"type": "array"}, {"type": "null"}]}, "format_hint": {"type": "string", "enum": ["auto", "env", "json", "ini", "text"]}}, "required": ["action"]}

    def get_instruction(self) -> str:
        return "\nProject config tool usage:\n- Prefer project_config over terminal when reading or changing repository configuration.\n- Use action='inspect' first to discover config files and known environment keys.\n- Use action='set' or 'delete' only for actual repository config files, not source code.\n"

    def execute(self, user_id: int, tool_name: str, arguments: dict) -> str:
        del user_id, tool_name
        action = str(arguments.get("action", "")).strip().lower()
        if action == "inspect":
            files = discover_config_files()
            keys = discover_env_keys()
            return f"Config files:\n" + ("\n".join(f"- {item}" for item in files[:120]) or "(none found)") + f"\n\nKnown env keys:\n" + ("\n".join(f"- {item}" for item in keys[:200]) or "(none found)")
        path = resolve_config_path(str(arguments.get("path", "")).strip(), must_exist=action == "get")
        file_format = detect_format(path, str(arguments.get("format_hint", "auto")))
        ensure_supported_config_target(path, file_format)
        if action == "delete" and not arguments.get("key") and path.exists():
            path.unlink()
            return f"Deleted config file: {path.name}"
        data = load_data(path, file_format)
        if action == "get":
            return render_value(get_value(data, file_format, str(arguments.get("key") or "").strip() or None))
        if action == "set":
            updated = set_value(data, file_format, str(arguments.get("key") or "").strip() or None, arguments.get("value"))
            dump_data(path, file_format, updated)
            return f"Updated {path.name} ({file_format})."
        if action == "delete":
            deleted = delete_value(data, file_format, str(arguments.get("key") or "").strip() or None)
            if not deleted:
                return "Nothing deleted."
            if path.exists():
                dump_data(path, file_format, data)
            return f"Deleted value from {path.name}."
        return "Error: invalid action. Use inspect, get, set, or delete."
