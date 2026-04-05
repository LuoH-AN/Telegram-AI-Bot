"""State model for WeChat account runtime."""

from __future__ import annotations

from dataclasses import dataclass, field

from .constants import DEFAULT_BASE_URL


@dataclass
class WeChatAccountState:
    token: str = ""
    user_id: str = ""
    base_url: str = DEFAULT_BASE_URL
    get_updates_buf: str = ""
    peer_map: dict[str, str] = field(default_factory=dict)
    context_tokens: dict[str, str] = field(default_factory=dict)
