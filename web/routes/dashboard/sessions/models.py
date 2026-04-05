"""Request models for sessions routes."""

from pydantic import BaseModel


class SessionCreate(BaseModel):
    persona: str | None = None
    title: str | None = None
    switch_to_new: bool = True


class SessionRename(BaseModel):
    title: str


class SessionClearBody(BaseModel):
    reset_usage: bool = False

