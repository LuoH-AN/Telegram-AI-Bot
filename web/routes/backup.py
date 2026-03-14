"""Backup import/export API routes."""

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException

from cache import cache
from services import (
    get_user_settings,
    update_user_setting,
    get_personas,
    get_current_persona_name,
    create_persona,
    update_persona_prompt,
    delete_persona,
    get_sessions,
    create_session,
    get_conversation,
    add_message,
    get_memories,
    add_memory,
    clear_memories,
    reset_token_usage,
    set_token_limit,
    add_token_usage,
)
from services.log import record_web_action
from web.auth import get_current_user

router = APIRouter(prefix="/api/backup", tags=["backup"])

SETTINGS_BACKUP_KEYS = {
    "api_key",
    "base_url",
    "model",
    "temperature",
    "reasoning_effort",
    "show_thinking",
    "stream_mode",
    "enabled_tools",
    "cron_enabled_tools",
    "tts_voice",
    "tts_style",
    "tts_endpoint",
    "api_presets",
    "title_model",
    "cron_model",
}


def _parse_iso_datetime(value: str | None):
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except Exception:
        return None


def _clear_persona_sessions(user_id: int, persona_name: str) -> None:
    sessions = get_sessions(user_id, persona_name)
    for session in sessions:
        cache.delete_session(session["id"], user_id, persona_name)
    # clear pointer explicitly (method accepts runtime None)
    cache.set_current_session_id(user_id, persona_name, None)  # type: ignore[arg-type]


def _apply_persona_usage(user_id: int, persona_name: str, usage: dict | None) -> None:
    usage = usage or {}
    prompt_tokens = int(usage.get("prompt_tokens", 0) or 0)
    completion_tokens = int(usage.get("completion_tokens", 0) or 0)
    token_limit = int(usage.get("token_limit", 0) or 0)

    reset_token_usage(user_id, persona_name)
    set_token_limit(user_id, token_limit, persona_name)
    if prompt_tokens > 0 or completion_tokens > 0:
        add_token_usage(user_id, prompt_tokens, completion_tokens, persona_name)


def _export_sessions(user_id: int, persona_name: str) -> list[dict]:
    sessions = get_sessions(user_id, persona_name)
    current_session_id = cache.get_current_session_id(user_id, persona_name)
    output = []
    for session in sessions:
        session_id = session["id"]
        messages = get_conversation(session_id)
        output.append(
            {
                "title": session.get("title") or "",
                "created_at": session.get("created_at"),
                "current": session_id == current_session_id,
                "messages": [
                    {"role": m.get("role", ""), "content": m.get("content", "")}
                    for m in messages
                ],
            }
        )
    return output


@router.get("/export")
async def export_backup(user_id: int = Depends(get_current_user)):
    """Export user settings/data as JSON payload."""
    settings = dict(get_user_settings(user_id))
    personas = get_personas(user_id)
    current_persona = get_current_persona_name(user_id)

    personas_payload = []
    for name in sorted(personas.keys(), key=lambda x: (x != "default", x)):
        persona = personas[name]
        usage = cache.get_token_usage(user_id, name)
        personas_payload.append(
            {
                "name": name,
                "system_prompt": persona.get("system_prompt", ""),
                "current": name == current_persona,
                "usage": {
                    "prompt_tokens": usage.get("prompt_tokens", 0),
                    "completion_tokens": usage.get("completion_tokens", 0),
                    "total_tokens": usage.get("total_tokens", 0),
                    "token_limit": usage.get("token_limit", 0),
                },
                "sessions": _export_sessions(user_id, name),
            }
        )

    memories = [
        {
            "content": m.get("content", ""),
            "source": m.get("source", "user"),
        }
        for m in get_memories(user_id)
    ]

    cron_tasks = []
    for task in cache.get_cron_tasks(user_id):
        cron_tasks.append(
            {
                "name": task.get("name", ""),
                "cron_expression": task.get("cron_expression", ""),
                "prompt": task.get("prompt", ""),
                "enabled": bool(task.get("enabled", True)),
                "last_run_at": task["last_run_at"].isoformat() if hasattr(task.get("last_run_at"), "isoformat") else task.get("last_run_at"),
            }
        )

    payload = {
        "version": 1,
        "exported_at": datetime.now().isoformat(),
        "settings": {k: settings.get(k) for k in SETTINGS_BACKUP_KEYS if k in settings},
        "personas": personas_payload,
        "memories": memories,
        "cron_tasks": cron_tasks,
    }

    record_web_action(
        user_id,
        "backup.export",
        {
            "personas": len(personas_payload),
            "memories": len(memories),
            "cron_tasks": len(cron_tasks),
        },
    )
    return payload


