"""Write-side log recording operations."""

import json
import logging

from database.db import get_connection

logger = logging.getLogger(__name__)


def _execute_insert(sql: str, params: tuple) -> None:
    try:
        conn = get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute(sql, params)
            conn.commit()
        finally:
            conn.close()
    except Exception:
        logger.exception("Failed to record log entry")


def record_ai_interaction(
    user_id: int,
    model: str | None = None,
    prompt_tokens: int = 0,
    completion_tokens: int = 0,
    total_tokens: int = 0,
    tool_calls: list[str] | None = None,
    latency_ms: int | None = None,
    persona_name: str | None = None,
):
    _execute_insert(
        """INSERT INTO user_logs
           (user_id, log_type, model, prompt_tokens, completion_tokens,
            total_tokens, latency_ms, persona_name)
           VALUES (%s, 'ai_interaction', %s, %s, %s, %s, %s, %s)""",
        (user_id, model, prompt_tokens, completion_tokens, total_tokens, latency_ms, persona_name),
    )


def record_error(user_id: int, error_message: str, error_context: str | None = None, model: str | None = None, persona_name: str | None = None):
    _execute_insert(
        """INSERT INTO user_logs
           (user_id, log_type, error_message, error_context, model, persona_name)
           VALUES (%s, 'error', %s, %s, %s, %s)""",
        (user_id, error_message, error_context, model, persona_name),
    )


def record_terminal_command(user_id: int, *, command: str, exit_code: int, cwd: str, stdout: str, stderr: str, blocked: bool = False):
    detail = {"command": command, "exit_code": exit_code, "cwd": cwd, "stdout": stdout, "stderr": stderr, "blocked": blocked}
    _execute_insert(
        """INSERT INTO user_logs
           (user_id, log_type, error_message, error_context)
           VALUES (%s, 'terminal_command', %s, %s)""",
        (user_id, command, json.dumps(detail, ensure_ascii=False)),
    )
