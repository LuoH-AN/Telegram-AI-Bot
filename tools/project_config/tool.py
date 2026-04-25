"""AI tool for repository config and database inspection and edits."""

from __future__ import annotations

import json
import logging
import os
from typing import Any

from ..core.base import BaseTool
from .files import detect_format, discover_config_files, discover_env_keys, ensure_supported_config_target, resolve_config_path
from .formats import delete_value, dump_data, get_value, load_data, render_value, set_value

logger = logging.getLogger(__name__)

_VALID_DB_ACTIONS = {"get", "set", "list", "delete"}
_VALID_DB_TARGETS = {"settings", "personas", "sessions", "conversations", "skills", "skill_states"}


def _get_db(user_id: int):
    from cache import cache
    from database.db import get_connection, get_dict_cursor
    from database.loaders import (
        parse_conversation_row,
        parse_persona_row,
        parse_session_row,
        parse_settings_row,
        parse_skill_row,
        parse_skill_state_row,
    )
    return {
        "cache": cache,
        "conn": get_connection,
        "cursor": get_dict_cursor,
        "parsers": {
            "settings": parse_settings_row,
            "persona": parse_persona_row,
            "session": parse_session_row,
            "conversation": parse_conversation_row,
            "skill": parse_skill_row,
            "skill_state": parse_skill_state_row,
        },
    }


