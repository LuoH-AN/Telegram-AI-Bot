"""Tools module — register tools and expose public API.

Supports two calling methods:
1. Telegram Bot: Use ToolRegistry (get_definitions, process_tool_calls, etc.)
2. MCP Clients: Use get_mcp_server() to get an MCP server instance
"""

import logging
import os
import threading
from typing import Callable

from .registry import registry
from .memory import MemoryTool
from .search import SearchTool
from .fetch import FetchTool
from .wikipedia import WikipediaTool
from .tts import TTSTool, drain_pending_tts_jobs
from .shell import ShellTool
from .cron import CronTool
from .playwright import PlaywrightTool, drain_pending_screenshots, prewarm_playwright_worker
from .crawl4ai import Crawl4AITool, prewarm_crawl4ai_runtime
from .browser_agent import BrowserAgentTool, prewarm_browser_agent_worker

logger = logging.getLogger(__name__)


def _env_bool(name: str, default: bool) -> bool:
    raw = (os.getenv(name) or "").strip().lower()
    if not raw:
        return default
    if raw in {"1", "true", "yes", "on", "y"}:
        return True
    if raw in {"0", "false", "no", "off", "n"}:
        return False
    return default


def _prewarm_browser_tools_impl() -> None:
    logger.info("Browser prewarm started")

    tasks: list[tuple[str, Callable[[], tuple[bool, str]]]] = [
        ("playwright", prewarm_playwright_worker),
        ("browser_agent", prewarm_browser_agent_worker),
    ]

    if _env_bool("BROWSER_AUTO_START_CRAWL4AI", True):
        tasks.append(("crawl4ai", prewarm_crawl4ai_runtime))

    for name, fn in tasks:
        try:
            ok, detail = fn()
            if ok:
                logger.info("Browser prewarm ok: %s (%s)", name, detail)
            else:
                logger.warning("Browser prewarm failed: %s (%s)", name, detail)
        except Exception as e:
            logger.exception("Browser prewarm crashed: %s (%s)", name, e)

    logger.info("Browser prewarm completed")


def prewarm_browser_tools() -> None:
    """Best-effort startup warmup for browser-based tools.

    Env:
    - BROWSER_AUTO_START=1/0 (default: 1)
    - BROWSER_AUTO_START_BACKGROUND=1/0 (default: 1)
    - BROWSER_AUTO_START_CRAWL4AI=1/0 (default: 1)
    """
    if not _env_bool("BROWSER_AUTO_START", True):
        logger.info("Browser prewarm disabled by BROWSER_AUTO_START=0")
        return

    if _env_bool("BROWSER_AUTO_START_BACKGROUND", True):
        thread = threading.Thread(target=_prewarm_browser_tools_impl, daemon=True, name="browser-prewarm")
        thread.start()
    else:
        _prewarm_browser_tools_impl()

# Register all tools
registry.register(MemoryTool())
registry.register(SearchTool())
registry.register(FetchTool())
registry.register(WikipediaTool())
registry.register(TTSTool())
registry.register(ShellTool())
registry.register(CronTool())
registry.register(PlaywrightTool())
registry.register(Crawl4AITool())
registry.register(BrowserAgentTool())

# Public API for Telegram Bot (existing method)
get_all_tools = registry.get_definitions
process_tool_calls = registry.process_tool_calls
get_tool_instructions = registry.get_instructions
enrich_system_prompt = registry.enrich_system_prompt
post_process_response = registry.post_process

# TTS side-channel delivery API
drain_pending_voice_jobs = drain_pending_tts_jobs

# Playwright side-channel delivery API
drain_pending_screenshot_jobs = drain_pending_screenshots

# MCP Server API (for other platforms like Claude Desktop)
from .mcp_server import get_mcp_server, run_mcp_server, create_mcp_server, get_tool_mcp_server, MCP_API_KEY
