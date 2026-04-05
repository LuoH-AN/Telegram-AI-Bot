"""Official Weixin HTTP client facade."""

from __future__ import annotations

import logging
from pathlib import Path

import requests

from .client_base import ClientBaseMixin
from .client_media_download import ClientMediaDownloadMixin
from .client_media_send import ClientMediaSendMixin
from .client_messages import ClientMessagesMixin
from .constants import DEFAULT_BASE_URL, DEFAULT_BOT_TYPE, DEFAULT_CDN_BASE_URL
from .state_store import WeChatStateStore

logger = logging.getLogger(__name__)


class WeChatOfficialClient(
    ClientBaseMixin,
    ClientMessagesMixin,
    ClientMediaSendMixin,
    ClientMediaDownloadMixin,
):
    """HTTP client for the official Weixin bot protocol."""

    def __init__(
        self,
        *,
        state_dir: str | Path,
        base_url: str = DEFAULT_BASE_URL,
        cdn_base_url: str = DEFAULT_CDN_BASE_URL,
        bot_type: str = DEFAULT_BOT_TYPE,
        account_key: str = "default",
    ):
        self.base_url = base_url.rstrip("/")
        self.cdn_base_url = cdn_base_url.rstrip("/")
        self.bot_type = bot_type
        self.state_store = WeChatStateStore(state_dir, account_key=account_key, logger=logger)
        self._session = requests.Session()
        self._logger = logger