class ProjectConfigTool(BaseTool):
    @property
    def name(self) -> str:
        return "project_config"

    def definitions(self) -> list[dict]:
        return [
            {
                "type": "function",
                "function": {
                    "name": self.name,
                    "description": (
                        "Inspect and modify repository config files (env, JSON, INI) or user database records. "
                        "Use source='file' for config files, source='database' for user settings/personas/sessions/conversations."
                    ),
                    "parameters": self._parameters(),
                },
            }
        ]

    def _parameters(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["inspect", "get", "set", "delete", "list"],
                    "description": "Action to perform",
                },
                "source": {
                    "type": "string",
                    "enum": ["file", "database"],
                    "description": "Data source: 'file' for config files, 'database' for user records",
                },
                # File args
                "path": {"type": "string", "description": "Repository-relative config file path (source=file)."},
                "key": {"type": "string", "description": "Key path for structured configs. Use SECTION.key for INI."},
                "value": {"description": "Value to set."},
                "format_hint": {"type": "string", "enum": ["auto", "env", "json", "ini", "text"]},
                # Database args
                "target": {
                    "type": "string",
                    "enum": sorted(_VALID_DB_TARGETS),
                    "description": "Database table/resource to access (source=database)",
                },
                "persona": {"type": "string", "description": "Persona name for session/conversation queries (source=database)"},
                "session_id": {"type": "integer", "description": "Session ID for conversation queries (source=database)"},
                "skill_name": {"type": "string", "description": "Skill name for skill_state queries (source=database)"},
            },
            "required": ["action"],
        }

    def get_instruction(self) -> str:
        return (
            "\nProject config tool usage:\n"
            "- Prefer project_config over terminal when reading or changing repository configuration.\n"
            "- Use source='file' for config files: action='inspect' to discover, 'get' to read, 'set' to write.\n"
            "- Use source='database' for user records: target='settings' for AI settings, 'personas' for personalities,\n"
            "  'sessions' for chat sessions, 'conversations' for message history, 'skills' for plugin states.\n"
            "- Database queries use the calling user's ID automatically.\n"
        )

    def execute(self, user_id: int, tool_name: str, arguments: dict) -> str:
        del tool_name
        action = str(arguments.get("action") or "").strip().lower()
        source = str(arguments.get("source") or "file").strip().lower()

        if source == "database":
            return self._execute_db(user_id, action, arguments)

        # File operations (original behavior)
        return self._execute_file(action, arguments)

    def _execute_file(self, action: str, arguments: dict) -> str:
        if action == "inspect":
            files = discover_config_files()
            keys = discover_env_keys()
            return (
                f"Config files:\n"
                + ("\n".join(f"- {item}" for item in files[:120]) or "(none found)")
                + f"\n\nKnown env keys:\n"
                + ("\n".join(f"- {item}" for item in keys[:200]) or "(none found)")
            )
        path = resolve_config_path(str(arguments.get("path") or "").strip(), must_exist=action == "get")
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

    def _execute_db(self, user_id: int, action: str, arguments: dict) -> str:
        target = str(arguments.get("target") or "").strip().lower()

        if action == "inspect":
            return self._db_inspect(user_id)

        if action not in _VALID_DB_ACTIONS:
            return f"Error: invalid action '{action}' for database. Use: {', '.join(sorted(_VALID_DB_ACTIONS))}"

        if not target:
            return f"Error: target required for database operations. Options: {', '.join(sorted(_VALID_DB_TARGETS))}"

        if target not in _VALID_DB_TARGETS:
            return f"Error: unknown target '{target}'. Options: {', '.join(sorted(_VALID_DB_TARGETS))}"

        try:
            if target == "settings":
                return self._db_settings(user_id, action, arguments)
            if target == "personas":
                return self._db_personas(user_id, action, arguments)
            if target == "sessions":
                return self._db_sessions(user_id, action, arguments)
            if target == "conversations":
                return self._db_conversations(user_id, action, arguments)
            if target == "skills":
                return self._db_skills(user_id, action, arguments)
            if target == "skill_states":
                return self._db_skill_states(user_id, action, arguments)
        except Exception as exc:
            logger.exception("Database operation failed for user %d", user_id)
            return f"Error: database operation failed - {exc}"

    def _db_inspect(self, user_id: int) -> str:
        from cache import cache
        settings = cache.get_settings(user_id)
        personas = cache.get_user_personas(user_id)
        sessions = cache.get_user_sessions(user_id)
        lines = [
            f"Database records for user {user_id}:",
            f"  Settings: {len(settings)} keys (current_persona={settings.get('current_persona', 'default')})",
            f"  Personas: {len(personas)}",
            f"  Sessions: {sum(len(v) for v in sessions.values())} total",
        ]
        # Skill count
        try:
            conn = get_connection_from_cache()
            with get_dict_cursor(conn) as cur:
                cur.execute("SELECT COUNT(*) as cnt FROM user_skills WHERE user_id = %s", (user_id,))
                row = cur.fetchone()
                lines.append(f"  Skills: {row['cnt'] if row else 0}")
        except Exception:
            lines.append("  Skills: (unavailable)")
        return "\n".join(lines)

    def _db_settings(self, user_id: int, action: str, arguments: dict) -> str:
        from cache import cache
        if action == "get":
            settings = cache.get_settings(user_id)
            key = str(arguments.get("key") or "").strip()
            if key:
                value = settings.get(key)
                return f"{key} = {json.dumps(value, ensure_ascii=False)}"
            return json.dumps(settings, ensure_ascii=False, indent=2)
        if action == "set":
            key = str(arguments.get("key") or "").strip()
            value = arguments.get("value")
            if not key:
                return "Error: key required for settings set"
            cache.update_settings(user_id, key, value)
            self._sync_to_db(user_id)
            return f"Updated settings.{key} = {json.dumps(value, ensure_ascii=False)}"
        if action == "list":
            settings = cache.get_settings(user_id)
            return "\n".join(f"  {k} = {json.dumps(v, ensure_ascii=False)}" for k, v in settings.items())
        return f"Error: action '{action}' not supported for settings. Use get, set, or list."

    def _db_personas(self, user_id: int, action: str, arguments: dict) -> str:
        from cache import cache
        if action == "get":
            personas = cache.get_user_personas(user_id)
            name_filter = str(arguments.get("key") or "").strip()
            if name_filter:
                for p in personas:
                    if p.get("name") == name_filter:
                        return json.dumps(p, ensure_ascii=False, indent=2)
                return f"Persona '{name_filter}' not found"
            return json.dumps(personas, ensure_ascii=False, indent=2)
        if action == "list":
            personas = cache.get_user_personas(user_id)
            lines = [f"Personas ({len(personas)}):"]
            current = cache.get_current_persona_name(user_id)
            for p in personas:
                marker = " *" if p.get("name") == current else ""
                lines.append(f"  {p['name']}{marker}")
            return "\n".join(lines)
        if action == "set":
            name = str(arguments.get("key") or "").strip()
            system_prompt = arguments.get("value")
            if not name or system_prompt is None:
                return "Error: key (persona name) and value (system_prompt) required"
            self._upsert_persona(user_id, name, system_prompt)
            return f"Updated persona '{name}'"
        return f"Error: action '{action}' not supported for personas. Use get, list, or set."

    def _db_sessions(self, user_id: int, action: str, arguments: dict) -> str:
        from cache import cache
        persona_name = str(arguments.get("persona") or cache.get_current_persona_name(user_id)).strip()
        sessions = cache.get_user_sessions(user_id).get(persona_name, [])
        if action == "list":
            lines = [f"Sessions for '{persona_name}' ({len(sessions)}):"]
            current = cache.get_current_session_id(user_id)
            for s in sessions:
                marker = " *" if s.get("id") == current else ""
                lines.append(f"  [{s['id']}] {s.get('title', '(no title)')}{marker}")
            return "\n".join(lines)
        if action == "get":
            session_id = arguments.get("session_id")
            if session_id:
                for s in sessions:
                    if s.get("id") == session_id:
                        return json.dumps(s, ensure_ascii=False, indent=2)
                return f"Session {session_id} not found"
            return json.dumps(sessions, ensure_ascii=False, indent=2)
        return f"Error: action '{action}' not supported for sessions. Use list or get."

    def _db_conversations(self, user_id: int, action: str, arguments: dict) -> str:
        from cache import cache
        session_id = arguments.get("session_id")
        if not session_id:
            session_id = cache.get_current_session_id(user_id)
        if not session_id:
            return "No active session. Provide session_id."
        conversations = cache.get_conversation_by_session(session_id)
        if action == "list":
            lines = [f"Conversations in session {session_id} ({len(conversations)} messages):"]
            for msg in conversations:
                role = msg.get("role", "?")
                content = msg.get("content", "")
                preview = content[:80] + ("..." if len(content) > 80 else "")
                lines.append(f"  [{role}] {preview}")
            return "\n".join(lines)
        if action == "get":
            return json.dumps(conversations, ensure_ascii=False, indent=2)
        return f"Error: action '{action}' not supported for conversations. Use list or get."

    def _db_skills(self, user_id: int, action: str, arguments: dict) -> str:
        conn = get_connection_from_cache()
        with get_dict_cursor(conn) as cur:
            if action == "list":
                cur.execute("SELECT name, display_name, source_type, enabled, install_status FROM user_skills WHERE user_id = %s", (user_id,))
                rows = cur.fetchall()
                lines = [f"Skills ({len(rows)}):"]
                for r in rows:
                    status = "✓" if r["enabled"] else "✗"
                    lines.append(f"  {status} {r['name']} ({r['display_name']}) - {r['source_type']} - {r['install_status']}")
                return "\n".join(lines)
            if action == "get":
                name = str(arguments.get("key") or "").strip()
                if not name:
                    cur.execute("SELECT name, display_name, source_type, source_ref, version, enabled, install_status, manifest_json, capabilities_json FROM user_skills WHERE user_id = %s", (user_id,))
                    return json.dumps([dict(r) for r in cur.fetchall()], ensure_ascii=False, indent=2)
                cur.execute("SELECT * FROM user_skills WHERE user_id = %s AND name = %s", (user_id, name))
                row = cur.fetchone()
                if not row:
                    return f"Skill '{name}' not found"
                return json.dumps(dict(row), ensure_ascii=False, indent=2)
        return f"Error: action '{action}' not supported for skills. Use list or get."

    def _db_skill_states(self, user_id: int, action: str, arguments: dict) -> str:
        skill_name = str(arguments.get("skill_name") or arguments.get("key") or "").strip()
        if not skill_name:
            return "Error: skill_name required for skill_states"
        conn = get_connection_from_cache()
        with get_dict_cursor(conn) as cur:
            if action == "get":
                cur.execute("SELECT * FROM user_skill_states WHERE user_id = %s AND skill_name = %s", (user_id, skill_name))
                row = cur.fetchone()
                if not row:
                    return f"No state found for skill '{skill_name}'"
                return json.dumps(dict(row), ensure_ascii=False, indent=2)
            if action == "list":
                cur.execute("SELECT skill_name, state_version, updated_at FROM user_skill_states WHERE user_id = %s", (user_id,))
                rows = cur.fetchall()
                lines = [f"Skill states ({len(rows)}):"]
                for r in rows:
                    lines.append(f"  {r['skill_name']} (v{r['state_version']}) updated={r['updated_at']}")
                return "\n".join(lines)
        return f"Error: action '{action}' not supported for skill_states. Use list or get."

    def _sync_to_db(self, user_id: int) -> None:
        from cache import sync_to_database
        try:
            sync_to_database()
        except Exception:
            pass

    def _upsert_persona(self, user_id: int, name: str, system_prompt: str) -> None:
        from cache import cache
        personas = cache.get_user_personas(user_id)
        for p in personas:
            if p["name"] == name:
                p["system_prompt"] = system_prompt
                cache.replace_user_personas(user_id, personas)
                self._sync_to_db(user_id)
                return
        # Insert new
        from database.db import get_connection, get_dict_cursor
        conn = get_connection()
        try:
            with get_dict_cursor(conn) as cur:
                cur.execute(
                    "INSERT INTO user_personas (user_id, name, system_prompt) VALUES (%s, %s, %s) ON CONFLICT (user_id, name) DO UPDATE SET system_prompt = EXCLUDED.system_prompt",
                    (user_id, name, system_prompt),
                )
            conn.commit()
        finally:
            conn.close()
        from services.state.db import refresh_cache_from_db
        refresh_cache_from_db(user_id)


# Module-level helpers to avoid import overhead
_conn_cache = None


def get_connection_from_cache():
    global _conn_cache
    if _conn_cache is None:
        from database.db import get_connection
        _conn_cache = get_connection
    return _conn_cache()


def get_dict_cursor(conn):
    from database.db import get_dict_cursor as _gdc
    return _gdc(conn)
