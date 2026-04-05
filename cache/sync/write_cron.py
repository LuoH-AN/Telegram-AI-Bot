"""Sync cron task mutations."""

from __future__ import annotations


def sync_deleted_cron_tasks(cur, dirty: dict) -> None:
    for user_id, name in dirty["deleted_cron_tasks"]:
        cur.execute("DELETE FROM user_cron_tasks WHERE user_id = %s AND name = %s", (user_id, name))


def sync_new_cron_tasks(cur, dirty: dict) -> None:
    for task in dirty["new_cron_tasks"]:
        cur.execute(
            "INSERT INTO user_cron_tasks (user_id, name, cron_expression, prompt, enabled) VALUES (%s, %s, %s, %s, %s) RETURNING id",
            (task["user_id"], task["name"], task["cron_expression"], task["prompt"], task["enabled"]),
        )
        task["id"] = cur.fetchone()[0]


def sync_updated_cron_tasks(cur, dirty: dict) -> None:
    for task in dirty["updated_cron_tasks"]:
        cur.execute(
            "UPDATE user_cron_tasks SET cron_expression = %s, prompt = %s, enabled = %s, last_run_at = %s WHERE user_id = %s AND name = %s",
            (task["cron_expression"], task["prompt"], task["enabled"], task["last_run_at"], task["user_id"], task["name"]),
        )
