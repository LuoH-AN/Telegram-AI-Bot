#!/usr/bin/env python3
"""Inspect user memories from DB using DATABASE_URL in .env."""

from __future__ import annotations

import argparse
import os
import sys

import psycopg2
from dotenv import load_dotenv


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="List memories from user_memories table",
    )
    parser.add_argument(
        "--user-id",
        type=int,
        default=None,
        help="Target Telegram user_id. If omitted, auto-select.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=200,
        help="Max memories to print (default: 200)",
    )
    return parser.parse_args()


def pick_user_id(cur, explicit_user_id: int | None) -> int | None:
    if explicit_user_id is not None:
        return explicit_user_id

    cur.execute(
        """
        SELECT user_id, COUNT(*) AS cnt, MAX(created_at) AS last_at
        FROM user_memories
        GROUP BY user_id
        ORDER BY last_at DESC NULLS LAST, user_id DESC
        """
    )
    rows = cur.fetchall()
    if not rows:
        return None
    if len(rows) == 1:
        return int(rows[0][0])

    print("Found multiple users with memories:")
    for row in rows:
        print(f"  - user_id={row[0]} memories={row[1]} last_at={row[2]}")
    print(f"Auto-selecting most recent user_id={rows[0][0]}.")
    return int(rows[0][0])


def main() -> int:
    load_dotenv(dotenv_path=".env", override=False)
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        print("Error: DATABASE_URL is missing in .env", file=sys.stderr)
        return 1

    args = parse_args()
    limit = max(1, args.limit)

    try:
        conn = psycopg2.connect(database_url)
    except Exception as e:
        print(f"Error: failed to connect database: {e}", file=sys.stderr)
        return 1

    try:
        with conn:
            with conn.cursor() as cur:
                user_id = pick_user_id(cur, args.user_id)
                if user_id is None:
                    print("No memories found in user_memories.")
                    return 0

                cur.execute(
                    """
                    SELECT id, content, source, created_at
                    FROM user_memories
                    WHERE user_id = %s
                    ORDER BY id ASC
                    LIMIT %s
                    """,
                    (user_id, limit),
                )
                rows = cur.fetchall()

                if not rows:
                    print(f"No memories found for user_id={user_id}.")
                    return 0

                print(f"user_id={user_id} total={len(rows)}")
                for i, row in enumerate(rows, start=1):
                    mem_id, content, source, created_at = row
                    print(f"\n[{i}] id={mem_id} source={source} created_at={created_at}")
                    print(content)
    finally:
        conn.close()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
