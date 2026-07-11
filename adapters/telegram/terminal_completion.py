"""Automatic Agent continuation for completed persistent terminal sessions."""

from __future__ import annotations

import asyncio
import logging

from telegram.constants import ParseMode

from adapters.telegram.bot_api import send_rich_message
from domain.services import (
    add_assistant_message,
    add_token_usage,
    conversation_slot,
    get_conversation,
    get_system_prompt,
    get_user_settings,
)
from domain.services.queue import register_response, unregister_response
from infrastructure.ai import get_ai_client
from infrastructure.cache import cache
from infrastructure.config import TELEGRAM_RICH_MESSAGES, VALID_REASONING_EFFORTS
from infrastructure.tools.builtin.terminal.store import (
    acknowledge_completion_event,
    claim_completion_events,
    claim_ready_completion_event,
    claim_ready_completion_events,
    get_session as get_terminal_session,
    mark_completion_delivered,
    release_completion_event,
    release_completion_delivery,
    save_completion_response,
)
from infrastructure.tools.core import ToolContext
from shared.utils.ai import estimate_tokens, estimate_tokens_str
from shared.utils.files import get_datetime_prompt
from shared.utils.format import (
    build_rich_message,
    markdown_to_telegram_html,
    should_use_rich_message,
    split_message,
)

from .handlers.messages.chat.generate import generate_with_tools

logger = logging.getLogger(__name__)
POLL_SECONDS = 2


class _NoopPump:
    async def drain(self) -> None:
        return None


class _NoopOutbound:
    async def deliver_final(self, _text: str) -> bool:
        return True


class _HeadlessRuntime:
    def __init__(self) -> None:
        self.render_pump = _NoopPump()
        self.outbound = _NoopOutbound()

    async def stream_update(self, _text: str) -> bool:
        return True

    async def status_update(self, _text: str) -> bool:
        return True

    async def prepare_tool_boundary(self, _text: str) -> bool:
        return True

    def clear_placeholder(self) -> None:
        return None

    def tool_event_callback(self, _event: dict) -> None:
        return None


def _completion_event_text(job: dict) -> str:
    exit_label = (
        f"exit code {job['exit_code']}"
        if job.get("exit_code") is not None
        else f"status {job['status']}"
    )
    return (
        "[Automatic terminal completion event]\n"
        f"Persistent terminal session {job['session_id']} finished with {exit_label}.\n"
        "Inspect it with terminal_process poll. Recover the user's original goal from the "
        "conversation, continue the work autonomously, run any safe follow-up checks or fixes, "
        "and only then give the user a concise final update. Do not merely announce that the "
        "command finished. If progress is blocked by an approval or user decision, explain the "
        "specific blocker."
    )


async def _generate_continuation(job: dict) -> tuple[str, dict]:
    user_id = int(job["user_id"])
    chat_id = int(job["chat_id"])
    session_id = int(job["conversation_id"])
    session = cache.get_session_by_id(session_id)
    if not session or int(session.get("user_id") or 0) != user_id:
        raise RuntimeError("owning conversation no longer exists")
    settings = get_user_settings(user_id)
    if not settings.get("api_key"):
        raise RuntimeError("user has no configured API key")
    persona_name = session.get("persona_name") or "default"
    reasoning_effort = str(settings.get("reasoning_effort", "") or "").strip().lower()
    if reasoning_effort not in VALID_REASONING_EFFORTS:
        settings = dict(settings)
        settings["reasoning_effort"] = ""
    tool_context = ToolContext(
        user_id=user_id,
        chat_id=chat_id,
        session_id=session_id,
        env={"terminal_completion_session_id": job["session_id"]},
    )
    conversation_key = f"telegram:{chat_id}:{user_id}:{session_id}"
    response_key = f"{conversation_key}:terminal:{job['session_id']}"
    current_task = asyncio.current_task()
    if current_task:
        register_response(response_key, task=current_task, pump=None)
    try:
        async with conversation_slot(conversation_key):
            current = get_terminal_session(job["session_id"])
            if not current or not current.get("notify_on_exit"):
                return "", {}
            latest_session = cache.get_session_by_id(session_id)
            if not latest_session or int(latest_session.get("user_id") or 0) != user_id:
                raise RuntimeError("owning conversation no longer exists")
            persona_name = latest_session.get("persona_name") or persona_name
            system_prompt = get_system_prompt(user_id, persona_name, session_id)
            system_prompt += "\n\n" + get_datetime_prompt()
            system_prompt += (
                "\n\nYou are running because a persistent terminal task completed. This is an "
                "automatic continuation of the existing conversation, not a new user request. "
                "Use tools until the original task is genuinely complete."
            )
            messages = [{"role": "system", "content": system_prompt}]
            messages.extend(list(get_conversation(session_id)))
            messages.append({"role": "user", "content": _completion_event_text(job)})
            generated = await generate_with_tools(
                client=get_ai_client(user_id),
                messages=messages,
                settings=settings,
                user_id=user_id,
                ctx=f"[terminal={job['session_id']} user={user_id}]",
                runtime=_HeadlessRuntime(),
                tool_context=tool_context,
            )
    finally:
        unregister_response(response_key)
    final_text = generated["final_text"]
    if final_text == "(Empty response)":
        final_text = (
            f"Terminal session `{job['session_id']}` finished, but the automatic continuation "
            "produced no response."
        )
    return final_text, generated


