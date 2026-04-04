"""Tools module — register tools and expose public API."""

import logging

from .registry import registry
from .skill_terminal import SkillTerminalTool
from .hf_sync import HFSyncTool

logger = logging.getLogger(__name__)

# Register all tools
registry.register(SkillTerminalTool())
registry.register(HFSyncTool())

# Public API
get_all_tools = registry.get_definitions
process_tool_calls = registry.process_tool_calls
get_tool_instructions = registry.get_instructions
enrich_system_prompt = registry.enrich_system_prompt
post_process_response = registry.post_process
