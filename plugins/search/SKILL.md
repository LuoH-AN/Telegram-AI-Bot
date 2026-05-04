---
name: search
version: 1.0.0
description: Integrated web search with local binary management. Supports install/start/status/stop/search actions.
entry_point: plugins.search.tool:SearchTool
capabilities: [search, status, install, start, stop]
platforms: [telegram, wechat, onebot]
---
