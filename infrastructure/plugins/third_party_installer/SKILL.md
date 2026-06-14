---
name: third_party_installer
version: 1.0.0
description: Guide third-party CLI setup and convert external integrations into this agent's runtime plugins.
capabilities: [install_guidance, plugin_generation, cli_verification]
platforms: [telegram]
---

When the user asks to install a third-party CLI, skill pack, or agent integration, do the setup end to end.

Use this workflow:

1. Install and verify the third-party CLI with `terminal`.
2. If the user asks for that tool's own skill installer, run it with `terminal`; treat it as that tool's setup only.
3. Inspect official plugin docs. Prefer markdown docs when available, such as `<url>.md`.
4. If there is no native plugin for this Telegram AI Bot, create a prompt-only plugin for this agent with `project_config`.
5. Write the plugin to `runtime/plugins/<name>/SKILL.md` with frontmatter: name, version, description, repository, capabilities, platforms.
6. Put concrete usage rules in the body: which command to run, when to prefer it, how to verify it, and fallbacks.
7. Confirm the plugin is registered by checking `/skill list` behavior when possible, or report that a restart is needed.
8. Verify the third-party tool with a real sample command and show the important result to the user.

Do not use `/skill install` as the default path for third-party setup. Use it only when the user explicitly asks for that command or when installing a plugin package already built for this agent.

Generated prompt-only plugins should be specific to the tool being installed, but the generation process is generic:

- Derive the plugin name from the tool name, normalized for paths.
- Copy only stable behavior from official docs, not marketing text.
- Include exact commands discovered during installation.
- Include verification commands that the model can run later.
- Include fallback behavior when the CLI or external service is unavailable.
- Avoid hardcoding one vendor's installation flow into this plugin; generate a tool-specific plugin from the requested tool's docs each time.
