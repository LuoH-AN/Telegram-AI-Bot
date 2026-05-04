---
name: project_config
version: 1.0.0
description: Read and write project configuration files (CLAUDE.md, .env, etc.) and user database records (settings, personas, sessions, conversations, skills).
entry_point: plugins.project_config.tool:ProjectConfigTool
capabilities: [file_read, file_write, file_list, db_get, db_set, db_list]
platforms: [telegram, wechat, onebot]
---
