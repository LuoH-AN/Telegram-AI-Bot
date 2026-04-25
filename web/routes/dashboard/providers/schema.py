"""Schemas and helper functions for provider routes."""

from pydantic import BaseModel


class ProviderCreate(BaseModel):
    name: str
    api_key: str
    base_url: str
    model: str = ""


class ProviderUpdate(BaseModel):
    api_key: str | None = None
    base_url: str | None = None
    model: str | None = None


class ProviderSaveCurrent(BaseModel):
    name: str


def mask_key(key: str) -> str:
    if not key:
        return ""
    if len(key) <= 8:
        return key[:2] + "***"
    return key[:8] + "***"


def resolve_provider_name(presets: dict, name: str) -> str | None:
    if name in presets:
        return name
    lowered = name.lower()
    return next((key for key in presets if key.lower() == lowered), None)

