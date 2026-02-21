"""Personas API routes."""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from services import (
    get_personas,
    get_current_persona_name,
    create_persona,
    update_persona_prompt,
    delete_persona,
)
from web.auth import get_current_user

router = APIRouter(prefix="/api/personas", tags=["personas"])


class PersonaCreate(BaseModel):
    name: str
    system_prompt: str | None = None


class PersonaUpdate(BaseModel):
    system_prompt: str


@router.get("")
async def list_personas(user_id: int = Depends(get_current_user)):
    """Return all personas and the current persona name."""
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
async def create_new_persona(
    body: PersonaCreate,
    user_id: int = Depends(get_current_user),
):
    """Create a new persona."""
    ok = create_persona(user_id, body.name, body.system_prompt)
    if not ok:
        raise HTTPException(status_code=409, detail="Persona already exists")
    return {"ok": True}


@router.put("/{name}")
async def update_persona(
    name: str,
    body: PersonaUpdate,
    user_id: int = Depends(get_current_user),
):
    """Update a persona's system prompt."""
    ok = update_persona_prompt(user_id, name, body.system_prompt)
    if not ok:
        raise HTTPException(status_code=404, detail="Persona not found")
    return {"ok": True}


@router.delete("/{name}")
async def delete_persona_route(
    name: str,
    user_id: int = Depends(get_current_user),
):
    """Delete a persona (cannot delete 'default')."""
    if name == "default":
        raise HTTPException(status_code=400, detail="Cannot delete the default persona")
    ok = delete_persona(user_id, name)
    if not ok:
        raise HTTPException(status_code=404, detail="Persona not found or cannot delete")
    return {"ok": True}
