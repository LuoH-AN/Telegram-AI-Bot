"""Actionable user-facing AI error classification."""

from __future__ import annotations

from telegram import InlineKeyboardButton, InlineKeyboardMarkup

from .locale import pick


def error_panel(exc: Exception, lang: str, *, user_id: int | None = None) -> tuple[str, InlineKeyboardMarkup]:
    raw = str(exc or "")
    lowered = raw.lower()
    rows = []
    retry_callback = f"ux:retry:{user_id}" if user_id is not None else "ux:retry"
    if any(token in lowered for token in ("api key", "authentication", "unauthorized", "401", "invalid_api_key")):
        text = pick(lang, "🔑 **API 验证失败**\n\n请检查 API Key 和服务地址。", "🔑 **API authentication failed**\n\nCheck the API key and endpoint.")
        rows.append([InlineKeyboardButton(pick(lang, "🔌 检查 API 设置", "🔌 Check API settings"), callback_data="ux:settings:connection")])
    elif any(token in lowered for token in ("rate limit", "too many requests", "429")):
        text = pick(lang, "⏳ **请求过于频繁**\n\n服务商暂时限流，请稍后重试。", "⏳ **Rate limited**\n\nThe provider is temporarily limiting requests. Try again shortly.")
        rows.append([InlineKeyboardButton(pick(lang, "🔄 重试", "🔄 Retry"), callback_data=retry_callback)])
    elif any(token in lowered for token in ("context length", "maximum context", "too many tokens", "context window")):
        text = pick(lang, "📚 **对话上下文过长**\n\n请新建会话，或清理当前会话后重试。", "📚 **Conversation context is too long**\n\nCreate a new chat or clear the current one, then retry.")
        rows.append([InlineKeyboardButton(pick(lang, "➕ 新会话", "➕ New chat"), callback_data="ux:chat:new"), InlineKeyboardButton(pick(lang, "💬 会话管理", "💬 Chats"), callback_data="ux:chat:0")])
    elif any(token in lowered for token in ("model", "not found", "does not exist", "unsupported")):
        text = pick(lang, "🤖 **模型不可用**\n\n请选择其他模型后重试。", "🤖 **Model unavailable**\n\nChoose another model and retry.")
        rows.append([InlineKeyboardButton(pick(lang, "🤖 选择模型", "🤖 Choose model"), callback_data="ux:settings:model")])
    elif any(token in lowered for token in ("timeout", "timed out", "connection", "network", "temporarily unavailable", "502", "503", "504")):
        text = pick(lang, "🌐 **服务暂时不可用**\n\n网络或上游服务发生超时，可以直接重试。", "🌐 **Service temporarily unavailable**\n\nThe network or provider timed out. You can retry now.")
        rows.append([InlineKeyboardButton(pick(lang, "🔄 重试", "🔄 Retry"), callback_data=retry_callback)])
    else:
        text = pick(lang, "❌ **生成失败**\n\n请求没有完成。可以重试，或检查设置。", "❌ **Generation failed**\n\nThe request did not complete. Retry or check your settings.")
        rows.append([InlineKeyboardButton(pick(lang, "🔄 重试", "🔄 Retry"), callback_data=retry_callback), InlineKeyboardButton(pick(lang, "⚙️ 设置", "⚙️ Settings"), callback_data="ux:settings")])
    rows.append([InlineKeyboardButton(pick(lang, "⬅️ 主菜单", "⬅️ Main menu"), callback_data="ux:menu")])
    return text, InlineKeyboardMarkup(rows)
