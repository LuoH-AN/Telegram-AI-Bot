"""db_records tool — read/write user database records (settings/personas/sessions/...).

Split out of the old project_config god-tool (database half). All queries are
scoped to the calling user's id automatically.
"""

from __future__ import annotations

import asyncio
import json
from typing import Annotated, Any, Literal

from infrastructure.tools.core import ToolContext, ToolResult, tool

VALID_TARGETS = ("settings", "personas", "sessions", "conversations", "skills", "skill_states")

DB_RECORDS_INSTRUCTION = (
    "\ndb_records usage (admin toolset):\n"
    "- Inspect or modify user records. All queries use the calling user's id automatically.\n"
    "- target='settings' AI settings, 'personas' personalities, 'sessions' chat sessions,\n"
    "  'conversations' message history, 'skills' plugin enable/visibility, 'skill_states' skill state.\n"
    "- action=inspect summarizes record counts; get/list read; set writes (settings/personas only).\n"
)


def _inspect(user_id: int) -> ToolResult:
    from infrastructure.cache import cache
    from infrastructure.database.db import get_connection, get_dict_cursor

    settings = cache.get_settings(user_id)
    personas = cache.get_user_personas(user_id)
    sessions = cache.get_user_sessions(user_id)
    lines = [
        f"Database records for user {user_id}:",
        f"  Settings: {len(settings)} keys (current_persona={settings.get('current_persona', 'default')})",
        f"  Personas: {len(personas)}",
        f"  Sessions: {sum(len(v) for v in sessions.values())} total",
    ]
    try:
        with get_connection() as conn, get_dict_cursor(conn) as cur:
            cur.execute("SELECT COUNT(*) AS cnt FROM user_skills WHERE user_id = %s", (user_id,))
            row = cur.fetchone()
            lines.append(f"  Skills: {row['cnt'] if row else 0}")
    except Exception:
        lines.append("  Skills: (unavailable)")
    return ToolResult.text("\n".join(lines))


def _settings(user_id: int, action: str, key: str, value: Any) -> ToolResult:
    from infrastructure.cache import cache, sync_to_database

    if action == "get":
        settings = cache.get_settings(user_id)
        if key:
            return ToolResult.text(f"{key} = {json.dumps(settings.get(key), ensure_ascii=False)}")
        return ToolResult.text(json.dumps(settings, ensure_ascii=False, indent=2))
    if action == "set":
        if not key:
            return ToolResult.error("missing_key", "key required for settings set")
        cache.update_settings(user_id, key, value)
        sync_to_database()
        return ToolResult.text(f"Updated settings.{key} = {json.dumps(value, ensure_ascii=False)}")
    if action == "list":
        settings = cache.get_settings(user_id)
        return ToolResult.text("\n".join(f"  {k} = {json.dumps(v, ensure_ascii=False)}" for k, v in settings.items()))
    return ToolResult.error("invalid_action", f"action '{action}' not supported for settings. Use get, set, or list.")


def _personas(user_id: int, action: str, key: str, value: Any) -> ToolResult:
    from infrastructure.cache import cache, sync_to_database

    personas = cache.get_user_personas(user_id)
    if action == "list":
        current = cache.get_current_persona_name(user_id)
        lines = [f"Personas ({len(personas)}):"]
        lines += [f"  {p['name']}{' *' if p.get('name') == current else ''}" for p in personas]
        return ToolResult.text("\n".join(lines))
    if action == "get":
        if key:
            for p in personas:
                if p.get("name") == key:
                    return ToolResult.text(json.dumps(p, ensure_ascii=False, indent=2))
            return ToolResult.error("not_found", f"Persona '{key}' not found")
        return ToolResult.text(json.dumps(personas, ensure_ascii=False, indent=2))
    if action == "set":
        if not key or value is None:
            return ToolResult.error("missing_args", "key (persona name) and value (system_prompt) required")
        for p in personas:
            if p["name"] == key:
                p["system_prompt"] = value
                cache.replace_user_personas(user_id, personas)
                sync_to_database()
                return ToolResult.text(f"Updated persona '{key}'")
        from domain.services.sync_state.db import refresh_cache_from_db
        from infrastructure.database.db import get_connection, get_dict_cursor

        with get_connection() as conn:
            with get_dict_cursor(conn) as cur:
                cur.execute("INSERT INTO user_personas (user_id, name, system_prompt) VALUES (%s, %s, %s) ON CONFLICT (user_id, name) DO UPDATE SET system_prompt = EXCLUDED.system_prompt", (user_id, key, value))
            conn.commit()
        refresh_cache_from_db(user_id)
        return ToolResult.text(f"Updated persona '{key}'")
    return ToolResult.error("invalid_action", f"action '{action}' not supported for personas. Use get, list, or set.")


def _sessions(user_id: int, action: str, persona: str, session_id: int | None) -> ToolResult:
    from infrastructure.cache import cache

    persona_name = persona or cache.get_current_persona_name(user_id)
    sessions = cache.get_user_sessions(user_id).get(persona_name, [])
    if action == "list":
        current = cache.get_current_session_id(user_id)
        lines = [f"Sessions for '{persona_name}' ({len(sessions)}):"]
        lines += [f"  [{s.get('id')}] {s.get('title', '(no title)')}{' *' if s.get('id') == current else ''}" for s in sessions]
        return ToolResult.text("\n".join(lines))
    if action == "get":
        if session_id:
            for s in sessions:
                if s.get("id") == session_id:
                    return ToolResult.text(json.dumps(s, ensure_ascii=False, indent=2))
            return ToolResult.error("not_found", f"Session {session_id} not found")
        return ToolResult.text(json.dumps(sessions, ensure_ascii=False, indent=2))
    return ToolResult.error("invalid_action", f"action '{action}' not supported for sessions. Use list or get.")


