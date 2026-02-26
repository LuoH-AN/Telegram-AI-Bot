"""Tools module — register tools and expose public API.

Supports two calling methods:
1. Telegram Bot: Use ToolRegistry (get_definitions, process_tool_calls, etc.)
2. MCP Clients: Use get_mcp_server() to get an MCP server instance
"""

from .registry import registry
from .memory import MemoryTool
from .search import SearchTool
from .fetch import FetchTool
from .wikipedia import WikipediaTool
from .tts import TTSTool, drain_pending_tts_jobs
from .shell import ShellTool
from .cron import CronTool
from .playwright_tool import PlaywrightTool, drain_pending_screenshots

# Register all tools
registry.register(MemoryTool())
registry.register(SearchTool())
registry.register(FetchTool())
registry.register(WikipediaTool())
registry.register(TTSTool())
registry.register(ShellTool())
registry.register(CronTool())
registry.register(PlaywrightTool())

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
