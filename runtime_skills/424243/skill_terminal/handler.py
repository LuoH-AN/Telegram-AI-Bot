"""Runtime skill handler for skill_terminal."""

from services.skill_terminal import run_skill_terminal


def run(user_id: int, skill_name: str, input_text: str, state: dict) -> dict:
    result = run_skill_terminal(user_id, input_text)
    calls = int(state.get("calls", 0)) + 1
    return {
        "output": result.get("message", "技能终端执行完成。"),
        "state": {
            **state,
            "calls": calls,
            "last_input": input_text,
            "last_terminal_steps": result.get("steps", []),
            "last_terminal_ok": bool(result.get("ok")),
        },
    }
