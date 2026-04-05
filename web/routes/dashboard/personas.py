"""Personas API routes."""
from fastapi import APIRouter, Depends, HTTPException
from services import (
    get_personas,
    get_current_persona_name,
    create_persona,
    update_persona_prompt,
    delete_persona,
    switch_persona,
    get_token_usage,
    ensure_session,
    get_message_count,
    get_session_count,
    get_current_session,
)
from services.log import record_web_action
from web.auth import get_current_user
from web.routes.dashboard.personas_schema import PersonaCreate, PersonaUpdate, normalize_persona_name

router = APIRouter(prefix="/api/personas", tags=["personas"])

@router.get("")
async def list_personas(user_id: int = Depends(get_current_user)):
    personas = get_personas(user_id)
    current = get_current_persona_name(user_id)
    return {
        "current": current,
        "personas": {
            name: {"name": name, "system_prompt": p["system_prompt"]}
            for name, p in personas.items()
        },
    }
@router.post("")
async def create_new_persona(body: PersonaCreate, user_id: int = Depends(get_current_user)):
    name = normalize_persona_name(body.name)
    if not name:
        raise HTTPException(status_code=400, detail="Persona name is required")

    ok = create_persona(user_id, name, body.system_prompt)
    if not ok:
        raise HTTPException(status_code=409, detail="Persona already exists")

    record_web_action(user_id, "persona.create", {"persona": name})
    return {"ok": True}
@router.post("/{name}/switch")
async def switch_persona_route(name: str, user_id: int = Depends(get_current_user)):
    name = normalize_persona_name(name)
    personas = get_personas(user_id)
    if name not in personas:
        raise HTTPException(status_code=404, detail="Persona not found")

    switch_persona(user_id, name)
    usage = get_token_usage(user_id, name)
    session_id = ensure_session(user_id, name)
    msg_count = get_message_count(session_id)
    session_ct = get_session_count(user_id, name)
    current_session = get_current_session(user_id, name)
    session_title = (current_session.get("title") or "New Chat") if current_session else "New Chat"
    prompt_text = personas[name]["system_prompt"]
    if len(prompt_text) > 120: prompt_text = prompt_text[:120] + "..."

    record_web_action(user_id, "persona.switch", {"persona": name})
    return {
        "ok": True,
        "persona": name,
        "messages": msg_count,
        "sessions": session_ct,
        "current_session_title": session_title,
        "tokens": usage.get("total_tokens", 0),
        "prompt_preview": prompt_text,
    }
@router.put("/{name}")
async def update_persona(name: str, body: PersonaUpdate, user_id: int = Depends(get_current_user)):
    name = normalize_persona_name(name)
    ok = update_persona_prompt(user_id, name, body.system_prompt)
    if not ok:
        raise HTTPException(status_code=404, detail="Persona not found")

    record_web_action(user_id, "persona.update", {"persona": name})
    return {"ok": True}
@router.delete("/{name}")
async def delete_persona_route(name: str, user_id: int = Depends(get_current_user)):
    name = normalize_persona_name(name)
    if name == "default":
        raise HTTPException(status_code=400, detail="Cannot delete the default persona")

    ok = delete_persona(user_id, name)
    if not ok:
        raise HTTPException(status_code=404, detail="Persona not found or cannot delete")

    record_web_action(user_id, "persona.delete", {"persona": name})
    return {"ok": True}
