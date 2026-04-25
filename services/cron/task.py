"""AI response execution and message delivery for cron tasks."""

from __future__ import annotations

from .delivery import _detect_platform, _send_message
from .heartbeat import _heartbeat_monitor


def execute_ai_and_send(
    bot,
    *,
    user_id: int,
    task_name: str,
    prompt: str,
    settings: dict,
    client,
    cron_model: str,
    reasoning_effort: str,
) -> None:
    from services import get_system_prompt
    from utils.ai import filter_thinking_content
    from utils.files import get_datetime_prompt

    system_prompt = get_system_prompt(user_id)
    system_prompt += "\n\n" + get_datetime_prompt()
    platform_hint = _detect_platform(bot)
    system_prompt += "\n\nYou are executing a scheduled task. Provide a concise, useful response."
    system_prompt += f"\n\nScheduled task results are delivered via {platform_hint}."

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": prompt},
    ]

    with _heartbeat_monitor(user_id, task_name) as phase:
        full_response = ""
        last_text_response = ""
        while True:
            phase[0] = "waiting for AI"
            chunks = list(
                client.chat_completion(
                    messages=messages,
                    model=cron_model,
                    temperature=settings["temperature"],
                    reasoning_effort=reasoning_effort or None,
                    stream=False,
                )
            )
            if not chunks:
                break

            chunk = chunks[0]
            content = chunk.content or ""
            full_response = content
            if content.strip():
                last_text_response = content

            if chunk.finish_reason == "length":
                messages.append({"role": "assistant", "content": content})
                messages.append(
                    {
                        "role": "user",
                        "content": "Please continue and complete your response concisely.",
                    }
                )
                continue
            break

        final_text = filter_thinking_content(full_response).strip()
        if not final_text and last_text_response:
            final_text = filter_thinking_content(last_text_response).strip()
        if not final_text:
            final_text = "(Scheduled task produced no output)"

        phase[0] = "sending message"
        _send_message(bot, user_id, f"[Scheduled: {task_name}]\n\n{final_text}")
