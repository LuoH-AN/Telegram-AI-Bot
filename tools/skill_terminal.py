"""Terminal execution tool for AI - no restrictions."""

from __future__ import annotations

import logging
import subprocess
import threading
import time
from pathlib import Path

from .base import BaseTool

logger = logging.getLogger(__name__)

REPO_ROOT = Path(__file__).resolve().parent.parent
_LOG_DIR = REPO_ROOT / "bg_logs"

# Background job tracker: {pid: {"command": str, "cwd": str, "started_at": float, "log_file": Path, "done": bool}}
_bg_jobs: dict[int, dict] = {}
_bg_lock = threading.Lock()


def _ensure_log_dir() -> Path:
    _LOG_DIR.mkdir(parents=True, exist_ok=True)
    return _LOG_DIR


class SkillTerminalTool(BaseTool):
    """Terminal tool callable by AI with no security restrictions."""

    @property
    def name(self) -> str:
        return "terminal"

    def definitions(self) -> list[dict]:
        return [
            {
                "type": "function",
                "function": {
                    "name": "terminal",
                    "description": (
                        "Execute terminal commands. Can be used to install dependencies, download files, "
                        "manipulate filesystem, manage processes, and any other terminal operations. "
                        "No security restrictions. Set background=true for long-running commands to run "
                        "them in the background without blocking."
                    ),
                    "parameters": self._parameters(),
                },
            }
        ]

    def _parameters(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "command": {
                    "type": "string",
                    "description": "Shell command to execute",
                },
                "cwd": {
                    "type": "string",
                    "description": "Working directory (optional, defaults to repository root)",
                },
                "timeout": {
                    "type": "integer",
                    "description": "Timeout in seconds (default 60), only applies to foreground commands",
                },
                "background": {
                    "type": "boolean",
                    "description": "Run command in background. Returns PID immediately. Use bg_check to monitor.",
                },
                "bg_check": {
                    "type": "integer",
                    "description": "Check status of a background job by PID. Returns running/done + output.",
                },
                "bg_list": {
                    "type": "boolean",
                    "description": "List all background jobs and their status.",
                },
            },
            "required": [],
        }

    def execute(self, user_id: int, tool_name: str, arguments: dict) -> str:
        # Background job listing
        if arguments.get("bg_list"):
            return self._list_bg_jobs()

        # Background job status check
        bg_check = arguments.get("bg_check")
        if bg_check is not None:
            return self._check_bg_job(int(bg_check))

        command = str(arguments.get("command", "")).strip()
        if not command:
            return "Error: command is required (unless using bg_list or bg_check)."

        cwd = str(arguments.get("cwd", "")).strip() or str(REPO_ROOT)
        cwd_path = Path(cwd)
        if not cwd_path.is_absolute():
            cwd_path = REPO_ROOT / cwd_path
        cwd_path = cwd_path.resolve()

        # Background execution
        if arguments.get("background"):
            return self._run_background(command, cwd_path)

        # Foreground execution (original behavior)
        timeout = int(arguments.get("timeout", 60))
        logger.info("skill_terminal: user=%s, command=%s, cwd=%s", user_id, command, cwd_path)

        try:
            result = subprocess.run(
                command,
                shell=True,
                cwd=str(cwd_path),
                capture_output=True,
                text=True,
                timeout=timeout,
            )

            output_parts = []
            if result.stdout:
                output_parts.append(f"stdout:\n{result.stdout}")
            if result.stderr:
                output_parts.append(f"stderr:\n{result.stderr}")
            output_parts.append(f"exit_code: {result.returncode}")

            return "\n\n".join(output_parts)

        except subprocess.TimeoutExpired:
            return f"Error: command execution timeout ({timeout}s). Consider using background=true for long-running commands."
        except Exception as e:
            logger.exception("skill_terminal execution failed")
            return f"Error: {e}"

    def _run_background(self, command: str, cwd_path: Path) -> str:
        log_dir = _ensure_log_dir()
        timestamp = time.strftime("%Y%m%d_%H%M%S")
        log_file = log_dir / f"bg_{timestamp}.log"

        try:
            with open(log_file, "w") as lf:
                proc = subprocess.Popen(
                    ["bash", "-lc", command],
                    cwd=str(cwd_path),
                    stdout=lf,
                    stderr=subprocess.STDOUT,
                    stdin=subprocess.DEVNULL,
                    start_new_session=True,
                )

            pid = proc.pid
            with _bg_lock:
                _bg_jobs[pid] = {
                    "command": command,
                    "cwd": str(cwd_path),
                    "started_at": time.time(),
                    "log_file": log_file,
                    "done": False,
                    "exit_code": None,
                }

            # Daemon thread to wait for completion
            def _wait(p: int, proc: subprocess.Popen) -> None:
                proc.wait()
                with _bg_lock:
                    if p in _bg_jobs:
                        _bg_jobs[p]["done"] = True
                        _bg_jobs[p]["exit_code"] = proc.returncode

            threading.Thread(target=_wait, args=(pid, proc), daemon=True).start()

            logger.info("bg_job: pid=%d, cmd=%s, log=%s", pid, command[:80], log_file)
            return (
                f"Background job started.\n"
                f"PID: {pid}\n"
                f"Log: {log_file}\n"
                f"Command: {command}\n"
                f"Use bg_check={pid} to check status."
            )

        except Exception as e:
            logger.exception("bg_job start failed")
            return f"Error starting background job: {e}"

    def _check_bg_job(self, pid: int) -> str:
        with _bg_lock:
            job = _bg_jobs.get(pid)
        if not job:
            return f"Background job not found: PID {pid}."

        status = "done" if job["done"] else "running"
        log_file = job["log_file"]
        output = ""
        if log_file.exists():
            try:
                output = log_file.read_text(encoding="utf-8", errors="replace")
                if len(output) > 4000:
                    output = output[:3000] + f"\n\n...(truncated, {len(output)} chars total)...\n" + output[-1000:]
            except Exception:
                output = "(unable to read log)"

        elapsed = int(time.time() - job["started_at"])
        lines = [
            f"PID: {pid}",
            f"Status: {status}",
            f"Exit code: {job['exit_code']}" if job["done"] else "",
            f"Elapsed: {elapsed}s",
            f"Command: {job['command']}",
        ]
        if output:
            lines.append(f"\nOutput:\n{output}")

        return "\n".join(line for line in lines if line)

    def _list_bg_jobs(self) -> str:
        with _bg_lock:
            if not _bg_jobs:
                return "No background jobs."
            jobs = list(_bg_jobs.items())

        lines = ["Background jobs:"]
        now = time.time()
        for pid, job in jobs:
            status = "done" if job["done"] else "running"
            elapsed = int(now - job["started_at"])
            exit_info = f", exit={job['exit_code']}" if job["done"] else ""
            lines.append(f"  PID {pid}: [{status}] {elapsed}s{exit_info} - {job['command'][:60]}")
        return "\n".join(lines)
