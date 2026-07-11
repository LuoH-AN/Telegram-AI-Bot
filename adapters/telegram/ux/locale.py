"""Small bilingual text layer for Telegram UX surfaces."""

from __future__ import annotations


def language(update=None, context=None) -> str:
    if context is not None:
        selected = (context.user_data.get("ux_language") or "").strip().lower()
        if selected in {"zh", "en"}:
            return selected
    user = getattr(update, "effective_user", None)
    user_id = getattr(user, "id", None)
    if user_id is not None:
        from domain.services import get_user_settings

        selected = (get_user_settings(user_id).get("ux_language") or "").strip().lower()
        if selected in {"zh", "en"}:
            if context is not None:
                context.user_data["ux_language"] = selected
            return selected
    code = (getattr(user, "language_code", "") or "").lower()
    return "zh" if code.startswith("zh") else "en"


def pick(lang: str, zh: str, en: str) -> str:
    return zh if (lang or "").startswith("zh") else en
