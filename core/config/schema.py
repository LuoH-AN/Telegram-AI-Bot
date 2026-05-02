"""Configuration schema with validation."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any


class ConfigurationError(Exception):
    """Invalid or missing configuration."""
    pass


@dataclass
class DatabaseConfig:
    """Database configuration."""
    url: str

    @classmethod
    def from_env(cls) -> "DatabaseConfig":
        url = os.getenv("DATABASE_URL", "")
        return cls(url=url)

    def validate(self) -> None:
        if not self.url:
            raise ConfigurationError("DATABASE_URL is required")


@dataclass
class TelegramConfig:
    """Telegram bot configuration."""
    bot_token: str
    api_base: str | None = None
    rate_limit_global: float = 25.0
    rate_limit_per_chat: float = 1.0

    @classmethod
    def from_env(cls) -> "TelegramConfig":
        token = os.getenv("TELEGRAM_BOT_TOKEN", "")
        return cls(
            bot_token=token,
            api_base=os.getenv("TELEGRAM_API_BASE") or None,
            rate_limit_global=float(os.getenv("TELEGRAM_SEND_GLOBAL_RATE", "25")),
            rate_limit_per_chat=float(os.getenv("TELEGRAM_SEND_PER_CHAT_RATE", "1")),
        )

    def validate(self) -> None:
        if not self.bot_token:
            raise ConfigurationError("TELEGRAM_BOT_TOKEN is required for Telegram platform")


@dataclass
class WeChatConfig:
    """WeChat platform configuration."""
    enabled: bool = False
    command_prefix: str = "/"
    state_dir: str = "runtime/wechat"
    login_access_token: str = ""

    @classmethod
    def from_env(cls) -> "WeChatConfig":
        return cls(
            enabled=os.getenv("WECHAT_ENABLED", "").strip().lower() in {"1", "true", "yes", "on"},
            command_prefix=os.getenv("WECHAT_COMMAND_PREFIX", "/").strip() or "/",
            state_dir=os.getenv("WECHAT_STATE_DIR", "runtime/wechat").strip() or "runtime/wechat",
            login_access_token=os.getenv("WECHAT_LOGIN_ACCESS_TOKEN", "").strip(),
        )


@dataclass
class OneBotConfig:
    """OneBot/QQ platform configuration."""
    enabled: bool = False
    mode: str = "client"  # "client", "server", "ws"
    ws_url: str = "ws://127.0.0.1:6099"
    http_url: str = "http://127.0.0.1:3000"
    access_token: str = ""
    command_prefix: str = "/"

    @classmethod
    def from_env(cls) -> "OneBotConfig":
        return cls(
            enabled=os.getenv("ONEBOT_ENABLED", "").strip().lower() in {"1", "true", "yes", "on"},
            mode=os.getenv("ONEBOT_MODE", "client").strip().lower(),
            ws_url=os.getenv("ONEBOT_WS_URL", "ws://127.0.0.1:6099").strip(),
            http_url=os.getenv("ONEBOT_HTTP_URL", "http://127.0.0.1:3000").strip(),
            access_token=os.getenv("ONEBOT_ACCESS_TOKEN", "").strip(),
            command_prefix=os.getenv("QQ_COMMAND_PREFIX", "/").strip() or "/",
        )


@dataclass
class OpenAIConfig:
    """OpenAI API configuration."""
    api_key: str = ""
    base_url: str = ""
    model: str = "gpt-4o-mini"
    temperature: float = 0.7

    @classmethod
    def from_env(cls) -> "OpenAIConfig":
        return cls(
            api_key=os.getenv("OPENAI_API_KEY", "").strip(),
            base_url=os.getenv("OPENAI_BASE_URL", "").strip(),
            model=os.getenv("OPENAI_MODEL", "gpt-4o-mini").strip(),
            temperature=float(os.getenv("OPENAI_TEMPERATURE", "0.7")),
        )


@dataclass
class AppConfig:
    """Root application configuration."""
    database: DatabaseConfig
    telegram: TelegramConfig | None = None
    wechat: WeChatConfig = field(default_factory=WeChatConfig)
    onebot: OneBotConfig = field(default_factory=OneBotConfig)
    openai: OpenAIConfig = field(default_factory=OpenAIConfig)

    @classmethod
    def from_env(cls) -> "AppConfig":
        telegram_token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
        return cls(
            database=DatabaseConfig.from_env(),
            telegram=TelegramConfig.from_env() if telegram_token else None,
            wechat=WeChatConfig.from_env(),
            onebot=OneBotConfig.from_env(),
            openai=OpenAIConfig.from_env(),
        )

    def validate(self) -> None:
        self.database.validate()
        if self.telegram:
            self.telegram.validate()

    @property
    def any_platform_enabled(self) -> bool:
        """Check if any platform is configured."""
        return bool(self.telegram) or self.wechat.enabled or self.onebot.enabled