@router.post("/import")
async def import_backup(
    body: dict,
    user_id: int = Depends(get_current_user),
):
    """Import backup payload (mode: replace | merge)."""
    mode = str(body.get("mode", "replace")).strip().lower()
    payload = body.get("payload", body)
    if mode not in {"replace", "merge"}:
        raise HTTPException(status_code=400, detail="mode must be replace or merge")
    if not isinstance(payload, dict):
        raise HTTPException(status_code=400, detail="Invalid payload")

    settings_payload = payload.get("settings") or {}
    personas_payload = payload.get("personas") or []
    memories_payload = payload.get("memories") or []
    cron_payload = payload.get("cron_tasks") or []

    if not isinstance(settings_payload, dict):
        raise HTTPException(status_code=400, detail="settings must be an object")
    if not isinstance(personas_payload, list):
        raise HTTPException(status_code=400, detail="personas must be an array")
    if not isinstance(memories_payload, list):
        raise HTTPException(status_code=400, detail="memories must be an array")
    if not isinstance(cron_payload, list):
        raise HTTPException(status_code=400, detail="cron_tasks must be an array")

    if mode == "replace":
        # Remove all non-default personas and clear default persona data.
        existing_names = list(get_personas(user_id).keys())
        for name in existing_names:
            if name != "default":
                delete_persona(user_id, name)

        # Default persona always exists; reset its sessions/tokens before import.
        if "default" in get_personas(user_id):
            _clear_persona_sessions(user_id, "default")
            _apply_persona_usage(user_id, "default", {"prompt_tokens": 0, "completion_tokens": 0, "token_limit": 0})

        clear_memories(user_id)

        for task in list(cache.get_cron_tasks(user_id)):
            cache.delete_cron_task(user_id, task.get("name", ""))

    # Apply settings
    for key, value in settings_payload.items():
        if key in SETTINGS_BACKUP_KEYS:
            update_user_setting(user_id, key, value)

    # Apply personas and sessions
    imported_current_persona = None
    for p in personas_payload:
        if not isinstance(p, dict):
            continue
        name = str(p.get("name", "")).strip()
        if not name:
            continue
        prompt = str(p.get("system_prompt", "")).strip() or "You are a helpful assistant."

        if name not in get_personas(user_id):
            create_persona(user_id, name, prompt)
        else:
            update_persona_prompt(user_id, name, prompt)

        if mode == "replace":
            _clear_persona_sessions(user_id, name)

        _apply_persona_usage(user_id, name, p.get("usage"))

        current_session_id = None
        sessions = p.get("sessions", [])
        if isinstance(sessions, list):
            for s in sessions:
                if not isinstance(s, dict):
                    continue
                title = str(s.get("title", "")).strip() or None
                new_session = create_session(user_id, name, title)
                new_session_id = new_session["id"]

                messages = s.get("messages", [])
                if isinstance(messages, list):
                    for m in messages:
                        if not isinstance(m, dict):
                            continue
                        role = str(m.get("role", "")).strip() or "user"
                        content = str(m.get("content", ""))
                        add_message(new_session_id, role, content)

                if bool(s.get("current", False)):
                    current_session_id = new_session_id

        if current_session_id is not None:
            cache.set_current_session_id(user_id, name, current_session_id)

        if bool(p.get("current", False)):
            imported_current_persona = name

    # Apply memories
    for mem in memories_payload:
        if not isinstance(mem, dict):
            continue
        content = str(mem.get("content", "")).strip()
        if not content:
            continue
        source = str(mem.get("source", "user") or "user")
        add_memory(user_id, content, source=source)

    # Apply cron tasks
    existing_task_names = {t.get("name", ""): t for t in cache.get_cron_tasks(user_id)}
    for task in cron_payload:
        if not isinstance(task, dict):
            continue
        name = str(task.get("name", "")).strip()
        expr = str(task.get("cron_expression", "")).strip()
        prompt = str(task.get("prompt", "")).strip()
        if not name or not expr or not prompt:
            continue

        if name in existing_task_names:
            cache.update_cron_task(
                user_id,
                name,
                cron_expression=expr,
                prompt=prompt,
                enabled=bool(task.get("enabled", True)),
            )
        else:
            created = cache.add_cron_task(user_id, name, expr, prompt)
            if created is None:
                continue
            cache.update_cron_task(
                user_id,
                name,
                enabled=bool(task.get("enabled", True)),
            )

        last_run_at = _parse_iso_datetime(task.get("last_run_at"))
        if last_run_at is not None:
            cache.update_cron_last_run(user_id, name, last_run_at)

    # Switch current persona at end if specified and valid.
    if imported_current_persona and imported_current_persona in get_personas(user_id):
        cache.set_current_persona(user_id, imported_current_persona)

    record_web_action(
        user_id,
        "backup.import",
        {
            "mode": mode,
            "settings": len(settings_payload),
            "personas": len(personas_payload),
            "memories": len(memories_payload),
            "cron_tasks": len(cron_payload),
        },
    )
    return {
        "ok": True,
        "mode": mode,
        "imported": {
            "settings": len(settings_payload),
            "personas": len(personas_payload),
            "memories": len(memories_payload),
            "cron_tasks": len(cron_payload),
        },
    }
