#!/usr/bin/env python3
"""One-off migration script from legacy DB layout to the new session-based schema.

Usage:
    python migrate_legacy_tables.py
    python migrate_legacy_tables.py --dry-run
    python migrate_legacy_tables.py --cleanup-legacy

What it migrates:
1. Adds missing columns required by the new schema.
2. Ensures base tables/indexes exist.
3. Migrates legacy conversation rows without session_id into per-persona sessions.
4. Migrates legacy token table `user_token_usage` into `user_persona_tokens`.
5. Ensures each persona has a valid `current_session_id`.
6. Optionally drops legacy artifacts (`--cleanup-legacy`).
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
from pathlib import Path

try:
    import psycopg2 as pg_driver
except ModuleNotFoundError:
    try:
        import psycopg as pg_driver  # type: ignore[no-redef]
    except ModuleNotFoundError:
        pg_driver = None

LOGGER = logging.getLogger("legacy_migration")


def _load_dotenv_fallback() -> None:
    """Load .env file without external dependency (best-effort)."""
    env_path = Path(__file__).resolve().parent / ".env"
    if not env_path.exists():
        return

    for raw in env_path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


_load_dotenv_fallback()

DEFAULT_SYSTEM_PROMPT = os.getenv("OPENAI_SYSTEM_PROMPT", "You are a helpful assistant.")
DEFAULT_ENABLED_TOOLS = os.getenv("ENABLED_TOOLS", "memory,search,fetch,wikipedia,tts")
DEFAULT_TTS_VOICE = os.getenv("TTS_VOICE", "zh-CN-XiaoxiaoMultilingualNeural")
DEFAULT_TTS_STYLE = os.getenv("TTS_STYLE", "general")
DEFAULT_TTS_ENDPOINT = os.getenv("TTS_ENDPOINT", "")

CREATE_USER_SETTINGS_TABLE = """
    CREATE TABLE IF NOT EXISTS user_settings (
        user_id BIGINT PRIMARY KEY,
        api_key TEXT,
        base_url TEXT,
        model TEXT,
        temperature REAL,
        token_limit BIGINT DEFAULT 0,
        current_persona TEXT DEFAULT 'default',
        enabled_tools TEXT,
        tts_voice TEXT,
        tts_style TEXT,
        tts_endpoint TEXT,
        api_presets TEXT,
        title_model TEXT
    )
"""

CREATE_USER_PERSONAS_TABLE = """
    CREATE TABLE IF NOT EXISTS user_personas (
        id SERIAL PRIMARY KEY,
        user_id BIGINT NOT NULL,
        name TEXT NOT NULL,
        system_prompt TEXT NOT NULL,
        current_session_id INTEGER,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        UNIQUE(user_id, name)
    )
"""

CREATE_PERSONAS_INDEX = """
    CREATE INDEX IF NOT EXISTS idx_personas_user_id
    ON user_personas(user_id)
