"""Official Weixin channel protocol helpers."""

from .config import DEFAULT_BOT_TYPE, WECHAT_TEXT_LIMIT
from .ids import local_chat_id_for_wechat, local_user_id_for_wechat

__all__ = [
    "DEFAULT_BOT_TYPE",
    "WECHAT_TEXT_LIMIT",
    "local_user_id_for_wechat",
    "local_chat_id_for_wechat",
]
