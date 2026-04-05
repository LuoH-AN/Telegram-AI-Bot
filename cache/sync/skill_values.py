"""Skill row value builders."""

from __future__ import annotations

import json


def skill_values(skill: dict) -> tuple:
    return (
        skill["user_id"],
        skill["name"],
        skill.get("display_name", skill["name"]),
        skill.get("source_type", "builtin"),
        skill.get("source_ref", ""),
        skill.get("version", ""),
        bool(skill.get("enabled", True)),
        skill.get("install_status", "installed"),
        skill.get("entrypoint", ""),
        json.dumps(skill.get("manifest", {}), ensure_ascii=False),
        json.dumps(skill.get("capabilities", []), ensure_ascii=False),
        skill.get("persist_mode", "none"),
        skill.get("last_restore_at"),
        skill.get("last_persist_at"),
        skill.get("last_error", ""),
    )


def skill_update_values(skill: dict) -> tuple:
    return skill_values(skill)[2:] + (skill["user_id"], skill["name"])


def skill_state_values(state: dict) -> tuple:
    return (
        state["user_id"],
        state["skill_name"],
        json.dumps(state.get("state", {}), ensure_ascii=False),
        state.get("state_version", ""),
        state.get("checkpoint_ref", ""),
    )
