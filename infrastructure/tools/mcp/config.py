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
import re
from dataclasses import dataclass, field
from pathlib import Path

logger = logging.getLogger(__name__)
_NAME_RE = re.compile(r"^[A-Za-z0-9_-]{1,48}$")

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
    access: str = "admin"


def validate_servers_payload(raw) -> list[str]:
    """Return structural errors that would otherwise make entries disappear."""
    if not isinstance(raw, list):
        return ["MCP config must be a JSON list"]
    errors: list[str] = []
    seen_names: set[str] = set()
    for index, item in enumerate(raw):
        label = f"entry {index + 1}"
        if not isinstance(item, dict):
            errors.append(f"{label} must be an object")
            continue
        name = str(item.get("name") or "").strip()
        transport = str(item.get("transport") or "http").strip().lower()
        access = str(item.get("access") or "admin").strip().lower()
        if not _NAME_RE.fullmatch(name):
            errors.append(f"{label} has an invalid name")
        elif name in seen_names:
            errors.append(f"{label} duplicates server name '{name}'")
        else:
            seen_names.add(name)
        if transport not in {"http", "sse", "stdio"}:
            errors.append(f"{label} has an invalid transport")
        if access not in {"admin", "user"}:
            errors.append(f"{label} has an invalid access value")
        if not isinstance(item.get("env") or {}, dict) or not isinstance(item.get("headers") or {}, dict):
            errors.append(f"{label} env and headers must be objects")
        if not isinstance(item.get("args") or [], list):
            errors.append(f"{label} args must be a list")
        if transport in {"http", "sse"} and not str(item.get("url") or "").strip():
            errors.append(f"{label} requires a URL")
        if transport == "stdio" and not str(item.get("command") or "").strip():
            errors.append(f"{label} requires a command")
    return errors


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
    validation_errors = validate_servers_payload(raw)
    if validation_errors:
        logger.warning("MCP config %s rejected: %s", config_path, "; ".join(validation_errors))
        return []

    servers: list[McpServerConfig] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name") or "").strip()
        transport = str(item.get("transport") or "http").strip().lower()
        access = str(item.get("access") or "admin").strip().lower()
        if not _NAME_RE.fullmatch(name) or transport not in {"http", "sse", "stdio"} or access not in {"admin", "user"}:
            logger.warning("MCP entry skipped (bad name/transport): %s", item)
            continue
        raw_env = item.get("env") or {}
        raw_headers = item.get("headers") or {}
        raw_args = item.get("args") or []
        if (not isinstance(raw_env, dict) or not isinstance(raw_headers, dict)
                or not isinstance(raw_args, list)):
            logger.warning("MCP entry skipped (env/headers objects and args list required): %s", name)
            continue
        if transport in {"http", "sse"} and not str(item.get("url") or "").strip():
            logger.warning("MCP entry skipped (URL required): %s", name)
            continue
        if transport == "stdio" and not str(item.get("command") or "").strip():
            logger.warning("MCP entry skipped (command required): %s", name)
            continue
        servers.append(McpServerConfig(
            name=name,
            transport=transport,
            url=str(item.get("url") or ""),
            command=str(item.get("command") or ""),
            args=[str(a) for a in raw_args if a is not None],
            env={str(k): str(v) for k, v in raw_env.items()},
            headers={str(k): str(v) for k, v in raw_headers.items()},
            access=access,
        ))
    return servers
