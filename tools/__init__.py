"""Tools module — register tools and expose public API."""

import logging

from .core.registry import registry
from .terminal import TerminalTool
from .hf_sync import HFSyncTool
from .scrapling import ScraplingTool
from .sosearch import SoSearchTool

logger = logging.getLogger(__name__)

# Register all tools
registry.register(TerminalTool())
registry.register(HFSyncTool())
registry.register(ScraplingTool())
registry.register(SoSearchTool())

# Public API
get_all_tools = registry.get_definitions
process_tool_calls = registry.process_tool_calls
get_tool_instructions = registry.get_instructions
enrich_system_prompt = registry.enrich_system_prompt
post_process_response = registry.post_process
