"""Unified launcher for Telegram / WeChat / OneBot runtimes."""

from __future__ import annotations

import os
import signal
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler
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

DEFAULT_WEB_PORT = 7860
WEB_PORT = int(os.getenv("WEB_PORT", str(DEFAULT_WEB_PORT)))


class _HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.end_headers()
        self.wfile.write(b"OK")

    def log_message(self, format, *args):
        pass


def _start_web_server() -> None:
    server = HTTPServer(("0.0.0.0", WEB_PORT), _HealthHandler)
    server.serve_forever()


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

    web_thread = threading.Thread(target=_start_web_server, daemon=True)
    web_thread.start()
    print(f">>> Web server running on http://0.0.0.0:{WEB_PORT}", flush=True)

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
                print(">>> Web server is still running. Press Ctrl+C to exit.", flush=True)
                signal.pause()
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
