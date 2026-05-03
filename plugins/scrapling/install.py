"""Installation helpers for scrapling integration."""

from __future__ import annotations

import json
import subprocess
import sys
import time

from .constants import INSTALL_LOG_FILE, RUNTIME_DIR
from .runtime import detect_capabilities


def install_scrapling(*, with_fetchers: bool = True, with_browser: bool = False, upgrade: bool = False, timeout: int = 900) -> dict:
    package = "scrapling[fetchers]" if with_fetchers else "scrapling"
    pip_args = [sys.executable, "-m", "pip", "install"]
    if upgrade:
        pip_args.append("--upgrade")
    pip_args.append(package)

    logs: list[str] = []
    start_at = time.time()
    install_run = _run(pip_args, timeout=timeout)
    logs.append(_format_run("pip_install", install_run))
    if install_run["returncode"] != 0:
        _write_log(logs)
        return {
            "ok": False,
            "step": "pip_install",
            "message": "Failed to install scrapling package.",
            "returncode": install_run["returncode"],
            "log_file": str(INSTALL_LOG_FILE),
            "capabilities": detect_capabilities(),
        }

    if with_browser:
        browser_run = _run(
            [sys.executable, "-c", "from scrapling.cli import main; main(['install'])"],
            timeout=timeout,
        )
        logs.append(_format_run("scrapling_install", browser_run))
        if browser_run["returncode"] != 0:
            _write_log(logs)
            return {
                "ok": False,
                "step": "scrapling_install",
                "message": "scrapling package installed but browser dependency install failed.",
                "returncode": browser_run["returncode"],
                "log_file": str(INSTALL_LOG_FILE),
                "capabilities": detect_capabilities(),
            }

    _write_log(logs)
    return {
        "ok": True,
        "step": "done",
        "message": "scrapling installed successfully.",
        "elapsed_seconds": int(time.time() - start_at),
        "log_file": str(INSTALL_LOG_FILE),
        "capabilities": detect_capabilities(),
    }


def _run(args: list[str], *, timeout: int) -> dict:
    try:
        proc = subprocess.run(
            args,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        return {
            "args": args,
            "returncode": int(proc.returncode),
            "stdout": str(proc.stdout or ""),
            "stderr": str(proc.stderr or ""),
            "timeout": False,
        }
    except subprocess.TimeoutExpired as exc:
        return {
            "args": args,
            "returncode": 124,
            "stdout": str(exc.stdout or ""),
            "stderr": str(exc.stderr or ""),
            "timeout": True,
        }


def _format_run(name: str, run: dict) -> str:
    payload = {
        "step": name,
        "args": run.get("args"),
        "returncode": run.get("returncode"),
        "timeout": bool(run.get("timeout")),
        "stdout": _trim(str(run.get("stdout") or ""), 3000),
        "stderr": _trim(str(run.get("stderr") or ""), 3000),
    }
    return json.dumps(payload, ensure_ascii=False, indent=2)


def _trim(text: str, max_chars: int) -> str:
    if len(text) <= max_chars:
        return text
    return text[: max_chars - 3] + "..."


def _write_log(lines: list[str]) -> None:
    RUNTIME_DIR.mkdir(parents=True, exist_ok=True)
    INSTALL_LOG_FILE.write_text("\n\n".join(lines), encoding="utf-8")

