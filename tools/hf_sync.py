"""HuggingFace Dataset sync tool for AI — backup/restore skill data."""

from __future__ import annotations

import logging

from .base import BaseTool
from services.skills import (
    persist_skill_state,
    persist_skill_snapshot,
    restore_skill,
    restore_skill_snapshot,
    list_skill_snapshots,
)

logger = logging.getLogger(__name__)

_VALID_ACTIONS = {"persist", "restore", "snapshot", "list_snapshots"}


class HFSyncTool(BaseTool):
    """Tool for AI to backup/restore skill data to/from HuggingFace Dataset."""

    @property
    def name(self) -> str:
        return "hf_sync"

    def definitions(self) -> list[dict]:
        return [
            {
                "type": "function",
                "function": {
                    "name": "hf_sync",
                    "description": (
                        "将技能数据备份到 HuggingFace Dataset 或从其恢复。"
                        "支持的操作：persist（备份最新状态）、restore（从HF恢复）、"
                        "snapshot（创建命名快照并备份）、list_snapshots（列出所有快照）。"
                        "用户要求备份、上传、恢复、快照技能数据时使用此工具。"
                    ),
                    "parameters": self._parameters(),
                },
            }
        ]

    def _parameters(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["persist", "restore", "snapshot", "list_snapshots"],
                    "description": (
                        "操作类型：persist=备份技能最新状态到HF，"
                        "restore=从HF恢复技能数据，"
                        "snapshot=创建命名快照并备份到HF，"
                        "list_snapshots=列出技能的所有快照"
                    ),
                },
                "skill_name": {
                    "type": "string",
                    "description": "目标技能名称",
                },
                "snapshot_id": {
                    "type": "string",
                    "description": "快照ID，仅在 snapshot/restore 操作时使用。snapshot时为空则自动生成，restore时为空则恢复最新状态。",
                },
            },
            "required": ["action", "skill_name"],
        }

    def execute(self, user_id: int, tool_name: str, arguments: dict) -> str:
        action = str(arguments.get("action", "")).strip().lower()
        skill_name = str(arguments.get("skill_name", "")).strip()
        snapshot_id = str(arguments.get("snapshot_id", "")).strip() or None

        if not action or action not in _VALID_ACTIONS:
            return f"错误：无效的 action '{action}'，可选值：{', '.join(sorted(_VALID_ACTIONS))}"

        if not skill_name:
            return "错误：skill_name 不能为空"

        logger.info("hf_sync: user=%d, action=%s, skill=%s, snapshot=%s", user_id, action, skill_name, snapshot_id)

        try:
            if action == "persist":
                ok = persist_skill_state(user_id, skill_name)
                return f"技能 '{skill_name}' 备份{'成功' if ok else '失败'}" + ("。" if ok else "，请检查 HF 配置和技能是否存在。")

            if action == "restore":
                ok = restore_skill_snapshot(user_id, skill_name, snapshot_id=snapshot_id)
                label = f"（快照: {snapshot_id}）" if snapshot_id else "（最新状态）"
                return f"技能 '{skill_name}' 恢复{label}{'成功' if ok else '失败'}。"

            if action == "snapshot":
                ok = persist_skill_snapshot(user_id, skill_name, snapshot_id=snapshot_id)
                return f"技能 '{skill_name}' 快照创建{'成功' if ok else '失败'}。"

            if action == "list_snapshots":
                snapshots = list_skill_snapshots(user_id, skill_name)
                if not snapshots:
                    return f"技能 '{skill_name}' 暂无快照。"
                lines = [f"技能 '{skill_name}' 的快照列表："]
                for snap in snapshots:
                    lines.append(f"  - {snap}")
                return "\n".join(lines)

        except Exception as e:
            logger.exception("hf_sync execution failed: %s %s", action, skill_name)
            return f"错误：{action} 操作失败 - {e}"

        return "未知操作。"
