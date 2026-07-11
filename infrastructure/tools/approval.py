"""一次性工具审批状态，供平台按钮恢复原工具调用。"""

from __future__ import annotations

import asyncio
import hashlib
import secrets
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
        self._session_approved: dict[str, set[str]] = {}

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
            future=loop.create_future(),
        )
        self._pending[approval_id] = pending
        return pending

    def get(self, approval_id: str) -> PendingApproval | None:
        return self._pending.get(approval_id)

    def discard(self, approval_id: str) -> PendingApproval | None:
        return self._pending.pop(approval_id, None)

    def allow_session(self, pending: PendingApproval) -> None:
        self._session_approved.setdefault(pending.session_key, set()).add(pending.fingerprint)

    def is_session_allowed(self, session_key: str, fingerprint: str) -> bool:
        return fingerprint in self._session_approved.get(session_key, set())

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


def is_permanently_allowed(user_id: int, fingerprint: str) -> bool:
    from infrastructure.cache import cache

    values = cache.get_settings(user_id).get("terminal_approvals", [])
    return fingerprint in values if isinstance(values, list) else False


def add_permanent_approval(user_id: int, fingerprint: str) -> None:
    """持久保存精确命令指纹，不保存原始命令或其中的秘密。"""
    from infrastructure.cache import cache, sync_to_database

    with _PERMANENT_LOCK:
        current = cache.get_settings(user_id).get("terminal_approvals", [])
        previous = [str(item) for item in current] if isinstance(current, list) else []
        if fingerprint in previous:
            return
        approvals = (previous + [fingerprint])[-500:]
        cache.update_settings(user_id, "terminal_approvals", approvals)
        try:
            sync_to_database()
        except Exception:
            cache.update_settings(user_id, "terminal_approvals", previous)
            raise
