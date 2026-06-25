# 命令系统重构 TODO

> 本文档由分析会话生成。重启后新开会话,让 Claude 先读本文件即可无缝接手。
> 目标:解决命令系统"太多太杂"——三层抽象却只服务一个平台 + 大量重复死代码。

## 背景:当前架构(三层,但只服务 Telegram 一个平台)

```
app_builder  ── 手写 16 行 name→handler 注册表
   │  handlers/__init__.py 用 __getattr__ 懒加载导出
   ▼
adapters/telegram/commands/   ← 第3层:Telegram 入口 (update,context) → ctx
   ▼
application/commands/          ← 第2层:"跨平台"逻辑 (ctx 协议)  ← 实际无第二个平台
   ▼
application/use_cases/         ← 第1层:平台无关工作流
```

实际入口在 `adapters/telegram/app_builder.py:_register_handlers`。
handler 经 `adapters/telegram/handlers/__init__.py` 的 `__getattr__` 懒加载,
真正命令代码在 `adapters/telegram/commands/`。

## "杂"的 4 个硬证据(已 grep 验证)

1. **逻辑逐字重复**。`/start /clear /stop /update /restart` 在两层各写一遍:
   - `application/commands/basic.py`:`start_command / clear_command / stop_command / update_command / restart_command`
   - `adapters/telegram/commands/basic.py`:`_start / _clear`
   - `adapters/telegram/commands/lifecycle.py`:`_stop / _update / _restart`
   - adapter 入口调本地副本,**不复用**第2层 → 第2层这些命令除 `settings_command` 外基本是死代码。
   - 验证:`grep -rn "from application.commands.basic" --include=*.py` 仅 settings/route.py 引用 `settings_command`。

2. **settings 子包爆炸 + 死 shim**。settings 两层各 6 文件(共12),其中:
   - `adapters/telegram/commands/settings/{core,runtime,help,command}.py` 是 **4 个 5 行纯转发 shim**
   - 验证:`grep` 确认无人引用 `adapters.telegram.commands.settings.core/runtime/help` → 死代码。
   - settings 唯一有 `route.py` 路由层,其他命令没有 → 架构不对称。

3. **ctx 协议无用武之地**。`TelegramCommandContextAdapter` 27 处引用,为"将来加 Discord/网页"而建。
   - 验证:`grep -rln "command_prefix" adapters/ | grep -v telegram` → 空。整个项目只有 Telegram 一个平台。

4. **加一个命令要改 3 处**。手写注册表 + `__getattr__` 导出列表 + 命令本身,命名三层不统一(`start_command`/`start`/`_start`)。

## 硬约束(重构时必须遵守)

- **文件长度 ≤ 100 行**:`scripts/check_file_length.py` 默认 max=100,作用于 application/domain/adapters/infrastructure/shared。
  → 这是 settings 当初被拆子包的原因。拍平时不能把命令塞进超长文件。
- **无测试、无 telegram 库**:无法靠运行验证。每步用 `python3 -m py_compile` + `grep` 调用链 + 严守 100 行 + 推理验证。
- **py3.10**:注意不要用 3.11+ 语法。

## 三阶段执行计划(按"避免返工"排序)

### 阶段 A:删死代码(零风险)
- [x] A1. 删 `adapters/telegram/commands/settings/core.py`、`runtime.py`、`help.py`、`command.py` 这 4 个 5 行死 shim。
      先 `grep` 复核无引用(应只剩 shim 自身),再删。✅ 已删,`py_compile` + grep 通过(无悬空引用;`__init__.py` 只 import `.model`/`.route`)。
- [x] A2. (并入阶段 B)adapter 的 `_start/_clear/_stop/_update/_restart` 去重。
      按"第2层实际没人用"分支处理:阶段 B 直接删 `application/commands/`,所以本步的去重由 B 的合并达成,不单独做(单独做会返工)。
- [x] A3. 统一命名:并入阶段 C(注册表统一命名风格)。
- [x] A4. `py_compile` + `grep` 调用链 + `check_file_length.py` 验证。✅ A1 后已验证。

### 阶段 B:拍平两层(中风险,根治"杂")✅ 已完成
目标:三层 → 两层(`use_cases` + `adapters/telegram/commands`),干掉 ctx 协议。
- [x] B1. 评估 `application/commands/*` 每个文件:`basic/account/chat/memory/persona` 是纯重复(adapter 已有等价实现)→ 删;
      `settings/*` 有真实编排逻辑 → 整体迁入 adapter settings 子包;`settings_command`/`set_command` 逻辑并入 `settings/route.py`+`command.py`。
- [x] B2. 逐命令迁移:adapter 命令合并本地 `_x` 副本,直接用 `(update, context)`,回复改用 `adapters.telegram.rich_text.reply_rich_text`(与原 `ctx.reply_text` 等价的 markdown→HTML),
      `ctx.session_user_id` → `update.effective_user.id`,去掉 `TelegramCommandContextAdapter`。`/export` 的 `reply_document_buffer` 内联(唯一调用点)。
