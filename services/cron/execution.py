"""Cron task execution flow."""

from __future__ import annotations

import logging
import time
from datetime import datetime

from cache.manager import cache
from config import VALID_REASONING_EFFORTS

from .client_factory import _create_task_client
from .delivery import _send_message
from .state import CST, running_tasks, running_tasks_lock
from .task_response import execute_ai_and_send

logger = logging.getLogger(__name__)


def _execute_cron_task(bot, task: dict) -> None:
    user_id = task["user_id"]
    task_name = task["name"]
    task_key = (user_id, task_name)
    prompt = task["prompt"]
    task_start = time.time()
    logger.info("[user=%d] cron task '%s' started | prompt: %s", user_id, task_name, prompt[:100])

    try:
        from services import get_user_settings

        settings = get_user_settings(user_id)
        if not settings.get("api_key"):
            logger.warning("[user=%d] cron task '%s' skipped: no API key", user_id, task_name)
            return

        reasoning_effort = str(settings.get("reasoning_effort", "") or "").strip().lower()
        if reasoning_effort not in VALID_REASONING_EFFORTS:
            reasoning_effort = ""

        client, cron_model = _create_task_client(user_id, settings.get("cron_model", ""), settings)
        execute_ai_and_send(
            bot,
            user_id=user_id,
            task_name=task_name,
            prompt=prompt,
            settings=settings,
            client=client,
            cron_model=cron_model,
            reasoning_effort=reasoning_effort,
        )

        cache.update_cron_last_run(user_id, task_name, datetime.now(CST))
        logger.info(
            "[user=%d] cron task '%s' completed successfully (%ds)",
            user_id,
            task_name,
            int(time.time() - task_start),
        )
    except Exception as exc:
        logger.exception(
            "[user=%d] cron task '%s' failed (%ds)",
            user_id,
            task_name,
            int(time.time() - task_start),
        )
        try:
            _send_message(bot, user_id, f"[Scheduled: {task_name}]\n\nError: {exc}")
        except Exception:
            logger.exception("[user=%d] failed to send cron error message", user_id)
    finally:
        with running_tasks_lock:
            running_tasks.discard(task_key)
