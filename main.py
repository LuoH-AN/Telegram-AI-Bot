"""Unified launcher for Telegram / Discord / WeChat runtimes."""

from __future__ import annotations

import os
import signal
from pathlib import Path

from dotenv import load_dotenv

from launcher import (
    apply_env_text,
    get_ports,
    is_configured_token,
    is_wechat_enabled,
    start_child,
    terminate_children,
    wait_for_first_exit,
)

ROOT_DIR = Path(__file__).resolve().parent


def _start_children() -> list:
    telegram_port, discord_port, wechat_port = get_ports()
    children = []
    if is_configured_token(os.getenv("TELEGRAM_BOT_TOKEN")):
        children.append(start_child("Telegram", "platforms.telegram", root_dir=ROOT_DIR, port=telegram_port))
    else:
        print(">>> Telegram disabled (TELEGRAM_BOT_TOKEN is not configured)", flush=True)

    if is_configured_token(os.getenv("DISCORD_BOT_TOKEN")):
        children.append(start_child("Discord", "platforms.discord", root_dir=ROOT_DIR, port=discord_port))
    else:
        print(">>> Discord disabled (DISCORD_BOT_TOKEN is not configured)", flush=True)

    if is_wechat_enabled():
        children.append(start_child("WeChat", "platforms.wechat", root_dir=ROOT_DIR, port=wechat_port))
    else:
        print(">>> WeChat disabled (WECHAT_ENABLED is not enabled)", flush=True)
    return children


def main() -> int:
    load_dotenv()
    apply_env_text()
    children = _start_children()

    if not children:
        print(">>> No bot process configured. Set TELEGRAM_BOT_TOKEN and/or DISCORD_BOT_TOKEN, or enable WECHAT_ENABLED=1.", flush=True)
        return 1

    def _handle_signal(_signum, _frame) -> None:
        terminate_children(children)
        raise SystemExit(0)

    signal.signal(signal.SIGINT, _handle_signal)
    signal.signal(signal.SIGTERM, _handle_signal)

    try:
        return wait_for_first_exit(children)
    except KeyboardInterrupt:
        terminate_children(children)
        return 0


if __name__ == "__main__":
    raise SystemExit(main())

