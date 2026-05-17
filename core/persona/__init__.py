"""Persona command use cases shared by all platforms."""

from .command import run_persona_command
from .prompt_from_text import apply_global_prompt_from_text, apply_persona_prompt_from_text

__all__ = [
    "run_persona_command",
    "apply_persona_prompt_from_text",
    "apply_global_prompt_from_text",
]

