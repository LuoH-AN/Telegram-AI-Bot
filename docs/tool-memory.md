# memory 工具归档

## 工具定位
`memory` 是运行时工具系统里最轻量、也最贴近主对话链路的一个工具。它的目标不是查询外部数据，而是把“值得长期记住的信息”写回项目自己的记忆系统，供后续会话检索和注入系统提示词。

对应实现：`tools/memory.py`

## 对外暴露的函数
- 工具名：`save_memory`
- 参数：
  - `content: string`：需要记住的事实性描述

OpenAI function schema 在 `MEMORY_TOOL` 常量中定义，属于标准 `type=function` 形式。

## 运行时执行流程
1. 模型在回复过程中决定调用 `save_memory`
2. 工具注册中心把调用分发到 `MemoryTool.execute()`
3. `execute()` 从 `arguments` 中提取 `content`
4. 若 `content` 非空，则调用 `services.memory.add_memory(user_id, content, source="ai")`
5. 工具本身返回 `None`
6. 注册中心会把 `None` 统一转成 `OK` 形式的 tool result，继续喂回模型

这意味着它本质上是一个 **fire-and-forget side effect tool**：真正重要的是写入动作，而不是返回文本。

## 与提示词系统的耦合
`memory` 不只负责“写”，还负责“读”。

`MemoryTool.enrich_system_prompt()` 会：
1. 从调用方拿到 `query`（用户当前问题）
2. 调用 `services.memory.format_memories_for_prompt(user_id, query=query)`
3. 如果有可注入的记忆文本，就把它拼到当前 `system_prompt` 后面

也就是说，在旧架构里：
- `save_memory` 负责沉淀长期信息
- `enrich_system_prompt()` 负责把相关记忆重新喂给模型

这让 `memory` 成为一个同时参与 **写入链路** 和 **提示词增强链路** 的特殊工具。

## 工具指令
`get_instruction()` 会给模型追加一句额外说明，大意是：
- 可以使用 `save_memory`
- 适合记录用户偏好、事实、长期上下文

旧系统借此诱导模型主动决定“哪些内容值得记住”。

## 依赖关系
- `tools/registry.BaseTool`
- `services.memory.add_memory`
- `services.memory.format_memories_for_prompt`

## 设计特点
### 1. 极简执行
执行逻辑几乎不做复杂校验，只判断 `content` 是否为空。

### 2. 读写分离但挂在同一工具类中
这是它最关键的结构特点：
- `execute()` 处理写入
- `enrich_system_prompt()` 处理读取/注入

### 3. 强依赖用户作用域
所有记忆操作都基于 `user_id`，不是 persona 级别，而是用户级别共享记忆。

## 如果以后要恢复
最小恢复版本需要：
1. 恢复 `save_memory` 的 schema 定义
2. 恢复 `MemoryTool.execute()` 到 `services.memory.add_memory()` 的调用
3. 在主聊天链路恢复 `enrich_system_prompt()` 钩子
4. 在工具注册中心重新注册 `MemoryTool()`

## 恢复时建议
如果以后只想恢复“记忆能力”而不恢复完整工具系统，可以直接改成两段式：
- 在主聊天逻辑中显式做记忆注入
- 提供一个受控的“是否保存记忆”策略，而不是继续完全依赖模型自由调用工具

这样可以保留记忆系统的价值，同时减少 function-calling 依赖。
