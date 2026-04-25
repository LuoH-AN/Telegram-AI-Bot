"""Generic record parsers."""

from __future__ import annotations

from collections.abc import Mapping

from .json_utils import parse_json_list


def parse_persona_row(row: Mapping) -> dict:
    return {
        "name": row["name"],
        "system_prompt": row["system_prompt"],
        "current_session_id": row.get("current_session_id"),
    }


def parse_session_row(row: Mapping, *, user_id: int | None = None) -> dict:
    return {
        "id": row["id"],
        "user_id": row.get("user_id") or user_id,
        "persona_name": row["persona_name"],
        "title": row.get("title"),
        "created_at": str(row["created_at"]) if row.get("created_at") else None,
    }


def parse_conversation_row(row: Mapping) -> dict:
    return {"role": row["role"], "content": row["content"]}


def parse_token_row(row: Mapping) -> dict:
    return {
        "prompt_tokens": row.get("prompt_tokens") or 0,
        "completion_tokens": row.get("completion_tokens") or 0,
        "total_tokens": row.get("total_tokens") or 0,
        "token_limit": row.get("token_limit") or 0,
    }


def parse_memory_row(row: Mapping) -> dict:
    embedding = parse_json_list(row.get("embedding"))
    return {
        "id": row["id"],
        "user_id": row["user_id"],
        "content": row["content"],
        "source": row["source"],
        "embedding": embedding or None,
    }


def parse_cron_task_row(row: Mapping) -> dict:
    return {
        "id": row["id"],
        "user_id": row["user_id"],
        "name": row["name"],
        "cron_expression": row.get("cron_expression") or "",
        "prompt": row.get("prompt") or "",
        "enabled": bool(row.get("enabled", True)),
        "last_run_at": row.get("last_run_at"),
    }

