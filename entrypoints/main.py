"""Launcher for the Telegram runtime."""

from __future__ import annotations

import os
import signal
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from entrypoints.launcher import (
    UPDATE_RESTART_EXIT_CODE,
    apply_env_text,
    exec_active_workspace,
    get_telegram_port,
    is_configured_token,
    restore_backup,
    run_cli_bootstrap,
    start_backup_daemon,
    start_child,
    terminate_children,
    wait_for_first_exit,
)

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
    from infrastructure.config import load_env

    # Environment is also loaded at config import time; this re-applies .env /
    # ENV_TEXT after a possible hot-reload exec so subprocesses see fresh values.
    load_env(force=True)

    # Restore /data from the latest /backup snapshot before anything reads it
    # (CLI bootstrap, plugins). Ephemeral-container persistence: /backup is the
    # only durable location; /data is rebuilt from it on each cold start.
    skip_workspace_restore = os.environ.pop("_TGBOT_SKIP_WORKSPACE_RESTORE_ONCE", "") == "1"
    if skip_workspace_restore:
        print(">>> Controlled restart: preserving live /data and workspace without backup restore", flush=True)
    else:
        restore_backup()

    # The bot and all terminal-relative files run from /data. On the initial
    # image invocation this re-execs; subsequent managed restarts are already
    # executing the persistent copy and continue below.
    exec_active_workspace(ROOT_DIR)

    from adapters.http.web_app import serve_in_thread

    serve_in_thread(WEB_PORT)
    print(f">>> Web server running on http://0.0.0.0:{WEB_PORT}", flush=True)
    print(
        f">>> OpenAPI tool specs: http://0.0.0.0:{WEB_PORT}/tools/terminal/openapi.json "
        f"and http://0.0.0.0:{WEB_PORT}/tools/search/openapi.json",
        flush=True,
    )

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
                active_root = Path(os.getenv("_TGBOT_ACTIVE_WORKSPACE") or ROOT_DIR).resolve()
                os.chdir(active_root)
                # The current workspace already contains the just-applied update
                # or safe-restart state. Never overlay it with an older snapshot.
                os.environ["_TGBOT_SKIP_WORKSPACE_RESTORE_ONCE"] = "1"
                env = os.environ.copy()
                current_pythonpath = env.get("PYTHONPATH", "")
                env["PYTHONPATH"] = os.pathsep.join(part for part in (str(active_root), current_pythonpath) if part)
                os.execve(sys.executable, [sys.executable, "-m", "entrypoints.main"], env)
            return status
    except KeyboardInterrupt:
        terminate_children(current_children)
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
