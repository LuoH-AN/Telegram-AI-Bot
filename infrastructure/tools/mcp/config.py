"""MCP server configuration: load runtime/mcp_servers.json.

Schema (JSON, list of server entries):

    [
      {"name": "fetch", "transport": "http", "url": "https://mcp.example.com/mcp"},
      {"name": "fs", "transport": "sse", "url": "https://mcp.example.com/sse"},
      {"name": "git", "transport": "stdio", "command": "mcp-server-git", "args": ["--repo", "/repo"]}
    ]

Path is overridable via MCP_SERVERS_FILE env. Each server's tools register as
native ToolEntry names `<server>__<tool>` to avoid collisions with builtins.
"""

from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass, field
from pathlib import Path

logger = logging.getLogger(__name__)

DEFAULT_CONFIG_PATH = Path(os.getenv("MCP_SERVERS_FILE", "runtime/mcp_servers.json"))


@dataclass(frozen=True)
class McpServerConfig:
    name: str
    transport: str  # "http" | "sse" | "stdio"
    url: str = ""
    command: str = ""
    args: list[str] = field(default_factory=list)
    env: dict[str, str] = field(default_factory=dict)
    headers: dict[str, str] = field(default_factory=dict)


def load_servers(path: Path | None = None) -> list[McpServerConfig]:
    config_path = Path(path) if path else DEFAULT_CONFIG_PATH
    if not config_path.is_file():
        return []
    try:
        raw = json.loads(config_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        logger.warning("MCP config %s invalid: %s", config_path, exc)
        return []
    if not isinstance(raw, list):
        logger.warning("MCP config %s must be a JSON list", config_path)
        return []

    servers: list[McpServerConfig] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name") or "").strip()
        transport = str(item.get("transport") or "http").strip().lower()
        if not name or transport not in {"http", "sse", "stdio"}:
            logger.warning("MCP entry skipped (bad name/transport): %s", item)
            continue
        servers.append(McpServerConfig(
            name=name,
            transport=transport,
            url=str(item.get("url") or ""),
            command=str(item.get("command") or ""),
            args=[str(a) for a in item.get("args", []) if a is not None],
            env={str(k): str(v) for k, v in (item.get("env") or {}).items()},
            headers={str(k): str(v) for k, v in (item.get("headers") or {}).items()},
        ))
    return servers
