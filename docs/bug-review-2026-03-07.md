# 项目 Bug 排查记录（2026-03-07）

## 执行概览

- 已执行 `python -m compileall -q .`，通过。
- 已对核心模块做导入检查：`bot`、`tools.*`、`web.app`、`services.conversation_service`、`handlers`、`config`，均可导入。
- 当前未发现语法错误或显式 import 崩溃。
- 当前更值得关注的是并发、一致性、媒体分组和错误暴露这几类逻辑问题。

## 当前确认的重点问题

### 1. 跨进程会话数据不同步

`services/state_sync_service.py` 目前只刷新用户的 settings、personas、tokens，没有刷新 sessions 和 conversations。

相关位置：

- `services/state_sync_service.py:56`
- `services/state_sync_service.py:125`
- `services/state_sync_service.py:145`
- `services/session_service.py:11`
- `web/routes/sessions.py:67`
- `web/routes/sessions.py:159`

影响：

- Telegram / Discord / Web 分进程运行时，一个进程里新建、改名、删除会话，其他进程可能长时间看不到。
- Web 会话列表、消息列表和当前会话状态，可能与 bot 侧实际状态不一致。

建议：

- 在 `refresh_user_state_from_db()` 中补齐 `user_sessions` 与 `user_conversations` 的按用户刷新逻辑。
- 或者在会话查询链路改为优先从数据库读取，避免完全依赖进程内 cache。

### 2. 图片/文件请求的 persona 校验与实际写入对象可能错位

媒体入口先在 `preflight_media_request()` 中读取当前 persona 并校验 token，随后才进入主聊天链路；而主聊天链路里又会重新获取一次当前 persona 和 session。

相关位置：

- `handlers/common.py:153`
- `handlers/common.py:154`
- `handlers/messages/photo.py:70`
- `handlers/messages/document.py:146`
- `handlers/messages/text.py:484`
- `handlers/messages/text.py:485`

影响：

- 如果用户在图片/文件请求处理中切换 persona，可能出现“校验时是 A persona，实际落库/计费时是 B persona”的错位。
- 这会导致 token 配额判断和消息归档对象不一致。

建议：

- 在媒体入口就冻结 `persona_name` 和 `session_id`，并显式传递给 `chat()`。
- 避免 `chat()` 对媒体请求再次读取“当前 persona”。

### 3. media group 仍有被拆成两次处理的风险

当前媒体分组聚合依赖固定的 1 秒等待窗口。若某些媒体分片到达较慢，首个请求可能已经弹出缓冲区，后续分片又会被识别为新的 leader，再触发第二次处理。

相关位置：

- `handlers/common.py:17`
- `handlers/common.py:101`
- `handlers/common.py:104`

影响：

- 用户一组图片/文件偶发被拆成两次分析。
- 轻则重复回复，重则造成重复计费与重复写入会话。

建议：

- 增加“已完成 media_group_id 的短时去重表”。
- 或改为更稳妥的分组收敛策略，而不是纯固定 sleep 窗口。

### 4. Cache 层共享可变对象，线程安全边界不足

项目里同时存在：

- Telegram `concurrent_updates(True)`
- 数据库后台同步线程
- cron 调度线程
- Web 服务线程

但 cache 层多个读取接口直接返回内部 list/dict，可被外部无锁修改；同时增删会话、追加消息等操作也并非全程在统一锁保护下完成。

相关位置：

- `bot.py:124`
- `cache/sync.py:500`
- `services/cron_service.py:394`
- `cache/manager.py:205`
- `cache/manager.py:212`
- `cache/manager.py:233`
- `cache/manager.py:331`
- `cache/manager.py:335`

影响：

- 会话列表或消息列表在并发下可能出现脏读、瞬时不一致、覆盖更新。
- 这类问题通常难复现，但一旦出现会表现为“偶发串台”“列表跳变”“刚写入的消息又没了”。

建议：

- 对 sessions / conversations / personas 等共享结构统一加读写锁策略。
- 读取时返回副本，避免外部直接持有内部可变对象。

### 5. 工具层仍会回传原始异常文本

虽然聊天 handler 已经尽量把失败文案统一成 retry，但多个 tool 仍直接返回原始异常信息。

相关位置：

- `tools/fetch.py:68`
- `tools/fetch.py:85`
- `tools/tts.py:197`
- `tools/shell.py:375`

影响：

- 内部端点、路径、异常细节可能暴露给模型或最终用户。
- 会增加提示词污染和内部实现泄露的风险。

建议：

- tool 返回统一的简洁错误，例如 `Error. Please retry.`。
- 详细异常仅记录在日志中。

## 已确认已修或已有修复痕迹的问题

以下问题从当前代码看，已经有明显修复痕迹：

- `url_fetch` 已加入基础 SSRF 边界限制。
- provider 命令已改为显式 `load` 语义。
- session 新建后的 remap 已覆盖 `deleted_sessions` 与 `dirty_session_titles`。
- 图片/文件入口已接入 token limit 和 media group 聚合预处理。

## 建议修复优先级

1. 先修跨进程会话同步。
2. 再修媒体请求 persona/session 快照错位。
3. 再处理 media group 二次触发问题。
4. 最后系统性收敛 cache 线程安全和 tool 错误回传策略。
