"""Per-group proactive reply configuration with DB persistence."""

from __future__ import annotations

import time
from dataclasses import dataclass, field

from database.db import get_connection

from ..config import logger


@dataclass
class ProactiveConfig:
    enabled: bool = False
    probability: float = 0.1
    keywords: list[str] = field(default_factory=list)
    blacklist: list[str] = field(default_factory=list)
    mute_until: int = 0


_cache: dict[int, ProactiveConfig] = {}


def _split_csv(value: str) -> list[str]:
    return [item.strip() for item in (value or "").split(",") if item.strip()]


def _join_csv(items: list[str]) -> str:
    return ",".join(item.strip() for item in items if item.strip())


def load_proactive_configs() -> None:
    """Load all proactive reply configs into the in-memory cache."""
    try:
        conn = get_connection()
        if conn is None:
            return
        with conn.cursor() as cur:
            cur.execute(
                "SELECT group_id, enabled, probability, keywords, blacklist, mute_until "
                "FROM onebot_proactive_config"
            )
            for row in cur.fetchall():
                _cache[int(row["group_id"])] = ProactiveConfig(
                    enabled=bool(row["enabled"]),
                    probability=float(row["probability"]),
                    keywords=_split_csv(row["keywords"]),
                    blacklist=_split_csv(row["blacklist"]),
                    mute_until=int(row["mute_until"] or 0),
                )
        logger.info("Loaded %d proactive reply config(s)", len(_cache))
    except Exception:
        logger.debug("onebot_proactive_config table not yet created, skipping load")


def get_proactive_config(group_id: int) -> ProactiveConfig:
    cfg = _cache.get(int(group_id))
    return cfg if cfg is not None else ProactiveConfig()


def _persist(group_id: int, cfg: ProactiveConfig) -> None:
    try:
        conn = get_connection()
        if conn is None:
            return
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO onebot_proactive_config "
                "(group_id, enabled, probability, keywords, blacklist, mute_until) "
                "VALUES (%s, %s, %s, %s, %s, %s) "
                "ON CONFLICT (group_id) DO UPDATE SET "
                "enabled = EXCLUDED.enabled, probability = EXCLUDED.probability, "
                "keywords = EXCLUDED.keywords, blacklist = EXCLUDED.blacklist, "
                "mute_until = EXCLUDED.mute_until, updated_at = CURRENT_TIMESTAMP",
                (
                    int(group_id),
                    bool(cfg.enabled),
                    float(cfg.probability),
                    _join_csv(cfg.keywords),
                    _join_csv(cfg.blacklist),
                    int(cfg.mute_until),
                ),
            )
        conn.commit()
    except Exception:
        logger.exception("Failed to persist proactive config for group %s", group_id)


def update_proactive_config(group_id: int, **changes) -> ProactiveConfig:
    cfg = get_proactive_config(group_id)
    new_cfg = ProactiveConfig(
        enabled=bool(changes.get("enabled", cfg.enabled)),
        probability=float(changes.get("probability", cfg.probability)),
        keywords=list(changes.get("keywords", cfg.keywords)),
        blacklist=list(changes.get("blacklist", cfg.blacklist)),
        mute_until=int(changes.get("mute_until", cfg.mute_until)),
    )
    new_cfg.probability = max(0.0, min(1.0, new_cfg.probability))
    _cache[int(group_id)] = new_cfg
    _persist(int(group_id), new_cfg)
    return new_cfg


def set_mute_until(group_id: int, minutes: int) -> int:
    until = int(time.time()) + max(1, int(minutes)) * 60
    update_proactive_config(group_id, mute_until=until)
    return until


def clear_mute(group_id: int) -> None:
    update_proactive_config(group_id, mute_until=0)
