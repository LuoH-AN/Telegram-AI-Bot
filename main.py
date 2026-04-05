"""Unified launcher for Telegram / Discord / WeChat runtimes."""

from __future__ import annotations

import os
import shutil
import signal
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv


ROOT_DIR = Path(__file__).resolve().parent
TELEGRAM_PORT = os.getenv("TELEGRAM_PORT", "7860")
DISCORD_PORT = os.getenv("DISCORD_PORT", "7861")
WECHAT_PORT = os.getenv("WECHAT_PORT", "7862")
HEADLESS_OFF_VALUES = {"0", "false", "no", "off", "headed"}


@dataclass
class ChildProcess:
    name: str
    process: subprocess.Popen


def _trim(value: str | None) -> str:
    return (value or "").strip()


def _apply_env_text() -> None:
    raw = _trim(os.getenv("ENV_TEXT"))
    if not raw:
        raw = _trim(os.getenv("ENV_CONTENT"))
    if not raw:
        return

    text = raw.replace("\r\n", "\n").replace("\r", "\n")
    if "\n" not in text and "\\n" in text:
        text = text.replace("\\n", "\n")

    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[len("export "):].strip()
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        if not key or not (key[0].isalpha() or key[0] == "_"):
            continue
        if any(not (ch.isalnum() or ch == "_") for ch in key):
            continue
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
            value = value[1:-1]
        if key not in os.environ:
            os.environ[key] = value


def _is_configured_token(token: str | None) -> bool:
    value = _trim(token)
    if not value:
        return False
    return value not in {"your_telegram_bot_token_here", "your_discord_bot_token_here", "changeme", "CHANGE_ME"}


def _is_wechat_enabled() -> bool:
    return _trim(os.getenv("WECHAT_ENABLED")).lower() in {"1", "true", "yes", "on"}


def _build_command(module_name: str) -> list[str]:
    headless_mode = _trim(os.getenv("BROWSER_HEADLESS", "1")).lower()
    base_cmd = [sys.executable, "-m", module_name]
    if headless_mode in HEADLESS_OFF_VALUES:
        xvfb_run = shutil.which("xvfb-run")
        xauth = shutil.which("xauth")
        if xvfb_run and xauth:
            return [xvfb_run, "-a", *base_cmd]
    return base_cmd


def _start_child(name: str, module_name: str, *, port: str) -> ChildProcess:
    env = os.environ.copy()
    env["PORT"] = str(port)
    print(f">>> Starting {name} bot on PORT={port}", flush=True)
    process = subprocess.Popen(
        _build_command(module_name),
        cwd=ROOT_DIR,
        env=env,
    )
    return ChildProcess(name=name, process=process)


def _terminate_children(children: list[ChildProcess]) -> None:
    for child in children:
        if child.process.poll() is None:
            child.process.terminate()
    for child in children:
        try:
            child.process.wait(timeout=10)
        except Exception:
            if child.process.poll() is None:
                child.process.kill()


def main() -> int:
    load_dotenv()
    _apply_env_text()

    children: list[ChildProcess] = []
    if _is_configured_token(os.getenv("TELEGRAM_BOT_TOKEN")):
        children.append(_start_child("Telegram", "platforms.telegram", port=TELEGRAM_PORT))
    else:
        print(">>> Telegram disabled (TELEGRAM_BOT_TOKEN is not configured)", flush=True)

    if _is_configured_token(os.getenv("DISCORD_BOT_TOKEN")):
        children.append(_start_child("Discord", "platforms.discord", port=DISCORD_PORT))
    else:
        print(">>> Discord disabled (DISCORD_BOT_TOKEN is not configured)", flush=True)

    if _is_wechat_enabled():
        children.append(_start_child("WeChat", "platforms.wechat", port=WECHAT_PORT))
    else:
        print(">>> WeChat disabled (WECHAT_ENABLED is not enabled)", flush=True)

    if not children:
        print(
            ">>> No bot process configured. Set TELEGRAM_BOT_TOKEN and/or DISCORD_BOT_TOKEN, or enable WECHAT_ENABLED=1.",
            flush=True,
        )
        return 1

    def _handle_signal(signum, _frame) -> None:
        _terminate_children(children)
        raise SystemExit(0)

    signal.signal(signal.SIGINT, _handle_signal)
    signal.signal(signal.SIGTERM, _handle_signal)

    if len(children) == 1:
        return children[0].process.wait()

    try:
        while True:
            for child in children:
                status = child.process.poll()
                if status is None:
                    continue
                print(f">>> One bot process exited (status={status}), stopping remaining bot processes.", flush=True)
                _terminate_children(children)
                return status
            time.sleep(1)
    except KeyboardInterrupt:
        _terminate_children(children)
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
