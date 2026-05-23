---
name: search
version: 2.0.0
description: Web search via Tavily API with multi-key round-robin and per-key cooldown.
entry_point: plugins.search.tool:SearchTool
capabilities: [search, status]
platforms: [telegram, wechat, onebot]
---
