---
name: memory
version: 1.0.0
description: Save stable user preferences and facts to long-term memory.
entry_point: infrastructure.plugins.memory.tool:MemoryTool
capabilities: [memory_save, memory_list]
platforms: [telegram]
---

Memory policy:
- Use `save_memory` only for stable user preferences, durable personal facts, or project constraints the user explicitly asks you to remember or clearly states as ongoing context.
- Keep saved memories concise, standalone, and neutral.
- Do not save secrets, API keys, one-off task details, transient conversation content, or sensitive inferences.
- Do not save a memory if the same fact is already present in the provided user memories.
