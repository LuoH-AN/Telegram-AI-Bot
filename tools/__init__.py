"""Tools module — register tools and expose public API."""

from .registry import registry
from .memory import MemoryTool
from .search import SearchTool
from .fetch import FetchTool
from .wikipedia import WikipediaTool
from .tts import TTSTool, drain_pending_tts_jobs

# Register all tools
registry.register(MemoryTool())
registry.register(SearchTool())
registry.register(FetchTool())
registry.register(WikipediaTool())
registry.register(TTSTool())

# Public API
get_all_tools = registry.get_definitions
process_tool_calls = registry.process_tool_calls
get_tool_instructions = registry.get_instructions
enrich_system_prompt = registry.enrich_system_prompt
post_process_response = registry.post_process

# TTS side-channel delivery API
drain_pending_voice_jobs = drain_pending_tts_jobs