"""

CREATE_USER_SESSIONS_TABLE = """
    CREATE TABLE IF NOT EXISTS user_sessions (
        id SERIAL PRIMARY KEY,
        user_id BIGINT NOT NULL,
        persona_name TEXT NOT NULL DEFAULT 'default',
        title TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
"""

CREATE_SESSIONS_INDEX = """
    CREATE INDEX IF NOT EXISTS idx_sessions_user_persona
    ON user_sessions(user_id, persona_name)
"""

CREATE_USER_CONVERSATIONS_TABLE = """
    CREATE TABLE IF NOT EXISTS user_conversations (
        id SERIAL PRIMARY KEY,
        user_id BIGINT NOT NULL,
        persona_name TEXT NOT NULL DEFAULT 'default',
        session_id INTEGER,
        role TEXT NOT NULL,
        content TEXT NOT NULL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
"""

CREATE_CONVERSATIONS_INDEX = """
    CREATE INDEX IF NOT EXISTS idx_conversations_user_persona
    ON user_conversations(user_id, persona_name)
"""

CREATE_CONVERSATIONS_SESSION_INDEX = """
    CREATE INDEX IF NOT EXISTS idx_conversations_session_id
    ON user_conversations(session_id)
"""

CREATE_USER_PERSONA_TOKENS_TABLE = """
    CREATE TABLE IF NOT EXISTS user_persona_tokens (
        user_id BIGINT NOT NULL,
        persona_name TEXT NOT NULL,
        prompt_tokens BIGINT DEFAULT 0,
        completion_tokens BIGINT DEFAULT 0,
        total_tokens BIGINT DEFAULT 0,
        PRIMARY KEY (user_id, persona_name)
    )
"""

CREATE_USER_MEMORIES_TABLE = """
    CREATE TABLE IF NOT EXISTS user_memories (
        id SERIAL PRIMARY KEY,
        user_id BIGINT NOT NULL,
        content TEXT NOT NULL,
        source TEXT NOT NULL DEFAULT 'user',
        embedding TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
"""

CREATE_MEMORIES_INDEX = """
    CREATE INDEX IF NOT EXISTS idx_memories_user_id
    ON user_memories(user_id)
"""

SCHEMA_STATEMENTS = [
    CREATE_USER_SETTINGS_TABLE,
    CREATE_USER_PERSONAS_TABLE,
    CREATE_PERSONAS_INDEX,
    CREATE_USER_SESSIONS_TABLE,
    CREATE_SESSIONS_INDEX,
    CREATE_USER_CONVERSATIONS_TABLE,
    CREATE_CONVERSATIONS_INDEX,
    CREATE_CONVERSATIONS_SESSION_INDEX,
    CREATE_USER_PERSONA_TOKENS_TABLE,
    CREATE_USER_MEMORIES_TABLE,
    CREATE_MEMORIES_INDEX,
]


def _get_connection():
    _load_dotenv_fallback()
    db_url = os.getenv("DATABASE_URL")
    if not db_url:
        raise RuntimeError("DATABASE_URL is not set. Please set it in env or .env")
    if pg_driver is None:
        raise RuntimeError(
            "No PostgreSQL driver found. Install one of: psycopg2-binary, psycopg"
        )
    return pg_driver.connect(db_url)


def _table_exists(cur, table_name: str) -> bool:
    cur.execute(
        """
        SELECT EXISTS (
            SELECT 1
            FROM information_schema.tables
            WHERE table_schema = 'public' AND table_name = %s
        )
        """,
        (table_name,),
    )
    return bool(cur.fetchone()[0])


def _column_exists(cur, table_name: str, column_name: str) -> bool:
    cur.execute(
        """
        SELECT EXISTS (
            SELECT 1
            FROM information_schema.columns
            WHERE table_schema = 'public'
              AND table_name = %s
              AND column_name = %s
        )
        """,
        (table_name, column_name),
    )
    return bool(cur.fetchone()[0])


def _fetch_one_value(cur, sql: str, params: tuple = ()) -> int:
    cur.execute(sql, params)
    row = cur.fetchone()
    return int(row[0]) if row and row[0] is not None else 0


def _ensure_schema(cur) -> None:
    for stmt in SCHEMA_STATEMENTS:
        cur.execute(stmt)

    # Additive compatibility: if old tables already exist, ensure new columns are present.
    cur.execute("ALTER TABLE user_settings ADD COLUMN IF NOT EXISTS token_limit BIGINT DEFAULT 0")
    cur.execute("ALTER TABLE user_settings ADD COLUMN IF NOT EXISTS current_persona TEXT DEFAULT 'default'")
    cur.execute("ALTER TABLE user_settings ADD COLUMN IF NOT EXISTS enabled_tools TEXT")
    cur.execute("ALTER TABLE user_settings ADD COLUMN IF NOT EXISTS tts_voice TEXT")
    cur.execute("ALTER TABLE user_settings ADD COLUMN IF NOT EXISTS tts_style TEXT")
    cur.execute("ALTER TABLE user_settings ADD COLUMN IF NOT EXISTS tts_endpoint TEXT")
    cur.execute("ALTER TABLE user_settings ADD COLUMN IF NOT EXISTS api_presets TEXT")
    cur.execute("ALTER TABLE user_settings ADD COLUMN IF NOT EXISTS title_model TEXT")

    cur.execute("ALTER TABLE user_personas ADD COLUMN IF NOT EXISTS current_session_id INTEGER")

    cur.execute("ALTER TABLE user_conversations ADD COLUMN IF NOT EXISTS persona_name TEXT DEFAULT 'default'")
    cur.execute("ALTER TABLE user_conversations ADD COLUMN IF NOT EXISTS session_id INTEGER")

    cur.execute("ALTER TABLE user_memories ADD COLUMN IF NOT EXISTS embedding TEXT")

    # Keep behavior consistent with runtime defaults.
    cur.execute(
        """
        UPDATE user_settings
        SET token_limit = COALESCE(token_limit, 0),
            current_persona = COALESCE(NULLIF(current_persona, ''), 'default'),
            enabled_tools = COALESCE(NULLIF(enabled_tools, ''), %s),
            tts_voice = COALESCE(NULLIF(tts_voice, ''), %s),
            tts_style = COALESCE(NULLIF(tts_style, ''), %s),
            tts_endpoint = COALESCE(tts_endpoint, %s),
            api_presets = COALESCE(api_presets, '{}'),
            title_model = COALESCE(title_model, '')
        """,
        (
            DEFAULT_ENABLED_TOOLS,
            DEFAULT_TTS_VOICE,
            DEFAULT_TTS_STYLE,
            DEFAULT_TTS_ENDPOINT,
        ),
    )


def _ensure_default_personas(cur) -> int:
    has_settings_prompt = _column_exists(cur, "user_settings", "system_prompt")
    if has_settings_prompt:
        cur.execute(
            """
            INSERT INTO user_personas (user_id, name, system_prompt, current_session_id)
            SELECT s.user_id,
                   'default',
                   COALESCE(NULLIF(s.system_prompt, ''), %s),
                   NULL
            FROM user_settings s
            LEFT JOIN user_personas p
              ON p.user_id = s.user_id AND p.name = 'default'
            WHERE p.user_id IS NULL
            """,
            (DEFAULT_SYSTEM_PROMPT,),
        )
    else:
        cur.execute(
            """
            INSERT INTO user_personas (user_id, name, system_prompt, current_session_id)
            SELECT s.user_id, 'default', %s, NULL
            FROM user_settings s
            LEFT JOIN user_personas p
              ON p.user_id = s.user_id AND p.name = 'default'
            WHERE p.user_id IS NULL
            """,
            (DEFAULT_SYSTEM_PROMPT,),
        )
    return cur.rowcount


def _ensure_persona_exists(cur, user_id: int, persona_name: str) -> None:
    cur.execute(
        """
        INSERT INTO user_personas (user_id, name, system_prompt, current_session_id)
        VALUES (%s, %s, %s, NULL)
        ON CONFLICT (user_id, name) DO NOTHING
        """,
        (user_id, persona_name, DEFAULT_SYSTEM_PROMPT),
    )


def _get_or_create_session(cur, user_id: int, persona_name: str, title: str | None) -> int:
    cur.execute(
        """
        SELECT id
        FROM user_sessions
        WHERE user_id = %s AND persona_name = %s
        ORDER BY id DESC
        LIMIT 1
        """,
        (user_id, persona_name),
    )
    row = cur.fetchone()
    if row:
        return int(row[0])

    cur.execute(
        """
        INSERT INTO user_sessions (user_id, persona_name, title)
        VALUES (%s, %s, %s)
        RETURNING id
        """,
        (user_id, persona_name, title),
    )
    return int(cur.fetchone()[0])


def _migrate_legacy_conversations(cur) -> tuple[int, int]:
    if not _table_exists(cur, "user_conversations"):
        return 0, 0

    # Normalize persona_name before grouping.
    cur.execute(
        """
        UPDATE user_conversations
        SET persona_name = 'default'
        WHERE persona_name IS NULL OR persona_name = ''
        """
    )

    cur.execute(
        """
        SELECT user_id, persona_name, COUNT(*) AS cnt
        FROM user_conversations
        WHERE session_id IS NULL
        GROUP BY user_id, persona_name
        ORDER BY user_id, persona_name
        """
    )
    groups = cur.fetchall()
    sessions_created = 0
    rows_migrated = 0

    for user_id, persona_name, _ in groups:
        persona = persona_name or "default"
        _ensure_persona_exists(cur, int(user_id), persona)

        # Detect whether a session already exists before deciding if we "created" one.
        cur.execute(
            """
            SELECT id
            FROM user_sessions
            WHERE user_id = %s AND persona_name = %s
            ORDER BY id DESC
            LIMIT 1
            """,
            (user_id, persona),
        )
        had_existing = cur.fetchone() is not None
        session_id = _get_or_create_session(cur, int(user_id), persona, "Legacy Chat")
        if not had_existing:
            sessions_created += 1

        cur.execute(
            """
            UPDATE user_conversations
            SET session_id = %s
            WHERE user_id = %s
              AND persona_name = %s
              AND session_id IS NULL
            """,
            (session_id, user_id, persona),
        )
        rows_migrated += cur.rowcount

        cur.execute(
            """
            UPDATE user_personas
            SET current_session_id = %s
            WHERE user_id = %s
              AND name = %s
              AND current_session_id IS NULL
            """,
            (session_id, user_id, persona),
        )

    return sessions_created, rows_migrated


def _ensure_persona_current_sessions(cur) -> tuple[int, int]:
    cur.execute(
        """
        SELECT p.user_id, p.name
        FROM user_personas p
        LEFT JOIN user_sessions s ON s.id = p.current_session_id
        WHERE p.current_session_id IS NULL OR s.id IS NULL
        ORDER BY p.user_id, p.name
        """
    )
    rows = cur.fetchall()

    created = 0
    updated = 0
    for user_id, persona_name in rows:
        cur.execute(
            """
            SELECT id
            FROM user_sessions
            WHERE user_id = %s AND persona_name = %s
            ORDER BY id DESC
            LIMIT 1
            """,
            (user_id, persona_name),
        )
        row = cur.fetchone()
        if row:
            sid = int(row[0])
        else:
            sid = _get_or_create_session(cur, int(user_id), str(persona_name), None)
            created += 1

        cur.execute(
            """
            UPDATE user_personas
            SET current_session_id = %s
            WHERE user_id = %s AND name = %s
            """,
            (sid, user_id, persona_name),
        )
        updated += cur.rowcount

    return created, updated


def _migrate_legacy_tokens(cur) -> tuple[int, int]:
    if not _table_exists(cur, "user_token_usage"):
        return 0, 0

    cur.execute(
        """
        UPDATE user_settings s
        SET token_limit = u.token_limit
        FROM user_token_usage u
        WHERE s.user_id = u.user_id
          AND COALESCE(s.token_limit, 0) = 0
          AND COALESCE(u.token_limit, 0) > 0
        """
    )
    limits_updated = cur.rowcount

    cur.execute(
        """
        INSERT INTO user_persona_tokens (
            user_id, persona_name, prompt_tokens, completion_tokens, total_tokens
        )
        SELECT u.user_id,
               'default',
               COALESCE(u.prompt_tokens, 0),
               COALESCE(u.completion_tokens, 0),
               COALESCE(u.total_tokens, 0)
        FROM user_token_usage u
        LEFT JOIN user_persona_tokens p
          ON p.user_id = u.user_id AND p.persona_name = 'default'
        WHERE p.user_id IS NULL
          AND COALESCE(u.total_tokens, 0) > 0
        """
    )
    tokens_inserted = cur.rowcount
    return limits_updated, tokens_inserted


def _normalize_settings_persona(cur) -> int:
    cur.execute(
        """
        UPDATE user_settings s
        SET current_persona = 'default'
        WHERE current_persona IS NULL
           OR current_persona = ''
           OR NOT EXISTS (
               SELECT 1
               FROM user_personas p
               WHERE p.user_id = s.user_id
                 AND p.name = s.current_persona
           )
        """
    )
    return cur.rowcount


def _finalize_conversation_constraints(cur) -> tuple[int, bool]:
    remaining_null = _fetch_one_value(
        cur,
        "SELECT COUNT(*) FROM user_conversations WHERE session_id IS NULL",
    )

    made_not_null = False
    if remaining_null == 0:
        cur.execute("ALTER TABLE user_conversations ALTER COLUMN session_id SET NOT NULL")
        made_not_null = True

    return remaining_null, made_not_null


def _cleanup_legacy(cur) -> None:
    if _table_exists(cur, "user_token_usage"):
        cur.execute("DROP TABLE user_token_usage")

    if _column_exists(cur, "user_settings", "system_prompt"):
        cur.execute("ALTER TABLE user_settings DROP COLUMN system_prompt")


def run_migration(dry_run: bool, cleanup_legacy: bool) -> int:
    conn = _get_connection()
    try:
        with conn.cursor() as cur:
            LOGGER.info("Ensuring base schema and required columns...")
            _ensure_schema(cur)

            LOGGER.info("Ensuring default personas exist...")
            personas_inserted = _ensure_default_personas(cur)

            LOGGER.info("Migrating legacy token table (if present)...")
            limits_updated, tokens_inserted = _migrate_legacy_tokens(cur)

            LOGGER.info("Migrating legacy conversation rows without session_id...")
            sessions_created, rows_migrated = _migrate_legacy_conversations(cur)

            LOGGER.info("Ensuring persona current_session_id integrity...")
            sessions_auto_created, persona_updates = _ensure_persona_current_sessions(cur)

            LOGGER.info("Normalizing current persona pointers in settings...")
            settings_fixed = _normalize_settings_persona(cur)

            LOGGER.info("Finalizing conversation constraints...")
            null_count, enforced_not_null = _finalize_conversation_constraints(cur)

            if cleanup_legacy:
                LOGGER.info("Cleaning up legacy artifacts...")
                _cleanup_legacy(cur)

            LOGGER.info("Migration summary:")
            LOGGER.info("  default personas inserted: %d", personas_inserted)
            LOGGER.info("  token limits updated from legacy table: %d", limits_updated)
            LOGGER.info("  default token rows inserted: %d", tokens_inserted)
            LOGGER.info("  legacy sessions created: %d", sessions_created)
            LOGGER.info("  legacy conversation rows migrated: %d", rows_migrated)
            LOGGER.info("  additional sessions created for personas: %d", sessions_auto_created)
            LOGGER.info("  personas current_session_id updated: %d", persona_updates)
            LOGGER.info("  settings current_persona fixed: %d", settings_fixed)
            LOGGER.info("  remaining NULL session_id rows: %d", null_count)
            LOGGER.info("  session_id NOT NULL enforced: %s", "yes" if enforced_not_null else "no")
            LOGGER.info("  cleanup legacy: %s", "yes" if cleanup_legacy else "no")

        if dry_run:
            conn.rollback()
            LOGGER.info("Dry-run complete, transaction rolled back.")
        else:
            conn.commit()
            LOGGER.info("Migration committed.")
        return 0
    except Exception:
        conn.rollback()
        LOGGER.exception("Migration failed, rolled back.")
        return 1
    finally:
        conn.close()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Migrate legacy database tables/data to the new session-based schema."
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Run migration in a transaction and rollback at the end.",
    )
    parser.add_argument(
        "--cleanup-legacy",
        action="store_true",
        help="Drop legacy artifacts after migration (e.g. user_token_usage, settings.system_prompt).",
    )
    return parser.parse_args()


def main() -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="[%(asctime)s] %(levelname)s %(message)s",
    )
    args = parse_args()
    try:
        return run_migration(dry_run=args.dry_run, cleanup_legacy=args.cleanup_legacy)
    except RuntimeError as exc:
        LOGGER.error("%s", exc)
        return 1


if __name__ == "__main__":
    sys.exit(main())
