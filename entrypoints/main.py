"""Launcher for the Telegram runtime."""

from __future__ import annotations

import os
import signal
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from dotenv import load_dotenv

from entrypoints.launcher import (
    UPDATE_RESTART_EXIT_CODE,
    apply_env_text,
    get_telegram_port,
    is_configured_token,
    restore_backup,
    run_cli_bootstrap,
    start_backup_daemon,
    start_child,
    terminate_children,
    wait_for_first_exit,
)
from adapters.http.web_app import serve_in_thread

DEFAULT_WEB_PORT = 7860
WEB_PORT = int(os.getenv("WEB_PORT", str(DEFAULT_WEB_PORT)))


def _start_children() -> list:
    telegram_port = get_telegram_port()
    children = []
    if is_configured_token(os.getenv("TELEGRAM_BOT_TOKEN")):
        children.append(start_child("Telegram", "adapters.telegram", root_dir=ROOT_DIR, port=telegram_port))
    else:
        print(">>> Telegram disabled (TELEGRAM_BOT_TOKEN is not configured)", flush=True)
    return children


def main() -> int:
    load_dotenv()

    # Restore /data from the latest /backup snapshot before anything reads it
    # (CLI bootstrap, plugins). Ephemeral-container persistence: /backup is the
    # only durable location; /data is rebuilt from it on each cold start.
    restore_backup()

    serve_in_thread(WEB_PORT)
    print(f">>> Web server running on http://0.0.0.0:{WEB_PORT}", flush=True)
    print(f">>> OpenAPI tools available at http://0.0.0.0:{WEB_PORT}/tools (spec: /openapi.json)", flush=True)

    # Periodically snapshot /data -> /backup so the next cold start can restore.
    start_backup_daemon()

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
                    ">>> No bot process configured. Set TELEGRAM_BOT_TOKEN to start the Telegram bot.",
                    flush=True,
                )
                print(">>> Web server is still running. Press Ctrl+C to exit.", flush=True)
                signal.pause()
            status = wait_for_first_exit(current_children)
            if status == UPDATE_RESTART_EXIT_CODE:
                print(">>> Runtime restart requested. Re-executing launcher with latest code...", flush=True)
                os.chdir(ROOT_DIR)
                os.execv(sys.executable, [sys.executable, "-m", "entrypoints.main"])
            return status
    except KeyboardInterrupt:
        terminate_children(current_children)
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
