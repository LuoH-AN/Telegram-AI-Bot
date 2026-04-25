"""Schemas and helpers for persona routes."""

from pydantic import BaseModel


class PersonaCreate(BaseModel):
    name: str
    system_prompt: str | None = None


class PersonaUpdate(BaseModel):
    system_prompt: str


def normalize_persona_name(name: str) -> str:
    return (name or "").strip()

