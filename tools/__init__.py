"""Tools module — register tools and expose public API."""

from .registry import registry
from .memory import MemoryTool
from .search import SearchTool
from .fetch import FetchTool
from .wikipedia import WikipediaTool

# Register all tools
registry.register(MemoryTool())
registry.register(SearchTool())
registry.register(FetchTool())
registry.register(WikipediaTool())

# Public API
get_all_tools = registry.get_definitions
process_tool_calls = registry.process_tool_calls
get_tool_instructions = registry.get_instructions
enrich_system_prompt = registry.enrich_system_prompt
post_process_response = registry.post_process
