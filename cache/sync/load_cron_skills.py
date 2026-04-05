"""Load cron tasks and skills/state."""

from __future__ import annotations

from database.loaders import parse_cron_task_row, parse_skill_row, parse_skill_state_row


def load_cron_tasks(cur, cache) -> None:
    cur.execute(
        "SELECT id, user_id, name, cron_expression, prompt, enabled, last_run_at FROM user_cron_tasks ORDER BY id"
    )
    cron_tasks: dict[int, list] = {}
    for row in cur.fetchall():
        cron_tasks.setdefault(row["user_id"], []).append(parse_cron_task_row(row))
    for user_id, task_list in cron_tasks.items():
        cache.set_cron_tasks(user_id, task_list)


def load_skills(cur, cache) -> None:
    cur.execute("SELECT * FROM user_skills ORDER BY id")
    skills: dict[int, list] = {}
    for row in cur.fetchall():
        skills.setdefault(row["user_id"], []).append(parse_skill_row(row))
    for user_id, skill_list in skills.items():
        cache.set_skills(user_id, skill_list)


def load_skill_states(cur, cache) -> None:
    cur.execute("SELECT * FROM user_skill_states ORDER BY id")
    for row in cur.fetchall():
        parsed = parse_skill_state_row(row)
        cache.set_skill_state(parsed["user_id"], parsed["skill_name"], {
            "id": parsed["id"],
            "state": parsed["state"],
            "state_version": parsed["state_version"],
            "checkpoint_ref": parsed["checkpoint_ref"],
            "updated_at": parsed["updated_at"],
        })


def run_cron_skills_load(cur, cache) -> None:
    load_cron_tasks(cur, cache)
    load_skills(cur, cache)
    load_skill_states(cur, cache)
