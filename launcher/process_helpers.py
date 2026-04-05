"""Child process helpers for launcher."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path

HEADLESS_OFF_VALUES = {"0", "false", "no", "off", "headed"}


@dataclass
class ChildProcess:
    name: str
    process: subprocess.Popen


def _build_command(module_name: str) -> list[str]:
    headless_mode = (os.getenv("BROWSER_HEADLESS", "1") or "").strip().lower()
    base_cmd = [sys.executable, "-m", module_name]
    if headless_mode in HEADLESS_OFF_VALUES:
        xvfb_run = shutil.which("xvfb-run")
        xauth = shutil.which("xauth")
        if xvfb_run and xauth:
            return [xvfb_run, "-a", *base_cmd]
    return base_cmd


def start_child(name: str, module_name: str, *, root_dir: Path, port: str) -> ChildProcess:
    env = os.environ.copy()
    env["PORT"] = str(port)
    print(f">>> Starting {name} bot on PORT={port}", flush=True)
    process = subprocess.Popen(_build_command(module_name), cwd=root_dir, env=env)
    return ChildProcess(name=name, process=process)


def terminate_children(children: list[ChildProcess]) -> None:
    for child in children:
        if child.process.poll() is None:
            child.process.terminate()
    for child in children:
        try:
            child.process.wait(timeout=10)
        except Exception:
            if child.process.poll() is None:
                child.process.kill()


def wait_for_first_exit(children: list[ChildProcess]) -> int:
    if len(children) == 1:
        return children[0].process.wait()
    while True:
        for child in children:
            status = child.process.poll()
            if status is None:
                continue
            print(f">>> One bot process exited (status={status}), stopping remaining bot processes.", flush=True)
            terminate_children(children)
            return status
        time.sleep(1)

