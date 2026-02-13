"""TTS tool — generate speech audio and enqueue for Telegram delivery."""

import logging
import threading

from config import DEFAULT_TTS_STYLE, DEFAULT_TTS_VOICE
from services import get_user_settings
from services.tts_service import (
    DEFAULT_OUTPUT_FORMAT,
    DEFAULT_STYLE,
    guess_audio_extension,
    get_voice_list,
    normalize_tts_endpoint,
    synthesize_voice,
)

from .registry import BaseTool

logger = logging.getLogger(__name__)

MAX_TTS_TEXT_LENGTH = 2000

_PENDING_JOBS: dict[int, list[dict]] = {}
_PENDING_LOCK = threading.Lock()

TTS_SPEAK_TOOL = {
    "type": "function",
    "function": {
        "name": "tts_speak",
        "description": (
            "Convert text to speech and send as a voice message. "
            "Supports optional voice and speaking style."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "text": {
                    "type": "string",
                    "description": "Text content that should be spoken",
                },
                "voice_name": {
                    "type": "string",
                    "description": "Optional voice name, e.g. zh-CN-XiaoxiaoMultilingualNeural",
                },
                "style": {
                    "type": "string",
                    "description": "Optional style, e.g. general/chat/assistant/cheerful/sad",
                },
                "rate": {
                    "type": "string",
                    "description": "Optional speaking rate percentage, e.g. -10, 0, 15",
                },
                "pitch": {
                    "type": "string",
                    "description": "Optional pitch percentage, e.g. -5, 0, 8",
                },
                "output_format": {
                    "type": "string",
                    "description": "Optional output format",
                    "enum": [
                        "ogg-24khz-16bit-mono-opus",
                        "audio-24khz-48kbitrate-mono-mp3",
                    ],
                    "default": "ogg-24khz-16bit-mono-opus",
                },
            },
            "required": ["text"],
        },
    },
}

TTS_LIST_VOICES_TOOL = {
    "type": "function",
    "function": {
        "name": "tts_list_voices",
        "description": "List available TTS voices and styles.",
        "parameters": {
            "type": "object",
            "properties": {
                "locale": {
                    "type": "string",
                    "description": "Optional locale filter, e.g. zh-CN, en-US",
                },
                "limit": {
                    "type": "integer",
                    "description": "Maximum voices to return (default 20, max 50)",
                    "default": 20,
                },
            },
            "required": [],
        },
    },
}


def _enqueue_pending_tts_job(user_id: int, job: dict) -> None:
    with _PENDING_LOCK:
        _PENDING_JOBS.setdefault(user_id, []).append(job)


def drain_pending_tts_jobs(user_id: int) -> list[dict]:
    """Drain and return pending TTS jobs for a user."""
    with _PENDING_LOCK:
        return _PENDING_JOBS.pop(user_id, [])


def _format_voice_items(items: list[dict]) -> str:
    lines = []
    for idx, voice in enumerate(items, 1):
        styles = ", ".join(voice.get("StyleList") or []) or "general"
        lines.append(
            f"{idx}. {voice.get('ShortName', 'unknown')} | "
            f"locale={voice.get('Locale', 'unknown')} | "
            f"gender={voice.get('Gender', 'unknown')} | "
            f"styles={styles}"
        )
    return "\n".join(lines)


