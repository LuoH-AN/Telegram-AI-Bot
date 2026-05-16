"""Decide whether to proactively reply in a QQ group chat."""

from __future__ import annotations

import random
import time
from dataclasses import dataclass

from ..config import QQ_GROUP_MENTION_ALIASES, logger
from .store import get_proactive_config


@dataclass(frozen=True)
class ProactiveDecision:
    should_reply: bool
    reason: str


def mention_target_is_self(raw_event: dict, self_id: int) -> bool:
    """Return True if the message @mentions the bot via CQ:at."""
    if not self_id:
        return False
    message = raw_event.get("message") if raw_event else None
    if not isinstance(message, list):
        return False
    self_str = str(self_id)
    for seg in message:
        if not isinstance(seg, dict):
            continue
        if seg.get("type") != "at":
            continue
        target = str(seg.get("data", {}).get("qq", ""))
        if target == self_str or target.lower() == "all":
            return True
    return False


def _reply_target_is_self(raw_event: dict, self_id: int) -> bool:
    """Return True when this message is a reply to one of the bot's messages."""
    if not self_id:
        return False
    message = raw_event.get("message") if raw_event else None
    if not isinstance(message, list):
        return False
    self_str = str(self_id)
    for seg in message:
        if not isinstance(seg, dict) or seg.get("type") != "reply":
            continue
        target = str(seg.get("data", {}).get("user_id") or seg.get("data", {}).get("qq") or "")
        if target == self_str:
            return True
    return False


def _matches_alias(text: str) -> bool:
    if not text:
        return False
    lowered = text.lower()
    for alias in QQ_GROUP_MENTION_ALIASES:
        if not alias:
            continue
        if alias.lower() in lowered:
            return True
    return False


def _matches_any(text: str, keywords: list[str]) -> bool:
    if not text or not keywords:
        return False
    lowered = text.lower()
    return any(kw and kw.lower() in lowered for kw in keywords)


def should_reply_in_group(
    *,
    group_id: int,
    text: str,
    raw_event: dict,
    self_id: int,
) -> ProactiveDecision:
    """Decide whether to reply to a non-command group message."""
    if mention_target_is_self(raw_event, self_id):
        return ProactiveDecision(True, "at-mention")
    if _reply_target_is_self(raw_event, self_id):
        return ProactiveDecision(True, "reply-to-bot")
    if _matches_alias(text):
        return ProactiveDecision(True, "alias")

    cfg = get_proactive_config(int(group_id))
    if not cfg.enabled:
        return ProactiveDecision(False, "disabled")
    if cfg.mute_until and cfg.mute_until > time.time():
        logger.debug("Proactive reply muted for group %s until %s", group_id, cfg.mute_until)
        return ProactiveDecision(False, "muted")
    if _matches_any(text, cfg.blacklist):
        return ProactiveDecision(False, "blacklist")
    if _matches_any(text, cfg.keywords):
        return ProactiveDecision(True, "keyword")
    if random.random() < cfg.probability:
        return ProactiveDecision(True, f"probability:{cfg.probability:.2f}")
    return ProactiveDecision(False, "probability-miss")
