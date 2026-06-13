# 重构收尾待办（已完成）

> 背景：`ecaec4f` 完成了平台裁剪与 Telegram 顶层包迁移。
> 本文记录这次重构后的收尾事项与完成验证。

## 1. [完成] 生命周期命令的导入还指向旧文件

`/stop`、`/update`、`/restart` 三个命令已经被拆分到新文件
`telegram_bot/commands/lifecycle.py`，包入口已改为从 `lifecycle.py` 导入它们:

```python
from .basic import start, help_command, clear
from .lifecycle import stop, update, restart
```

同时修复了同一启动链上发现的旧路径/循环导入问题：

- `telegram_bot/handlers/__init__.py` 改为懒加载重导出，避免导入 `handlers.common` 时反向加载命令包。
- `telegram_bot/handlers/callback.py` 改为从 `telegram_bot.commands.settings` 导入模型键盘。
- 补齐 `platforms/commands/settings/` 下共享 `/set` 命令实现，修复缺失的 `command.py`。

## 2. [完成] `handlers/__init__.py` 的 `__all__` 漏了 `stop`

`telegram_bot/handlers/__init__.py` 里 `stop` 已正常 import,
`__all__` 列表也已包含 `stop`，并验证 `from telegram_bot.handlers import *`
可以导出生命周期命令。

## 3. [完成] 运行时验证

已将项目复制到 `/tmp/Telegram-AI-Bot`，依赖安装到该目录的 `.deps/` 下并完成验证：

- `python3 -m compileall -q ai cache config core database launcher openapi_tools platforms plugins services telegram_bot utils scripts main.py web_app.py`
- `PYTHONPATH=.deps python3 -c "import telegram_bot.commands ..."`
- `PYTHONPATH=.deps TELEGRAM_BOT_TOKEN=123:ABC python3 -c "from telegram_bot.app_builder import build_application ..."`
- `PYTHONPATH=.deps TELEGRAM_BOT_TOKEN=123:ABC python3 -c "... MessageHandler ..."`
- `PYTHONPATH=.deps python3 -m telegram_bot`
- 旧平台/旧路径残留扫描通过。

随后补充了更接近运行时的验证：

- 安装并启动本机 PostgreSQL，使用临时 `gemen_test` 数据库验证 schema 初始化。
- 使用本地 Telegram Bot API mock 跑 `python -m telegram_bot` polling，验证 `/help` update 被处理并回发消息。
- 使用本地 Telegram Bot API mock 投递 photo/document update，验证消息与媒体 handler 被 polling 调度。
- 使用 mock 的 `getFile` 与 `/file/bot...` 下载路径验证文档上传链路，确认 `/set global_prompt` caption 会下载文本文件并更新 prompt。
- 使用 `.env` 的 `DATABASE_URL` 完成真实数据库初始化。
- 使用 `.env` 的 `TELEGRAM_BOT_TOKEN` 与 `TELEGRAM_API_BASE` 完成 `getMe` 校验。
- 使用 `.env` 短时启动 `telegram_bot.app.main()`，验证真实配置下进入 `Starting bot...`、cron scheduler 与 Telegram polling 初始化。

说明：`.env` 未提供全局 `OPENAI_API_KEY`，因此没有发起真实 AI 对话；这不影响本次重构收尾的启动、命令注册、消息处理与媒体上传链路验证。

## 附带清理

同步修正了 README 与 Dockerfile 中仍指向旧目录结构的说明/复制清单。
随后补充了结构一致性清理：

- `platforms.commands` 补齐 `restart_command` 重导出，生命周期命令的共享 API 保持一致。
- `telegram_bot/commands/settings/{command,core,help,runtime}.py` 收敛为兼容导入，`/set` 主实现统一维护在 `platforms/commands/settings/`。
- `telegram_bot.configure_platform_logging()` 改为返回真实 logger，包级 API 与底层实现保持一致。
- 清理只包含历史 `.pyc` 的旧平台目录残留，避免 `platforms/onebot`、`platforms/wechat`、`platforms/telegram`、`platforms/shared` 在本地结构诊断中误报。
- `.dockerignore` 显式保留 `plugins/*/SKILL.md`，避免全局 Markdown 排除规则影响容器内置插件发现。
