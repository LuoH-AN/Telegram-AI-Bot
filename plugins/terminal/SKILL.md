---
name: terminal
version: 1.0.0
description: Execute terminal commands without sandbox restrictions. Supports foreground command execution and background job management.
entry_point: plugins.terminal.tool:TerminalTool
capabilities: [exec, bg_list, bg_check]
platforms: [telegram, wechat, onebot]
---
