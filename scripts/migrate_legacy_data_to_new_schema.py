#!/usr/bin/env python3
"""Migrate legacy user_settings/user_memories schema to current schema."""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import re
import sys
from collections.abc import Mapping
from pathlib import Path

import psycopg2
from psycopg2.extras import RealDictCursor, execute_values

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from config import (
    DATABASE_URL,
    DEFAULT_REASONING_EFFORT,
    DEFAULT_SHOW_THINKING,
    DEFAULT_TTS_ENDPOINT,
    DEFAULT_TTS_STYLE,
    DEFAULT_TTS_VOICE,
)
from database.schema_parts import (
    CREATE_MEMORIES_INDEX,
    CREATE_USER_MEMORIES_TABLE,
    CREATE_USER_PERSONA_TOKENS_TABLE,
    CREATE_USER_SETTINGS_TABLE,
)

VALID_STREAM_MODES = {"default", "time", "chars", "off"}
VALID_REASONING = {"none", "minimal", "low", "medium", "high", "xhigh"}
BIGINT_MAX = (1 << 63) - 1
REQUIRED_SETTINGS_COLUMNS = {
    "user_id",
    "api_key",
    "base_url",
    "model",
    "temperature",
    "reasoning_effort",
    "show_thinking",
    "token_limit",
    "current_persona",
    "tts_voice",
    "tts_style",
    "tts_endpoint",
    "api_presets",
    "title_model",
    "cron_model",
    "stream_mode",
    "global_prompt",
}
REQUIRED_MEMORIES_COLUMNS = {"id", "user_id", "content", "source", "embedding", "created_at"}
REQUIRED_TOKEN_COLUMNS = {"user_id", "persona_name", "prompt_tokens", "completion_tokens", "total_tokens", "token_limit"}


def _as_object(value) -> dict:
    if isinstance(value, Mapping):
        return dict(value)
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return {}
        try:
            parsed = json.loads(text)
        except Exception:
            return {}
        if isinstance(parsed, Mapping):
            return dict(parsed)
    return {}


def _as_json_text(value, *, default: str = "{}") -> str:
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return default
        try:
            json.loads(text)
            return text
        except Exception:
            return default
    if isinstance(value, (list, dict)):
        return json.dumps(value, ensure_ascii=False)
    return default


def _as_float(value, default: float) -> float:
    try:
        return float(value)
    except Exception:
        return default


def _as_int(value, default: int = 0) -> int:
    try:
        return int(value)
    except Exception:
        return default


