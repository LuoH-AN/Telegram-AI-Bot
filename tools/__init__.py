"""Tools module — backed by the plugin system.

All public API calls are forwarded to the PluginRegistry singleton
so that existing call sites continue to work unchanged.
"""

from core.plugins import registry, get_plugin_manager

# Trigger plugin discovery on first tools import
get_plugin_manager().discover()

# Re-export the same public API as before — backed by PluginRegistry
get_all_tools = registry.get_definitions
process_tool_calls = registry.process_tool_calls
get_tool_instructions = registry.get_instructions
enrich_system_prompt = registry.enrich_system_prompt
post_process_response = registry.post_process
