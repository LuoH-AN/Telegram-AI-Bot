"""Detached terminal worker owning one reconnectable command session."""

from __future__ import annotations

import argparse
import json
import os
import pty
import selectors
import signal
import socket
import subprocess
import time
from pathlib import Path

from .store import get_session, update_session


def _reply(conn: socket.socket, payload: dict) -> None:
    conn.sendall((json.dumps(payload, ensure_ascii=False) + "\n").encode("utf-8"))


def _terminate(pid: int, sig: int = signal.SIGTERM) -> None:
    try:
        os.killpg(pid, sig)
    except ProcessLookupError:
        pass


def run(session_id: str) -> int:
    record = get_session(session_id)
    if not record:
        return 2
    socket_path = Path(record["socket_path"])
    log_path = Path(record["log_file"])
    socket_path.parent.mkdir(parents=True, exist_ok=True)
    log_path.parent.mkdir(parents=True, exist_ok=True)
    socket_path.unlink(missing_ok=True)

    listener = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    listener.bind(str(socket_path))
    os.chmod(socket_path, 0o600)
    listener.listen(8)
    listener.setblocking(False)

    use_pty = bool(record.get("pty"))
    master_fd: int | None = None
    stdin = None
    if use_pty:
        master_fd, slave_fd = pty.openpty()
        proc = subprocess.Popen(
            ["bash", "-lc", record["command"]],
            cwd=record["cwd"],
            env=dict(os.environ),
            stdin=slave_fd,
            stdout=slave_fd,
            stderr=slave_fd,
            start_new_session=True,
            close_fds=True,
        )
        os.close(slave_fd)
        os.set_blocking(master_fd, False)
        output_fd = master_fd
    else:
        proc = subprocess.Popen(
            ["bash", "-lc", record["command"]],
            cwd=record["cwd"],
            env=dict(os.environ),
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            start_new_session=True,
            bufsize=0,
        )
        stdin = proc.stdin
        output_fd = proc.stdout.fileno()
        os.set_blocking(output_fd, False)

    update_session(
        session_id,
        worker_pid=os.getpid(),
        pid=proc.pid,
        status="running",
        last_output_at=time.time(),
    )

    selector = selectors.DefaultSelector()
    selector.register(listener, selectors.EVENT_READ, "listener")
    selector.register(output_fd, selectors.EVENT_READ, "output")
    last_db_output_update = 0.0

    def write_input(data: str) -> None:
        raw = data.encode("utf-8")
        if master_fd is not None:
            os.write(master_fd, raw)
        elif stdin is not None:
            stdin.write(raw)
            stdin.flush()

    try:
        with log_path.open("ab", buffering=0) as log:
            while True:
                for key, _ in selector.select(timeout=0.25):
                    if key.data == "output":
                        try:
                            chunk = os.read(output_fd, 65536)
                        except BlockingIOError:
                            chunk = b""
                        except OSError:
                            chunk = b""
                        if chunk:
                            log.write(chunk)
                            now = time.time()
                            if now - last_db_output_update >= 0.5:
                                update_session(session_id, last_output_at=now)
                                last_db_output_update = now
                    else:
                        conn, _ = listener.accept()
                        with conn:
                            conn.settimeout(1)
                            raw = b""
                            while b"\n" not in raw and len(raw) < 1_000_000:
                                part = conn.recv(65536)
                                if not part:
                                    break
                                raw += part
                            try:
                                request = json.loads(raw.decode("utf-8").splitlines()[0])
                                action = request.get("action")
                                if action == "write":
                                    write_input(str(request.get("data") or ""))
                                    _reply(conn, {"ok": True})
                                elif action == "kill":
                                    _terminate(proc.pid)
                                    _reply(conn, {"ok": True})
                                elif action == "status":
                                    _reply(conn, {"ok": True, "running": proc.poll() is None})
                                else:
                                    _reply(conn, {"ok": False, "error": "unknown action"})
                            except Exception as exc:
                                _reply(conn, {"ok": False, "error": str(exc)})
                exit_code = proc.poll()
                if exit_code is not None:
                    # Drain any final bytes already waiting in the pipe/PTY.
                    while True:
                        try:
                            chunk = os.read(output_fd, 65536)
                        except (BlockingIOError, OSError):
                            break
                        if not chunk:
                            break
                        log.write(chunk)
                    ended = time.time()
                    update_session(
                        session_id,
                        status="completed" if exit_code == 0 else "failed",
                        exit_code=exit_code,
                        ended_at=ended,
                        last_output_at=ended,
                    )
                    if exit_code == 0:
                        try:
                            from .persist import persist_install_command

                            persist_install_command(record["command"])
                        except Exception:
                            pass
                    try:
                        from entrypoints.launcher.backup import request_snapshot

                        request_snapshot()
                    except Exception:
                        pass
                    return int(exit_code)
    finally:
        listener.close()
        socket_path.unlink(missing_ok=True)
        if master_fd is not None:
            try:
                os.close(master_fd)
            except OSError:
                pass
        if proc.poll() is None:
            _terminate(proc.pid, signal.SIGKILL)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("session_id")
    args = parser.parse_args()
    try:
        return run(args.session_id)
    except Exception:
        record = get_session(args.session_id)
        if record:
            update_session(
                args.session_id,
                status="failed",
                ended_at=time.time(),
                last_output_at=time.time(),
            )
            try:
                Path(record["socket_path"]).unlink(missing_ok=True)
            except OSError:
                pass
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
