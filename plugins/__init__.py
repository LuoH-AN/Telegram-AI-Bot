"""Plugins module — backed by the plugin system.

All public API calls are forwarded to the PluginRegistry singleton.
"""

from plugins.core import registry, get_plugin_manager

get_plugin_manager().discover()

get_all_tools = registry.get_definitions
process_tool_calls = registry.process_tool_calls
get_tool_instructions = registry.get_instructions
enrich_system_prompt = registry.enrich_system_prompt
post_process_response = registry.post_process
