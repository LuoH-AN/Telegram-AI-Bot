"""Small bilingual text layer for Telegram UX surfaces."""

from __future__ import annotations


def language(update=None, context=None) -> str:
    if context is not None:
        selected = (context.user_data.get("ux_language") or "").strip().lower()
        if selected in {"zh", "en"}:
            return selected
    user = getattr(update, "effective_user", None)
    code = (getattr(user, "language_code", "") or "").lower()
    return "zh" if code.startswith("zh") else "en"


def pick(lang: str, zh: str, en: str) -> str:
    return zh if (lang or "").startswith("zh") else en
