"""Memory tool — save important user information across conversations."""

import logging

from .registry import BaseTool
from services.memory import add_memory, format_memories_for_prompt

logger = logging.getLogger(__name__)

# Tool definition (OpenAI function-calling format)
MEMORY_TOOL = {
    "type": "function",
    "function": {
        "name": "save_memory",
        "description": (
            "Save important information about the user that should be remembered "
            "across conversations. Use this for user preferences, facts, context, "
            "or anything worth remembering long-term."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "content": {
                    "type": "string",
                    "description": "The information to remember, written as a brief factual statement",
                }
            },
            "required": ["content"],
        },
    },
}


class MemoryTool(BaseTool):
    """Tool for saving and recalling user memories."""

    @property
    def name(self) -> str:
        return "memory"

    def definitions(self) -> list[dict]:
        return [MEMORY_TOOL]

    def execute(self, user_id: int, tool_name: str, arguments: dict) -> str | None:
        content = arguments.get("content", "").strip()
        if content:
            add_memory(user_id, content, source="ai")
            logger.info(f"Saved memory via tool call: {content[:50]}...")
        return None

    def get_instruction(self) -> str:
        return (
            "\n\nYou can save important information about the user using the save_memory tool. "
            "Use it for preferences, facts, or context worth remembering long-term."
        )

    def enrich_system_prompt(self, user_id: int, system_prompt: str, **kwargs) -> str:
        query = kwargs.get("query")
        memories_text = format_memories_for_prompt(user_id, query=query)
        if memories_text:
            system_prompt += "\n\n" + memories_text
        return system_prompt


