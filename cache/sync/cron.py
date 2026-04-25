"""Cron cache sync."""

from __future__ import annotations

from database.loaders import parse_cron_task_row


def load(cur, cache) -> None:
    cur.execute(
        "SELECT id, user_id, name, cron_expression, prompt, enabled, last_run_at FROM user_cron_tasks ORDER BY id"
    )
    tasks: dict[int, list] = {}
    for row in cur.fetchall():
        tasks.setdefault(row["user_id"], []).append(parse_cron_task_row(row))
    for user_id, items in tasks.items():
        cache.set_cron_tasks(user_id, items)


def sync_deleted(cur, dirty: dict) -> None:
    for user_id, name in dirty["deleted_cron_tasks"]:
        cur.execute("DELETE FROM user_cron_tasks WHERE user_id = %s AND name = %s", (user_id, name))


def sync_new(cur, dirty: dict) -> None:
    for task in dirty["new_cron_tasks"]:
        cur.execute(
            "INSERT INTO user_cron_tasks (user_id, name, cron_expression, prompt, enabled) VALUES (%s, %s, %s, %s, %s) RETURNING id",
            (task["user_id"], task["name"], task["cron_expression"], task["prompt"], task["enabled"]),
        )
        task["id"] = cur.fetchone()[0]


def sync_updated(cur, dirty: dict) -> None:
    for task in dirty["updated_cron_tasks"]:
        cur.execute(
            "UPDATE user_cron_tasks SET cron_expression = %s, prompt = %s, enabled = %s, last_run_at = %s WHERE user_id = %s AND name = %s",
            (task["cron_expression"], task["prompt"], task["enabled"], task["last_run_at"], task["user_id"], task["name"]),
        )