class TTSTool(BaseTool):
    """Tool for AI-triggered text-to-speech voice delivery."""

    @property
    def name(self) -> str:
        return "tts"

    def definitions(self) -> list[dict]:
        return [TTS_SPEAK_TOOL, TTS_LIST_VOICES_TOOL]

    def execute(self, user_id: int, tool_name: str, arguments: dict) -> str | None:
        if tool_name == "tts_speak":
            return self._speak(user_id, arguments)
        if tool_name == "tts_list_voices":
            return self._list_voices(arguments)
        return f"Unknown tts tool: {tool_name}"

    def _speak(self, user_id: int, arguments: dict) -> str:
        text = str(arguments.get("text", "")).strip()
        if not text:
            return "TTS failed: empty text."

        if len(text) > MAX_TTS_TEXT_LENGTH:
            return (
                f"TTS failed: text too long ({len(text)} chars). "
                f"Limit is {MAX_TTS_TEXT_LENGTH} chars."
            )

        settings = get_user_settings(user_id)

        # /set 设定优先：默认由用户设置控制音色和风格。
        configured_voice = str(settings.get("tts_voice", "")).strip()
        configured_style = str(settings.get("tts_style", "")).strip().lower()
        requested_voice = str(arguments.get("voice_name", "")).strip()
        requested_style = str(arguments.get("style", "")).strip().lower()

        voice_name = configured_voice or requested_voice or DEFAULT_TTS_VOICE
        style = configured_style or requested_style or DEFAULT_TTS_STYLE

        # 校验音色是否存在，不存在时回退到默认音色。
        fallback_note = ""
        voice_list = get_voice_list()
        if voice_list:
            short_names = {
                str(voice.get("ShortName", "")).strip()
                for voice in voice_list
                if voice.get("ShortName")
            }
            if voice_name not in short_names:
                fallback_voice = DEFAULT_TTS_VOICE
                if fallback_voice not in short_names and requested_voice in short_names:
                    fallback_voice = requested_voice
                fallback_note = (
                    f" Requested voice '{voice_name}' not found, fallback to '{fallback_voice}'."
                )
                voice_name = fallback_voice

        if not style:
            style = DEFAULT_STYLE

        rate = arguments.get("rate", "")
        pitch = arguments.get("pitch", "")
        output_format = str(arguments.get("output_format") or DEFAULT_OUTPUT_FORMAT).strip()
        endpoint_host = normalize_tts_endpoint(settings.get("tts_endpoint", ""))

        try:
            audio = synthesize_voice(
                text=text,
                voice_name=voice_name,
                style=style,
                rate=rate,
                pitch=pitch,
                output_format=output_format,
                endpoint_host=endpoint_host,
            )
        except Exception as e:
            logger.exception("tts_speak failed")
            return f"TTS failed: {e}"

        extension = guess_audio_extension(output_format)
        _enqueue_pending_tts_job(
            user_id,
            {
                "audio": audio,
                "filename": f"tts.{extension}",
                "caption": f"🎤 {voice_name} ({style})",
            },
        )

        return (
            "Voice generated and queued for delivery. "
            f"voice={voice_name}, style={style}, endpoint={endpoint_host or 'auto'}, chars={len(text)}.{fallback_note}"
        )

    def _list_voices(self, arguments: dict) -> str:
        locale = str(arguments.get("locale", "")).strip().lower()
        raw_limit = arguments.get("limit", 20)
        try:
            limit = int(raw_limit)
        except (TypeError, ValueError):
            limit = 20
        limit = max(1, min(limit, 50))

        voice_list = get_voice_list()
        if not voice_list:
            return "Failed to fetch voice list."

        filtered = voice_list
        if locale:
            filtered = [
                voice for voice in voice_list
                if str(voice.get("Locale", "")).lower() == locale
            ]

        if not filtered:
            return f"No voices found for locale: {locale}"

        shown = filtered[:limit]
        body = _format_voice_items(shown)
        return f"Available voices ({len(shown)}/{len(filtered)}):\n{body}"

    def get_instruction(self) -> str:
        return (
            "\n\nYou have TTS tools to generate voice messages.\n"
            "- Use tts_speak when user asks for spoken/voice output.\n"
            "- Prefer /set voice and /set style as defaults.\n"
            "- Do not set voice_name/style arguments unless user explicitly requests a temporary override.\n"
            "- Keep spoken text concise and natural.\n"
            "- Use tts_list_voices when user asks what voices are available."
        )
