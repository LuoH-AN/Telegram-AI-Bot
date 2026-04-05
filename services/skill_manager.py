"""Shared skill command orchestration for Telegram and Discord."""

from __future__ import annotations

from .skills import (
    enable_skill,
    get_skill,
    install_skill,
    install_skill_from_github,
    list_skills,
    remove_skill,
)

SKILL_HELP_TEXT = (
    "Skill management:\n"
    "Just chat directly, AI will handle skill installation, execution, and management through tools.\n\n"
    "Built-in skills:\n"
    "- skill_terminal: direct shell terminal with persistent cwd/env session, plus AI-guided task mode\n"
    "- hf_sync: object storage + sync on Hugging Face, supports encrypted and plaintext uploads with view links\n\n"
    "/skill - list installed skills\n"
    "/skill help - show this help\n"
    "/skill install <name or GitHub URL> [persist] - install skill\n"
    "/skill remove <name> - remove skill\n"
    "/skill enable <name> - enable skill\n"
    "/skill disable <name> - disable skill"
)


def _list_message(user_id: int) -> str:
    skills = list_skills(user_id)
    if not skills:
        return "No installed skills.\n\nJust chat directly, AI will handle skill installation and management."
    lines = [
        f"- {item['name']} ({'enabled' if item.get('enabled') else 'disabled'})"
        for item in skills
    ]
    return "Installed skills:\n" + "\n".join(lines)


def ensure_skill_terminal(user_id: int) -> None:
    if not get_skill(user_id, "skill_terminal"):
        install_skill(user_id, "skill_terminal", source_type="builtin", source_ref="skill_terminal", persist_mode="hf_git")


def ensure_hf_sync_skill(user_id: int) -> None:
    if not get_skill(user_id, "hf_sync"):
        install_skill(user_id, "hf_sync", source_type="builtin", source_ref="hf_sync", persist_mode="hf_git")


def handle_skill_command(user_id: int, args: list[str], *, command_prefix: str = "/skill") -> str:
    if not args:
        return _list_message(user_id) + "\n\n" + SKILL_HELP_TEXT.replace("/skill", command_prefix)

    sub = (args[0] or "").strip().lower()
    if sub == "help":
        return SKILL_HELP_TEXT.replace("/skill", command_prefix)

    if sub == "install" and len(args) >= 2:
        ref = args[1].strip()
        persist_mode = "hf_git" if any(item.lower() == "persist" for item in args[2:]) else "none"
        if ref.startswith("https://github.com/") or ref.startswith("https://raw.githubusercontent.com/"):
            name_hint = ""
            for item in args[2:]:
                if item.lower() != "persist":
                    name_hint = item.strip().lower()
                    break
            skill = install_skill_from_github(user_id, ref, name_hint=name_hint, persist_mode=persist_mode)
            return (
                f"Installed skill from GitHub: {skill['name']} (backup={skill.get('persist_mode', 'none')})"
                if skill
                else "GitHub skill installation failed. Please check the link and manifest.json."
            )
        skill = install_skill(user_id, ref.lower(), source_type="builtin", source_ref=ref.lower(), persist_mode=persist_mode)
        return f"Installed skill: {skill['name']} (backup={skill.get('persist_mode', 'none')})"

    if sub == "enable" and len(args) >= 2:
        return "Skill enabled." if enable_skill(user_id, args[1].strip().lower(), True) else "Skill not found."

    if sub == "disable" and len(args) >= 2:
        return "Skill disabled." if enable_skill(user_id, args[1].strip().lower(), False) else "Skill not found."

    if sub in {"remove", "delete"} and len(args) >= 2:
        return "Skill removed." if remove_skill(user_id, args[1].strip().lower()) else "Skill not found."

    return SKILL_HELP_TEXT.replace("/skill", command_prefix)