def _conversations(user_id: int, action: str, session_id: int | None) -> ToolResult:
    from infrastructure.cache import cache

    if not session_id:
        session_id = cache.get_current_session_id(user_id)
    if not session_id:
        return ToolResult.error("no_session", "No active session. Provide session_id.")
    conv = cache.get_conversation_by_session(session_id)
    if action == "list":
        lines = [f"Conversations in session {session_id} ({len(conv)} messages):"]
        for msg in conv:
            preview = (msg.get("content", ""))[:80]
            lines.append(f"  [{msg.get('role', '?')}] {preview}{'...' if len(msg.get('content', '')) > 80 else ''}")
        return ToolResult.text("\n".join(lines))
    if action == "get":
        return ToolResult.text(json.dumps(conv, ensure_ascii=False, indent=2))
    return ToolResult.error("invalid_action", f"action '{action}' not supported for conversations. Use list or get.")


def _skills(user_id: int, action: str, key: str) -> ToolResult:
    from infrastructure.database.db import get_connection, get_dict_cursor

    with get_connection() as conn, get_dict_cursor(conn) as cur:
        if action == "list":
            cur.execute("SELECT name, display_name, source_type, enabled, install_status FROM user_skills WHERE user_id = %s", (user_id,))
            rows = cur.fetchall()
            lines = [f"Skills ({len(rows)}):"]
            lines += [f"  {'✓' if r['enabled'] else '✗'} {r['name']} ({r['display_name']}) - {r['source_type']} - {r['install_status']}" for r in rows]
            return ToolResult.text("\n".join(lines))
        if action == "get":
            if not key:
                cur.execute("SELECT name, display_name, source_type, source_ref, version, enabled, install_status, manifest_json, capabilities_json FROM user_skills WHERE user_id = %s", (user_id,))
                return ToolResult.text(json.dumps([dict(r) for r in cur.fetchall()], ensure_ascii=False, indent=2))
            cur.execute("SELECT * FROM user_skills WHERE user_id = %s AND name = %s", (user_id, key))
            row = cur.fetchone()
            if not row:
                return ToolResult.error("not_found", f"Skill '{key}' not found")
            return ToolResult.text(json.dumps(dict(row), ensure_ascii=False, indent=2))
    return ToolResult.error("invalid_action", f"action '{action}' not supported for skills. Use list or get.")


def _skill_states(user_id: int, action: str, skill_name: str) -> ToolResult:
    if not skill_name:
        return ToolResult.error("missing_skill_name", "skill_name required for skill_states")
    from infrastructure.database.db import get_connection, get_dict_cursor

    with get_connection() as conn, get_dict_cursor(conn) as cur:
        if action == "get":
            cur.execute("SELECT * FROM user_skill_states WHERE user_id = %s AND skill_name = %s", (user_id, skill_name))
            row = cur.fetchone()
            if not row:
                return ToolResult.error("not_found", f"No state found for skill '{skill_name}'")
            return ToolResult.text(json.dumps(dict(row), ensure_ascii=False, indent=2))
        if action == "list":
            cur.execute("SELECT skill_name, state_version, updated_at FROM user_skill_states WHERE user_id = %s", (user_id,))
            rows = cur.fetchall()
            lines = [f"Skill states ({len(rows)}):"]
            lines += [f"  {r['skill_name']} (v{r['state_version']}) updated={r['updated_at']}" for r in rows]
            return ToolResult.text("\n".join(lines))
    return ToolResult.error("invalid_action", f"action '{action}' not supported for skill_states. Use list or get.")


_DISPATCH = {
    "settings": _settings,
    "personas": _personas,
    "sessions": _sessions,
    "conversations": _conversations,
    "skills": _skills,
    "skill_states": _skill_states,
}


def _run_db(user_id: int, action: str, target: str, key: str, value: Any, persona: str, session_id: int | None, skill_name: str) -> ToolResult:
    if action == "inspect":
        return _inspect(user_id)
    if not target:
        return ToolResult.error("missing_target", f"target required. Options: {', '.join(VALID_TARGETS)}")
    if target not in VALID_TARGETS:
        return ToolResult.error("unknown_target", f"unknown target '{target}'. Options: {', '.join(VALID_TARGETS)}")
    handler = _DISPATCH[target]
    if target in ("settings", "personas"):
        return handler(user_id, action, key, value)
    if target == "sessions":
        return handler(user_id, action, persona, session_id)
    if target == "conversations":
        return handler(user_id, action, session_id)
    if target == "skills":
        return handler(user_id, action, key)
    return handler(user_id, action, skill_name or key)


@tool(toolset="admin", skill="project_config", instruction=DB_RECORDS_INSTRUCTION, description="Inspect and modify user database records: settings, personas, sessions, conversations, skills, skill_states. Scoped to the calling user.")
async def db_records(
    ctx: ToolContext,
    action: Literal["inspect", "get", "set", "list", "delete"],
    target: Annotated[str, "Database resource. One of: settings, personas, sessions, conversations, skills, skill_states."] = "",
    key: Annotated[str, "Record key (e.g. settings key, persona name, skill name)."] = "",
    value: Annotated[Any, "Value to set."] = None,
    persona: Annotated[str, "Persona name for session queries."] = "",
    session_id: Annotated[int, "Session id for conversation queries."] = 0,
    skill_name: Annotated[str, "Skill name for skill_state queries."] = "",
) -> ToolResult:
    try:
        return await asyncio.to_thread(_run_db, ctx.user_id, action, (target or "").strip().lower(), (key or "").strip(), value, (persona or "").strip(), int(session_id) or None, (skill_name or "").strip())
    except Exception as exc:
        return ToolResult.error("operation_failed", f"db_records failed: {exc}")
