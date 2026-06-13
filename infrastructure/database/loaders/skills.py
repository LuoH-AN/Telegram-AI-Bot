"""Skill-related row parsers."""

from __future__ import annotations

from collections.abc import Mapping

from .json_utils import parse_json_list, parse_json_object


def parse_skill_row(row: Mapping) -> dict:
    return {
        "id": row["id"],
        "user_id": row["user_id"],
        "name": row["name"],
        "display_name": row.get("display_name") or row["name"],
        "source_type": row.get("source_type") or "builtin",
        "source_ref": row.get("source_ref") or "",
        "version": row.get("version") or "",
        "enabled": bool(row.get("enabled", True)),
        "install_status": row.get("install_status") or "installed",
        "entrypoint": row.get("entrypoint") or "",
        "manifest": parse_json_object(row.get("manifest_json")),
        "capabilities": parse_json_list(row.get("capabilities_json")),
        "persist_mode": row.get("persist_mode") or "none",
        "last_restore_at": row.get("last_restore_at"),
        "last_persist_at": row.get("last_persist_at"),
        "last_error": row.get("last_error") or "",
        "created_at": row.get("created_at"),
        "updated_at": row.get("updated_at"),
    }


def parse_skill_state_row(row: Mapping) -> dict:
    return {
        "id": row["id"],
        "user_id": row["user_id"],
        "skill_name": row["skill_name"],
        "state": parse_json_object(row.get("state_json")),
        "state_version": row.get("state_version") or "",
        "checkpoint_ref": row.get("checkpoint_ref") or "",
        "updated_at": row.get("updated_at"),
    }

