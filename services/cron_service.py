"""Cron scheduler service — daemon thread that polls and executes cron tasks."""

import asyncio
import logging
import threading
import time
from datetime import datetime, timezone, timedelta

from cache.manager import cache

logger = logging.getLogger(__name__)

_CST = timezone(timedelta(hours=8))
_POLL_INTERVAL = 30  # seconds
_MAX_TOOL_ROUNDS = 5

# Track currently running tasks to prevent duplicate execution
_running_tasks: set[tuple[int, str]] = set()  # (user_id, task_name)
_running_tasks_lock = threading.Lock()


def _cron_matches(expr: str, dt: datetime) -> bool:
    """Check if a cron expression matches the given datetime.

    Supports: * (any), */N (step), N,M (list), N-M (range), exact value.
    Fields: minute hour day month weekday (0=Sun or 7=Sun, 1=Mon..6=Sat).
    """
    parts = expr.split()
    if len(parts) != 5:
        return False

    values = [dt.minute, dt.hour, dt.day, dt.month, dt.isoweekday() % 7]
    # isoweekday: Mon=1..Sun=7; % 7 makes Sun=0

    ranges = [
        (0, 59),   # minute
        (0, 23),   # hour
        (1, 31),   # day
        (1, 12),   # month
        (0, 6),    # weekday (0=Sun)
    ]

    for field_str, current, (lo, hi) in zip(parts, values, ranges):
        if not _field_matches(field_str, current, lo, hi):
            return False
    return True


def _field_matches(field: str, value: int, lo: int, hi: int) -> bool:
    """Check if a single cron field matches the given value."""
    for item in field.split(","):
        item = item.strip()
        if not item:
            continue

        # Handle step: */N or N-M/S
        step = 1
        if "/" in item:
            base, step_str = item.split("/", 1)
            try:
                step = int(step_str)
            except ValueError:
                continue
            item = base

        if item == "*":
            # Match any value with optional step
            if (value - lo) % step == 0:
                return True
        elif "-" in item:
            # Range: N-M
            try:
                start, end = item.split("-", 1)
                start, end = int(start), int(end)
            except ValueError:
                continue
            if start <= value <= end and (value - start) % step == 0:
                return True
        else:
            # Exact value
            try:
                exact = int(item)
            except ValueError:
                continue
            if exact == value:
                return True

    return False