async def _send_result(bot, job: dict, text: str) -> None:
    chat_id = int(job["chat_id"])
    if TELEGRAM_RICH_MESSAGES and should_use_rich_message(text):
        rich_message = build_rich_message(text)
        if rich_message and await send_rich_message(chat_id, rich_message):
            return
    for chunk in split_message(text, max_length=4096):
        await bot.send_message(
            chat_id=chat_id,
            text=markdown_to_telegram_html(chunk),
            parse_mode=ParseMode.HTML,
        )


def _record_usage(job: dict, generated: dict, response: str) -> None:
    if not generated:
        return
    prompt_tokens = int(generated.get("total_prompt_tokens") or 0)
    completion_tokens = int(generated.get("total_completion_tokens") or 0)
    if not prompt_tokens and not completion_tokens:
        prompt_tokens = estimate_tokens(generated.get("messages") or [])
        completion_tokens = estimate_tokens_str(response)
    if prompt_tokens or completion_tokens:
        session = cache.get_session_by_id(int(job["conversation_id"])) or {}
        add_token_usage(
            int(job["user_id"]),
            prompt_tokens,
            completion_tokens,
            persona_name=session.get("persona_name") or "default",
        )


async def _deliver_ready(bot, job: dict) -> None:
    current = get_terminal_session(job["session_id"])
    if not current or current.get("delivery_status") != "delivering":
        return
    response = str(current.get("completion_response") or "").strip()
    if not response:
        return
    await _send_result(bot, current, response)
    mark_completion_delivered(current["session_id"])
    try:
        add_assistant_message(int(current["conversation_id"]), response)
    except Exception:
        logger.exception(
            "terminal completion delivered but conversation persistence failed: session=%s",
            current["session_id"],
        )
    logger.info("terminal completion delivered: session=%s", current["session_id"])


async def _process_claimed(bot, job: dict) -> None:
    try:
        response, generated = await _generate_continuation(job)
        if not response:
            return
        save_completion_response(job["session_id"], response)
        try:
            _record_usage(job, generated, response)
        except Exception:
            logger.exception(
                "terminal continuation usage accounting failed: session=%s",
                job["session_id"],
            )
    except asyncio.CancelledError as exc:
        if any(str(arg) == "user-stop" for arg in exc.args):
            acknowledge_completion_event(job["session_id"])
        else:
            release_completion_event(job["session_id"], "automatic continuation interrupted")
        raise
    except Exception as exc:
        logger.exception("terminal automatic continuation failed: session=%s", job["session_id"])
        release_completion_event(job["session_id"], str(exc))
        current = get_terminal_session(job["session_id"])
        if current and current.get("delivery_status") == "failed":
            save_completion_response(
                job["session_id"],
                f"Terminal session `{job['session_id']}` finished, but automatic continuation "
                f"failed after several attempts: {exc}",
            )
        return

    ready = claim_ready_completion_event(job["session_id"])
    if not ready:
        return
    try:
        await _deliver_ready(bot, ready)
    except asyncio.CancelledError:
        raise
    except Exception as exc:
        release_completion_delivery(job["session_id"], str(exc))
        logger.exception("terminal completion delivery failed: session=%s", job["session_id"])


async def monitor_terminal_completions(bot) -> None:
    logger.info("Terminal completion monitor started (poll=%ss)", POLL_SECONDS)
    while True:
        try:
            ready = await asyncio.to_thread(claim_ready_completion_events, limit=10)
            for job in ready:
                try:
                    await _deliver_ready(bot, job)
                except Exception as exc:
                    await asyncio.to_thread(
                        release_completion_delivery,
                        job["session_id"],
                        str(exc),
                    )
                    logger.exception(
                        "terminal completion delivery failed: session=%s",
                        job["session_id"],
                    )
            claimed = await asyncio.to_thread(claim_completion_events, limit=4)
            if claimed:
                results = await asyncio.gather(
                    *(_process_claimed(bot, job) for job in claimed),
                    return_exceptions=True,
                )
                for result in results:
                    if isinstance(result, BaseException) and not isinstance(
                        result, asyncio.CancelledError
                    ):
                        logger.error("Terminal completion task failed: %r", result)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("Terminal completion monitor iteration failed")
        await asyncio.sleep(POLL_SECONDS)


def start_terminal_completion_monitor(application) -> asyncio.Task:
    task = asyncio.create_task(
        monitor_terminal_completions(application.bot),
        name="terminal-completion-monitor",
    )
    application.bot_data["terminal_completion_monitor"] = task
    return task


async def stop_terminal_completion_monitor(application) -> None:
    task = application.bot_data.pop("terminal_completion_monitor", None)
    if task and not task.done():
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)
