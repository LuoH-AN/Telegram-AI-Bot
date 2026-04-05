"""Compatibility stubs for deprecated skill management.

The `/skill` command flow has been removed. This module keeps a minimal API
surface so older imports do not crash, while returning disabled/no-op results.
"""

from __future__ import annotations


def list_skills(user_id: int) -> list[dict]:
    del user_id
    return []


def get_skill(user_id: int, name: str) -> dict | None:
    del user_id, name
    return None


def install_skill(
    user_id: int,
    name: str,
    *,
    source_type: str = "builtin",
    source_ref: str = "",
    persist_mode: str = "none",
) -> dict:
    del user_id, source_type, source_ref, persist_mode
    raise RuntimeError(f"Skill management is disabled: {name}")


def install_skill_from_github(
    user_id: int,
    github_url: str,
    *,
    name_hint: str = "",
    persist_mode: str = "none",
) -> dict | None:
    del user_id, github_url, name_hint, persist_mode
    return None


def enable_skill(user_id: int, name: str, enabled: bool = True) -> bool:
    del user_id, name, enabled
    return False


def remove_skill(user_id: int, name: str) -> bool:
    del user_id, name
    return False


def call_skill(user_id: int, name: str, input_text: str) -> str:
    del user_id, name, input_text
    return "Skill system is disabled."


def persist_skill_state(user_id: int, name: str) -> bool:
    del user_id, name
    return False


def persist_skill_snapshot(user_id: int, name: str, snapshot_id: str | None = None) -> bool:
    del user_id, name, snapshot_id
    return False


def list_skill_snapshots(user_id: int, name: str) -> list[str]:
    del user_id, name
    return []


def restore_skill(user_id: int, name: str) -> bool:
    del user_id, name
    return False


def restore_skill_snapshot(user_id: int, name: str, snapshot_id: str | None = None) -> bool:
    del user_id, name, snapshot_id
    return False


def auto_restore_skills(user_id: int) -> None:
    del user_id
    return None

