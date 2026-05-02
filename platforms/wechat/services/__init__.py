"""WeChat service package."""

from .official import (
    DEFAULT_BOT_TYPE,
    WECHAT_TEXT_LIMIT,
    local_chat_id_for_wechat,
    local_user_id_for_wechat,
)
from .runtime import WeChatRuntimeLike, get_wechat_runtime, set_wechat_runtime

__all__ = [
    "DEFAULT_BOT_TYPE",
    "WECHAT_TEXT_LIMIT",
    "local_user_id_for_wechat",
    "local_chat_id_for_wechat",
    "WeChatRuntimeLike",
    "set_wechat_runtime",
    "get_wechat_runtime",
]