def _as_bool(value, default: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return default
    if isinstance(value, (int, float)):
        return bool(value)
    text = str(value).strip().lower()
    if text in {"1", "true", "yes", "on", "y"}:
        return True
    if text in {"0", "false", "no", "off", "n"}:
        return False
    return default


def _table_exists(cur, table_name: str) -> bool:
    cur.execute(
        """
        SELECT EXISTS (
          SELECT 1
          FROM information_schema.tables
          WHERE table_schema='public' AND table_name=%s
        ) AS ok
        """,
        (table_name,),
    )
    row = cur.fetchone() or {}
    return bool(row.get("ok"))


def _table_columns(cur, table_name: str) -> list[str]:
    cur.execute(
        """
        SELECT column_name
        FROM information_schema.columns
        WHERE table_schema='public' AND table_name=%s
        ORDER BY ordinal_position
        """,
        (table_name,),
    )
    return [str(row["column_name"]) for row in (cur.fetchall() or [])]


class UserIdMapper:
    def __init__(self) -> None:
        self._used: set[int] = set()
        self._cache: dict[str, int] = {}

    def add_known(self, value) -> None:
        if value is None:
            return
        text = str(value).strip()
        if not re.fullmatch(r"-?\d+", text):
            return
        num = int(text)
        if 0 < num <= BIGINT_MAX:
            self._used.add(num)
            self._cache[text] = num

    def map(self, value) -> int:
        text = str(value).strip()
        if not text:
            raise ValueError("empty user id")
        cached = self._cache.get(text)
        if cached is not None:
            return cached
        if re.fullmatch(r"-?\d+", text):
            num = int(text)
            if 0 < num <= BIGINT_MAX:
                self._used.add(num)
                self._cache[text] = num
                return num
        num = int(hashlib.sha1(text.encode("utf-8")).hexdigest()[:15], 16)
        if num <= 0:
            num = 1
        while num in self._used:
            num += 1
            if num > BIGINT_MAX:
                num = 1
        self._used.add(num)
        self._cache[text] = num
        return num


def _seed_known_user_ids(cur, mapper: UserIdMapper) -> None:
    for table in ("user_personas", "user_sessions", "user_persona_tokens", "user_memories", "user_settings"):
        if not _table_exists(cur, table):
            continue
        cols = _table_columns(cur, table)
        id_col = "user_id" if "user_id" in cols else ("id" if table == "user_settings" and "id" in cols else None)
        if not id_col:
            continue
        cur.execute(f"SELECT {id_col} FROM {table}")
        for row in cur.fetchall() or []:
            mapper.add_known(row[id_col])


def _pick_model(row: Mapping) -> str:
    direct = str(row.get("model") or "").strip()
    if direct:
        return direct
    default_agent = _as_object(row.get("default_agent"))
    cfg = _as_object(default_agent.get("config"))
    model = str(cfg.get("model") or "").strip()
    if model:
        return model
    language_model = _as_object(row.get("language_model"))
    model = str(language_model.get("model") or "").strip()
    if model:
        return model
    return "gpt-4o"


def _pick_temperature(row: Mapping) -> float:
    if row.get("temperature") is not None:
        return _as_float(row.get("temperature"), 0.7)
    default_agent = _as_object(row.get("default_agent"))
    cfg = _as_object(default_agent.get("config"))
    if cfg.get("temperature") is not None:
        return _as_float(cfg.get("temperature"), 0.7)
    return 0.7


def _normalize_reasoning(value) -> str:
    text = str(value or DEFAULT_REASONING_EFFORT or "").strip().lower()
    return text if text in VALID_REASONING else ""


def _normalize_stream_mode(value) -> str:
    text = str(value or "").strip().lower()
    return text if text in VALID_STREAM_MODES else ""


def _transform_settings_row(row: Mapping, mapper: UserIdMapper) -> tuple:
    raw_user_id = row.get("user_id")
    if raw_user_id is None:
        raw_user_id = row.get("id")
    user_id = mapper.map(raw_user_id)
    tts = _as_object(row.get("tts"))
    key_vaults = _as_object(row.get("key_vaults"))
    api_key = str(row.get("api_key") or "").strip()
    base_url = str(row.get("base_url") or "").strip() or "https://api.openai.com/v1"
    if not api_key:
        api_key = str(key_vaults.get("api_key") or key_vaults.get("apiKey") or "").strip()

    return (
        user_id,
        api_key,
        base_url,
        _pick_model(row),
        _pick_temperature(row),
        _normalize_reasoning(row.get("reasoning_effort")),
        _as_bool(row.get("show_thinking"), DEFAULT_SHOW_THINKING),
        _as_int(row.get("token_limit"), 0),
        str(row.get("current_persona") or "default").strip() or "default",
        str(row.get("tts_voice") or tts.get("voice") or DEFAULT_TTS_VOICE),
        str(row.get("tts_style") or tts.get("style") or DEFAULT_TTS_STYLE),
        str(row.get("tts_endpoint") or tts.get("endpoint") or DEFAULT_TTS_ENDPOINT),
        _as_json_text(row.get("api_presets") or key_vaults, default="{}"),
        str(row.get("title_model") or ""),
        str(row.get("cron_model") or ""),
        _normalize_stream_mode(row.get("stream_mode")),
        str(row.get("global_prompt") or ""),
    )


def _transform_memory_row(row: Mapping, mapper: UserIdMapper) -> tuple:
    user_id = mapper.map(row.get("user_id"))
    content = (
        str(row.get("content") or "").strip()
        or str(row.get("details") or "").strip()
        or str(row.get("summary") or "").strip()
        or str(row.get("title") or "").strip()
    )
    source = (
        str(row.get("source") or "").strip()
        or str(row.get("memory_type") or "").strip()
        or str(row.get("memory_layer") or "").strip()
        or str(row.get("memory_category") or "").strip()
        or "user"
    )
    embedding = row.get("embedding")
    if embedding is None:
        embedding = row.get("details_vector_1024")
    if embedding is None:
        embedding = row.get("summary_vector_1024")
    if isinstance(embedding, (list, dict)):
        embedding = json.dumps(embedding, ensure_ascii=False)
    created_at = row.get("created_at") or row.get("captured_at")
    return (user_id, content, source, embedding, created_at)


def _migrate_user_settings(cur, mapper: UserIdMapper, *, dry_run: bool) -> bool:
    if not _table_exists(cur, "user_settings"):
        return False
    cols = set(_table_columns(cur, "user_settings"))
    if REQUIRED_SETTINGS_COLUMNS.issubset(cols) and "id" not in cols:
        print("user_settings: already new schema, skip")
        return False
    if "user_id" not in cols and "id" not in cols:
        raise RuntimeError(f"user_settings schema not recognized: {sorted(cols)}")

    order_col = "user_id" if "user_id" in cols else "id"
    cur.execute(f"SELECT * FROM user_settings ORDER BY {order_col}")
    old_rows = cur.fetchall() or []
    new_rows = []
    for row in old_rows:
        raw_user_id = row.get("user_id")
        if raw_user_id is None:
            raw_user_id = row.get("id")
        if raw_user_id is None:
            continue
        new_rows.append(_transform_settings_row(row, mapper))
    print(f"user_settings: migrate {len(new_rows)} rows")
    if dry_run:
        return True

    backup = f"user_settings_legacy_{dt.datetime.utcnow().strftime('%Y%m%d_%H%M%S')}"
    cur.execute(f"ALTER TABLE user_settings RENAME TO {backup}")
    cur.execute(CREATE_USER_SETTINGS_TABLE)
    if new_rows:
        execute_values(
            cur,
            """
            INSERT INTO user_settings (
              user_id, api_key, base_url, model, temperature, reasoning_effort, show_thinking,
              token_limit, current_persona, tts_voice, tts_style, tts_endpoint, api_presets,
              title_model, cron_model, stream_mode, global_prompt
            ) VALUES %s
            """,
            new_rows,
        )
    print(f"user_settings: done (backup={backup})")
    return True


def _migrate_user_memories(cur, mapper: UserIdMapper, *, dry_run: bool) -> bool:
    if not _table_exists(cur, "user_memories"):
        return False
    cols = set(_table_columns(cur, "user_memories"))
    if REQUIRED_MEMORIES_COLUMNS.issubset(cols):
        print("user_memories: already new schema, skip")
        return False
    if "user_id" not in cols:
        raise RuntimeError(f"user_memories schema not recognized: {sorted(cols)}")

    cur.execute("SELECT * FROM user_memories ORDER BY 1")
    old_rows = cur.fetchall() or []
    new_rows = [_transform_memory_row(row, mapper) for row in old_rows if row.get("user_id") is not None]
    print(f"user_memories: migrate {len(new_rows)} rows")
    if dry_run:
        return True

    backup = f"user_memories_legacy_{dt.datetime.utcnow().strftime('%Y%m%d_%H%M%S')}"
    cur.execute(f"ALTER TABLE user_memories RENAME TO {backup}")
    cur.execute(CREATE_USER_MEMORIES_TABLE)
    cur.execute(CREATE_MEMORIES_INDEX)
    if new_rows:
        execute_values(
            cur,
            """
            INSERT INTO user_memories (user_id, content, source, embedding, created_at)
            VALUES %s
            """,
            new_rows,
        )
    print(f"user_memories: done (backup={backup})")
    return True


def _transform_token_row(row: Mapping, mapper: UserIdMapper) -> tuple:
    return (
        mapper.map(row.get("user_id")),
        str(row.get("persona_name") or "default").strip() or "default",
        _as_int(row.get("prompt_tokens"), 0),
        _as_int(row.get("completion_tokens"), 0),
        _as_int(row.get("total_tokens"), 0),
        _as_int(row.get("token_limit"), 0),
    )


def _migrate_user_persona_tokens(cur, mapper: UserIdMapper, *, dry_run: bool) -> bool:
    if not _table_exists(cur, "user_persona_tokens"):
        return False
    cols = set(_table_columns(cur, "user_persona_tokens"))
    if REQUIRED_TOKEN_COLUMNS.issubset(cols):
        print("user_persona_tokens: already new schema, skip")
        return False
    required_base_cols = {"user_id", "persona_name", "prompt_tokens", "completion_tokens", "total_tokens"}
    if not required_base_cols.issubset(cols):
        raise RuntimeError(f"user_persona_tokens schema not recognized: {sorted(cols)}")

    cur.execute("SELECT * FROM user_persona_tokens ORDER BY 1, 2")
    old_rows = cur.fetchall() or []
    new_rows = []
    for row in old_rows:
        if row.get("user_id") is None:
            continue
        new_rows.append(_transform_token_row(row, mapper))
    print(f"user_persona_tokens: migrate {len(new_rows)} rows")
    if dry_run:
        return True

    backup = f"user_persona_tokens_legacy_{dt.datetime.utcnow().strftime('%Y%m%d_%H%M%S')}"
    cur.execute(f"ALTER TABLE user_persona_tokens RENAME TO {backup}")
    cur.execute(CREATE_USER_PERSONA_TOKENS_TABLE)
    if new_rows:
        execute_values(
            cur,
            """
            INSERT INTO user_persona_tokens (
              user_id, persona_name, prompt_tokens, completion_tokens, total_tokens, token_limit
            ) VALUES %s
            """,
            new_rows,
        )
    print(f"user_persona_tokens: done (backup={backup})")
    return True


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Migrate legacy DB tables to current schema")
    parser.add_argument("--dry-run", action="store_true", help="Only detect and print migration plan")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    conn = psycopg2.connect(DATABASE_URL)
    conn.autocommit = False
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            mapper = UserIdMapper()
            _seed_known_user_ids(cur, mapper)
            changed_settings = _migrate_user_settings(cur, mapper, dry_run=args.dry_run)
            changed_memories = _migrate_user_memories(cur, mapper, dry_run=args.dry_run)
            changed_tokens = _migrate_user_persona_tokens(cur, mapper, dry_run=args.dry_run)
        if args.dry_run:
            conn.rollback()
            print("dry-run complete")
        else:
            conn.commit()
            print(
                "migration complete "
                f"(settings_changed={changed_settings}, memories_changed={changed_memories}, "
                f"tokens_changed={changed_tokens})"
            )
        return 0
    except Exception as exc:
        conn.rollback()
        print(f"migration failed: {exc}")
        return 1
    finally:
        conn.close()


if __name__ == "__main__":
    raise SystemExit(main())