- [x] B3. 删除整个 `application/commands/`,删除 `adapters/telegram/commands/context.py`。附带:`infrastructure/plugins/core/commands.py` 的 `dispatch_skill_command(ctx)` 改为 `dispatch_skill_command(user_id)`,去掉 `_user_id` getattr 兜底(更明确)。
- [x] B4. 修正 import:`route.py` 不再 import `application.commands`;`handlers/__init__.py`、`app_builder`、`callback.py` 经 AST 验证导出面不变(`_build_model_keyboard` 仍由 settings 子包导出)。
- [x] B5. 每步 `py_compile` + grep;严守 100 行(settings 子包拆分保留:route/command/core/help/model/runtime,model.py 最大 93 行)。
- [x] B6. 全局 grep:`TelegramCommandContextAdapter` / `application.commands` / 适配器命令里的 `ctx.` 全部为 0;`from application` 仅剩 `application.use_cases`(正确)。
- 验证:全树 `py_compile` 通过;`check_file_length.py` 仍 26 项违规(全部为既有,无新增;plugins/core/commands.py 154→145)。

### 阶段 C:注册表化(让加命令只改一处)✅ 已完成
- [x] C1. 命令注册机制:`adapters/telegram/commands/registry.py` 定义 `@command(name, *, usage, help)` 装饰器 + `all_commands()`,`Command` dataclass(name/usage/help/handler)。
- [x] C2. 每个命令自描述 name + usage + help:17 个 handler 全部加 `@command(...)`(usage/help 字符串取自原手写 help 文案)。
- [x] C3. `app_builder._register_handlers` 改为 `for cmd in all_commands(): add_handler(CommandHandler(cmd.name, cmd.handler))`,删掉 16 行手写 name→handler 表;app_builder 从 102→68 行(不再超长)。
- [x] C4. `help_command` 从 `all_commands()` 渲染:`build_help_message(prefix, commands)` 改为接收 `(usage,help)` 列表(shared 层只做格式化,数据由 adapter 注入——不破坏分层)。手写 help 命令清单消除。
- [x] C5. `handlers/__init__.py` 删掉 `_COMMAND_EXPORTS`(命令名不再经此懒加载,app_builder 直接用注册表);仅保留 message/callback/common 的 `__getattr__`。
- [x] C6. 命名统一:三层 → 一层后,17 个 handler 全部 `<name>_command`(start→start_command、clear→clear_command、stop/update/restart/status 同理);telegram 命令名只在装饰器里声明一次(同时驱动路由与 /help)。
- [x] C7. 全树 `py_compile` 通过;`check_file_length.py` 26→25(修复 app_builder,无新增);AST 验证 17 命令/17 唯一名/全 async/无悬空 import。
- 净效果:加一个命令从"改 3 处(手写注册表 + `__getattr__` 导出 + 命令本身,且 name 重复登记在注册表与 help 文案)"→"写带 `@command(...)` 的 handler + `__init__.py` 加一行 import",name/help 单次声明。

## 验证 checklist(每阶段结束跑一遍)✅ 全通过
- [x] `python3 -m py_compile $(find application adapters/telegram -name "*.py")` 无报错
- [x] `python3 scripts/check_file_length.py` 无新增违规(26→25,仅修复 app_builder)
- [x] `grep -rn "TelegramCommandContextAdapter\|application.commands" --include=*.py adapters/` 符合预期(阶段B/C后为 0)
- [x] `app_builder._register_handlers` 注册的命令名 = 实际存在的命令,无悬空 import(AST 验证 17 命令/17 唯一名/handler 全部绑定存在)

## 最终结果(三阶段全部完成)
- **删**:`application/commands/`(12 文件,整层重复死代码)、`adapters/telegram/commands/context.py`(ctx 协议)、4 个 settings 死 shim。
- **加**:`adapters/telegram/commands/registry.py`(注册表)+ 5 个 settings 真实逻辑文件(吸收原 application 层编排)。
- **改**:`app_builder` 注册表化(102→68 行);`help` 由注册表生成;`handlers/__init__.py` 去命令懒加载;`build_help_message` 改为数据注入;`dispatch_skill_command` 收 `user_id` 而非 duck-type ctx。
- 净变更:**+243 / −940 行**。三层 → 两层(`use_cases` + `adapters/telegram/commands`),ctx 协议消除,加命令 ≈ 单点。

## 环境信息
- 项目现位于:`/tmp/Telegram-AI-Bot`(已从 /root 移来,git 在 1f87697,干净)
- Python:`/usr/bin/python3` (3.10.12),**无 telegram 库、无 pytest**
- 文件长度脚本:`scripts/check_file_length.py` (max=100)
- git safe.directory 已加:`/tmp/Telegram-AI-Bot`
- CLAUDE.md 约束:单一职责、节俭、少注释、不加签名
