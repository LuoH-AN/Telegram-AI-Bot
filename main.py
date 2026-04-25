"""Unified launcher for Telegram / WeChat / OneBot runtimes."""

from __future__ import annotations

import os
import signal
from pathlib import Path

from dotenv import load_dotenv

from launcher import (
    UPDATE_RESTART_EXIT_CODE,
    apply_env_text,
    get_ports,
    is_configured_token,
    is_wechat_enabled,
    is_onebot_enabled,
    run_cli_bootstrap,
    start_child,
    terminate_children,
    wait_for_first_exit,
)

ROOT_DIR = Path(__file__).resolve().parent


def _start_children() -> list:
    telegram_port, wechat_port, onebot_port = get_ports()
    children = []
    if is_configured_token(os.getenv("TELEGRAM_BOT_TOKEN")):
        children.append(start_child("Telegram", "platforms.telegram", root_dir=ROOT_DIR, port=telegram_port))
    else:
        print(">>> Telegram disabled (TELEGRAM_BOT_TOKEN is not configured)", flush=True)

    if is_wechat_enabled():
        children.append(start_child("WeChat", "platforms.wechat", root_dir=ROOT_DIR, port=wechat_port))
    else:
        print(">>> WeChat disabled (WECHAT_ENABLED is not enabled)", flush=True)

    if is_onebot_enabled():
        children.append(start_child("OneBot/QQ", "platforms.onebot", root_dir=ROOT_DIR, port=onebot_port))
    else:
        print(">>> OneBot/QQ disabled (ONEBOT_ENABLED is not enabled)", flush=True)
    return children


def main() -> int:
    load_dotenv()
    current_children: list = []

    def _handle_signal(_signum, _frame) -> None:
        terminate_children(current_children)
        raise SystemExit(0)

    signal.signal(signal.SIGINT, _handle_signal)
    signal.signal(signal.SIGTERM, _handle_signal)

    try:
        while True:
            apply_env_text()
            run_cli_bootstrap(root_dir=ROOT_DIR)
            current_children = _start_children()
            if not current_children:
                print(
                    ">>> No bot process configured. Set TELEGRAM_BOT_TOKEN and/or enable WECHAT_ENABLED=1.",
                    flush=True,
                )
                return 1
            status = wait_for_first_exit(current_children)
            if status == UPDATE_RESTART_EXIT_CODE:
                print(">>> Hot update requested. Restarting all bot processes with latest code...", flush=True)
                continue
            return status
    except KeyboardInterrupt:
        terminate_children(current_children)
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
