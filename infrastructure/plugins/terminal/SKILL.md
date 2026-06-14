---
name: terminal
version: 1.0.0
description: Execute shell commands for CLI installs, verification, downloads, foreground commands, and background jobs.
entry_point: infrastructure.plugins.terminal.tool:TerminalTool
capabilities: [exec, cli_install, download, bg_list, bg_check]
platforms: [telegram]
---
