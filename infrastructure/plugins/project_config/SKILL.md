---
name: project_config
version: 1.0.0
description: Read/write config files, prompt-only agent plugin manifests in runtime/plugins, and user database records.
entry_point: infrastructure.plugins.project_config.tool:ProjectConfigTool
capabilities: [file_read, file_write, file_list, plugin_manifest_write, db_get, db_set, db_list]
platforms: [telegram]
---