def _execute_cron_task(bot, task: dict) -> None:
    """Execute a single cron task: call AI with the task prompt, send result to user."""
    user_id = task["user_id"]
    task_name = task["name"]
    task_key = (user_id, task_name)
    prompt = task["prompt"]

    logger.info("[user=%d] cron task '%s' started | prompt: %s", user_id, task_name, prompt[:100])

    # Heartbeat: independent timer thread that logs elapsed time every 10s
    task_start = time.time()
    _heartbeat_phase = ["init"]
    _heartbeat_stop = threading.Event()

    def _heartbeat():
        while not _heartbeat_stop.wait(10):
            elapsed = int(time.time() - task_start)
            logger.info("[user=%d] cron task '%s': %s (%ds)", user_id, task_name, _heartbeat_phase[0], elapsed)

    hb = threading.Thread(target=_heartbeat, daemon=True)
    hb.start()

    try:
        from services import get_user_settings, get_system_prompt
        from ai import get_ai_client
        from ai.openai_client import create_openai_client
        from tools import get_all_tools, process_tool_calls
        from utils import get_datetime_prompt, filter_thinking_content

        settings = get_user_settings(user_id)
        if not settings.get("api_key"):
            logger.warning("[user=%d] cron task '%s' skipped: no API key", user_id, task_name)
            return

        # Resolve cron_model — same logic as title_model
        cron_model_raw = settings.get("cron_model", "")
        api_key = settings["api_key"]
        base_url = settings["base_url"]
        cron_model = settings.get("model", "gpt-4o")

        if cron_model_raw:
            if ":" in cron_model_raw:
                provider_name, model_name = cron_model_raw.split(":", 1)
                presets = settings.get("api_presets", {})
                preset = None
                for k, v in presets.items():
                    if k.lower() == provider_name.lower():
                        preset = v
                        break
                if preset:
                    api_key = preset["api_key"]
                    base_url = preset["base_url"]
                    cron_model = model_name or preset.get("model", cron_model)
                else:
                    logger.warning("[user=%d] cron_model provider '%s' not found", user_id, provider_name)
            else:
                cron_model = cron_model_raw

        if cron_model_raw:
            client = create_openai_client(api_key=api_key, base_url=base_url)
        else:
            client = get_ai_client(user_id)

        enabled_tools = settings.get("enabled_tools", "memory,search,fetch,wikipedia")

        # Build system prompt
        system_prompt = get_system_prompt(user_id)
        system_prompt += "\n\n" + get_datetime_prompt()
        system_prompt += (
            "\n\nYou are executing a scheduled task. Provide a concise, useful response. "
            "Use available tools (search, fetch, etc.) as needed to fulfill the task."
        )

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": prompt},
        ]

        tools = get_all_tools(enabled_tools=enabled_tools)

        # Non-streaming AI call with tool loop (max 2 rounds)
        full_response = ""
        last_text_response = ""
        tool_results_pending = False
        for round_num in range(_MAX_TOOL_ROUNDS + 1):
            _heartbeat_phase[0] = f"waiting for AI (round {round_num + 1})"
            chunks = list(client.chat_completion(
                messages=messages,
                model=cron_model,
                temperature=settings["temperature"],
                stream=False,
                tools=tools if round_num < _MAX_TOOL_ROUNDS else None,
            ))

            if not chunks:
                break

            chunk = chunks[0]
            content = chunk.content or ""
            full_response = content

            if content.strip():
                last_text_response = content
                tool_results_pending = False

            if not chunk.tool_calls:
                break

            # Process tool calls
            tool_names = [tc.name for tc in chunk.tool_calls]
            _heartbeat_phase[0] = f"running tools: {', '.join(tool_names)}"
            tool_results = process_tool_calls(user_id, chunk.tool_calls, enabled_tools=enabled_tools)

            # Add assistant message with tool calls
            assistant_msg = {
                "role": "assistant",
                "content": content or None,
                "tool_calls": [
                    {
                        "id": tc.id,
                        "type": "function",
                        "function": {"name": tc.name, "arguments": tc.arguments},
                    }
                    for tc in chunk.tool_calls
                ],
            }
            messages.append(assistant_msg)
            messages.extend(tool_results)
            tool_results_pending = True

        # If loop ended with pending tool results, make one final call without tools
        if tool_results_pending:
            _heartbeat_phase[0] = "waiting for AI (final)"
            messages.append({
                "role": "user",
                "content": "Please respond based on the information you have gathered above. Do not attempt to call any more tools.",
            })
            chunks = list(client.chat_completion(
                messages=messages,
                model=cron_model,
                temperature=settings["temperature"],
                stream=False,
                tools=None,
            ))
            if chunks and chunks[0].content:
                full_response = chunks[0].content
                last_text_response = full_response

        # Clean response
        final_text = filter_thinking_content(full_response).strip()
        if not final_text and last_text_response:
            final_text = filter_thinking_content(last_text_response).strip()
        if not final_text:
            final_text = "(Scheduled task produced no output)"

        # Prepend task header
        result_text = f"[Scheduled: {task_name}]\n\n{final_text}"

        # Send to user via Telegram
        _heartbeat_phase[0] = "sending message"
        _send_message(bot, user_id, result_text)

        # Update last_run_at
        now = datetime.now(_CST)
        cache.update_cron_last_run(user_id, task_name, now)

        logger.info("[user=%d] cron task '%s' completed successfully (%ds)", user_id, task_name, int(time.time() - task_start))

    except Exception as e:
        logger.exception("[user=%d] cron task '%s' failed (%ds)", user_id, task_name, int(time.time() - task_start))
        try:
            _send_message(bot, user_id, f"[Scheduled: {task_name}]\n\nError: {e}")
        except Exception:
            logger.exception("[user=%d] failed to send cron error message", user_id)
    finally:
        _heartbeat_stop.set()
        hb.join(timeout=1)
        with _running_tasks_lock:
            _running_tasks.discard(task_key)


