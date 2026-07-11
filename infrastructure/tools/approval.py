"""一次性工具审批状态，供平台按钮恢复原工具调用。"""

from __future__ import annotations

import asyncio
import hashlib
import secrets
import shlex
import threading
from dataclasses import dataclass
from typing import Literal

ApprovalChoice = Literal["approve", "deny", "timeout"]
ResolveStatus = Literal["approved", "denied", "missing", "forbidden"]


@dataclass
class PendingApproval:
    approval_id: str
    user_id: int
    chat_id: int
    command: str
    cwd: str
    lang: str
    session_key: str
    fingerprint: str
    prefix_rule: dict | None
    future: asyncio.Future[ApprovalChoice]
    processing: bool = False


@dataclass(frozen=True)
class ResolveResult:
    status: ResolveStatus
    pending: PendingApproval | None = None


class ApprovalBroker:
    """保存进程内的一次性审批；重启后旧按钮会自然失效。"""

    def __init__(self) -> None:
        self._pending: dict[str, PendingApproval] = {}
        self._session_approved: dict[str, list[dict]] = {}

    def create(
        self,
        *,
        user_id: int,
        chat_id: int,
        command: str,
        cwd: str,
        lang: str,
        session_key: str = "",
    ) -> PendingApproval:
        loop = asyncio.get_running_loop()
        while True:
            approval_id = secrets.token_urlsafe(9)
            if approval_id not in self._pending:
                break
        pending = PendingApproval(
            approval_id=approval_id,
            user_id=int(user_id),
            chat_id=int(chat_id),
            command=command,
            cwd=cwd,
            lang=lang,
            session_key=session_key or f"{chat_id}:{user_id}",
            fingerprint=approval_fingerprint(command, cwd),
            prefix_rule=suggest_prefix_rule(command, cwd),
            future=loop.create_future(),
        )
        self._pending[approval_id] = pending
        return pending

    def get(self, approval_id: str) -> PendingApproval | None:
        return self._pending.get(approval_id)

    def discard(self, approval_id: str) -> PendingApproval | None:
        return self._pending.pop(approval_id, None)

    def allow_session(self, pending: PendingApproval) -> None:
        if pending.prefix_rule is not None:
            rules = self._session_approved.setdefault(pending.session_key, [])
            if pending.prefix_rule not in rules:
                rules.append(pending.prefix_rule)

    def is_session_allowed(self, session_key: str, command: str, cwd: str) -> bool:
        return any(rule_matches(rule, command, cwd) for rule in self._session_approved.get(session_key, []))

    def resolve(self, approval_id: str, *, user_id: int, chat_id: int, approve: bool) -> ResolveResult:
        pending = self._pending.get(approval_id)
        if pending is None or pending.future.done():
            return ResolveResult("missing")
        if pending.user_id != int(user_id) or pending.chat_id != int(chat_id):
            return ResolveResult("forbidden", pending)
        self._pending.pop(approval_id, None)
        choice: ApprovalChoice = "approve" if approve else "deny"
        pending.future.set_result(choice)
        return ResolveResult("approved" if approve else "denied", pending)

    async def wait(self, pending: PendingApproval, timeout: float) -> ApprovalChoice:
        try:
            return await asyncio.wait_for(asyncio.shield(pending.future), timeout=max(1.0, timeout))
        except asyncio.TimeoutError:
            if not pending.future.done():
                pending.future.set_result("timeout")
            return "timeout"
        finally:
            self._pending.pop(pending.approval_id, None)


approval_broker = ApprovalBroker()
_PERMANENT_LOCK = threading.Lock()


def approval_fingerprint(command: str, cwd: str) -> str:
    """为精确命令和工作目录生成不可逆授权指纹。"""
    payload = f"terminal-approval-v1\0{cwd}\0{command}".encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


_UNSAFE_SHELL_SYNTAX = frozenset("|;&<>`$()\n\r")
_NO_BROAD_RULE_COMMANDS = {"curl", "wget", "rm", "chmod", "chown", "mv", "cp", "dd"}
_CWD_AGNOSTIC_COMMANDS = {"apt", "apt-get", "dnf", "yum", "pacman", "systemctl", "service"}


def _command_tokens(command: str) -> list[str]:
    if any(char in command for char in _UNSAFE_SHELL_SYNTAX):
        return []
    try:
        return shlex.split(command, posix=True)
    except ValueError:
        return []


def suggest_prefix_rule(command: str, cwd: str) -> dict | None:
    """Return a conservative, user-readable rule for repeated approval."""
    tokens = _command_tokens(command)
    if not tokens:
        return None
    offset = 1 if tokens[0] == "sudo" else 0
    if offset >= len(tokens):
        return None
    executable = tokens[offset].rsplit("/", 1)[-1]
    if executable in _NO_BROAD_RULE_COMMANDS:
        return None
    if executable == "git":
        if len(tokens) <= offset + 1 or tokens[offset + 1] != "push" or any(value in {"-f", "--force", "--force-with-lease"} for value in tokens):
            return None
        length = offset + 2
    else:
        if len(tokens) <= offset + 1:
            return None
        length = min(len(tokens), offset + 2)
    prefix = tokens[:length]
    rule_cwd = "" if executable in _CWD_AGNOSTIC_COMMANDS else cwd
    return {"version": 1, "prefix": prefix, "cwd": rule_cwd}


def rule_label(rule: dict | None) -> str:
    if not rule:
        return ""
    return " ".join(shlex.quote(str(token)) for token in rule.get("prefix", []))


def rule_matches(rule: object, command: str, cwd: str) -> bool:
    if not isinstance(rule, dict) or rule.get("version") != 1:
        return False
    prefix = rule.get("prefix")
    if not isinstance(prefix, list) or not prefix or not all(isinstance(token, str) for token in prefix):
        return False
    rule_cwd = rule.get("cwd", "")
    if rule_cwd and rule_cwd != cwd:
        return False
    tokens = _command_tokens(command)
    return len(tokens) >= len(prefix) and tokens[:len(prefix)] == prefix


def is_permanently_allowed(user_id: int, command: str, cwd: str) -> bool:
    from infrastructure.cache import cache

    values = cache.get_settings(user_id).get("terminal_approvals", [])
    if not isinstance(values, list):
        return False
    fingerprint = approval_fingerprint(command, cwd)
    return fingerprint in values or any(rule_matches(rule, command, cwd) for rule in values)


def add_permanent_approval(user_id: int, rule: dict) -> None:
    """Persist a structured command-prefix rule without storing command arguments."""
    from infrastructure.cache import cache, sync_to_database

    with _PERMANENT_LOCK:
        current = cache.get_settings(user_id).get("terminal_approvals", [])
        previous = list(current) if isinstance(current, list) else []
        if rule in previous:
            return
        approvals = (previous + [rule])[-500:]
        cache.update_settings(user_id, "terminal_approvals", approvals)
        try:
            sync_to_database()
        except Exception:
            cache.update_settings(user_id, "terminal_approvals", previous)
            raise