def _send_message(bot, chat_id: int, text: str) -> None:
    """Send a message from a background thread.

    Uses run_coroutine_threadsafe to schedule the send on the main event loop,
    reusing the bot's existing httpx connection pool.  This avoids both
    'Event loop is closed' errors and DNS resolution issues in containers.
    """
    from utils.formatters import markdown_to_telegram_html, split_message
    from telegram.constants import ParseMode

    html_text = markdown_to_telegram_html(text)

    # Split if too long (Telegram limit 4096)
    chunks = split_message(html_text, max_length=4096)

    loop = _main_loop
    if loop is None or loop.is_closed():
        logger.error("Main event loop not available, cannot send cron message")
        return

    for chunk in chunks:
        future = asyncio.run_coroutine_threadsafe(
            bot.send_message(chat_id=chat_id, text=chunk, parse_mode=ParseMode.HTML),
            loop,
        )
        future.result(timeout=60)


def _scheduler_loop(bot) -> None:
    """Background loop that checks cron tasks every POLL_INTERVAL seconds."""
    while True:
        time.sleep(_POLL_INTERVAL)
        try:
            now = datetime.now(_CST)
            tasks = cache.get_all_cron_tasks()

            for task in tasks:
                if not task.get("enabled", True):
                    continue

                expr = task.get("cron_expression", "")
                if not _cron_matches(expr, now):
                    continue

                # Avoid re-running within the same minute
                last_run = task.get("last_run_at")
                if last_run:
                    if hasattr(last_run, "minute"):
                        # datetime object
                        if (last_run.year == now.year and last_run.month == now.month
                                and last_run.day == now.day and last_run.hour == now.hour
                                and last_run.minute == now.minute):
                            continue

                # Skip if already running
                task_key = (task["user_id"], task["name"])
                with _running_tasks_lock:
                    if task_key in _running_tasks:
                        continue
                    _running_tasks.add(task_key)

                # Execute in a separate thread to avoid blocking the scheduler
                thread = threading.Thread(
                    target=_execute_cron_task,
                    args=(bot, task),
                    daemon=True,
                )
                thread.start()

        except Exception:
            logger.exception("Cron scheduler error")


_bot_ref = None
_main_loop = None


def set_main_loop(loop) -> None:
    """Store reference to the main asyncio event loop (called from post_init)."""
    global _main_loop
    _main_loop = loop


def start_cron_scheduler(bot) -> None:
    """Start the cron scheduler daemon thread."""
    global _bot_ref
    _bot_ref = bot
    thread = threading.Thread(target=_scheduler_loop, args=(bot,), daemon=True)
    thread.start()
    logger.info("Cron scheduler started (poll interval: %ds)", _POLL_INTERVAL)


def run_cron_task(user_id: int, task_name: str) -> str:
    """Manually trigger a cron task by name. Called from CronTool.execute (sync thread).

    Returns a status message. The actual AI execution + Telegram delivery
    happens in a background thread (same as scheduled runs).
    """
    if _bot_ref is None:
        return "Error: Bot is not initialized yet."

    tasks = cache.get_cron_tasks(user_id)
    task = next((t for t in tasks if t["name"] == task_name), None)
    if task is None:
        return f"Error: Task '{task_name}' not found."

    thread = threading.Thread(
        target=_execute_cron_task,
        args=(_bot_ref, task),
        daemon=True,
    )
    thread.start()
    return f"Task '{task_name}' triggered. The result will be sent as a separate message."
