对于 urlfetch 那部分你进行检测只允许 https http 这样的让他访问不到内部去拒绝你说的那些

图片/文件消息处理在 async handler 中执行阻塞式流读取这个问题你直接去修复就行

会话临时 ID 映射不完整，可能导致“已删除会话落库”或标题更新丢失这个问题你直接修复

并发更新下 persona/session 上下文可能错位写入 Token 限额可通过图片/文件入口绕过这个问题你直接修复

错误信息的那个，就不要返回给用户了
直接说 error 让他 retry

然后还有些我实际使用过程中的问题
Set provider save/load/delete/list
这个东西
我的理解是 /set provider load 名字
这样的
但是实际上/set provider 名字这样子是去加载
请你修复一下

第二个当我的一条消息里面有多个图片或文件的时候
他没有当成一条消息来处理
而是有多少图片或文件就有多少条消息来处理
请你修复一下

现在请你先 plan 一下修复计划
然后写入 md
然后你去清除上下文来修复# 项目代码审查报告（2026-02-20）

## 审查范围
- 入口与配置：`bot.py`、`config/`、`database/`、`cache/`
- 业务层：`services/`、`ai/`、`tools/`
- 交互层：`handlers/`、`utils/`
- 运行核查：基础语法编译检查、测试可用性检查

## 执行核查结果
- `python -m compileall -q .`：通过
- `pytest -q`：失败（环境中无 `pytest` 命令）
- `.venv/bin/pytest`：不存在
- 仓库内测试文件检索（`rg --files -g '*test*'`）：未发现测试文件

## 重点问题（按严重级别）

### 1. 高危：`url_fetch` 存在 SSRF 风险，缺少 URL 安全边界
- 证据：
  - `tools/fetch.py:88` 直接接收模型/用户提供的 URL
  - `tools/fetch.py:111` 直接对 URL 发起请求（`self._session.get(url)`）
  - `tools/fetch.py:156` 将 URL 直接转发到外部抓取服务
- 影响：
  - 可被诱导访问内网/本地地址（如 `localhost`、`169.254.169.254` 等），存在凭据/元数据泄露风险。
  - 在部署到云环境时，风险等级显著提升。
- 建议修复：
  - 强制仅允许 `http`/`https`。
  - 拒绝私网、回环、本地链路、`.local` 域名与裸 IP 的敏感网段。
  - 跳转后逐跳校验目标地址，避免通过 30x 绕过。
  - 增加可配置 allowlist（域名或前缀）用于生产环境。

### 2. 高危：图片/文件消息处理在 async handler 中执行阻塞式流读取
- 证据：
  - `handlers/messages/photo.py:116` 创建同步流，`handlers/messages/photo.py:128` 直接 `for chunk in stream`
  - `handlers/messages/document.py:175`、`handlers/messages/document.py:187`
  - `handlers/messages/document.py:288`、`handlers/messages/document.py:300`
- 影响：
  - 在单事件循环下，这类阻塞调用会拖慢其他更新处理，表现为延迟上升、吞吐下降。
  - 大图/大文件场景下更明显，用户会感知“机器人卡住”。
- 建议修复：
  - 统一复用 `handlers/messages/text.py` 中的 `run_in_executor` 模式。
  - 或替换为真正异步的 API 客户端调用链路。

### 3. 高危：会话临时 ID 映射不完整，可能导致“已删除会话落库”或标题更新丢失
- 证据：
  - 新会话使用内存临时 ID：`cache/manager.py:199`、`cache/manager.py:213`
  - 删除会话记录的是该临时 ID：`cache/manager.py:223`
  - 同步时新会话会被替换为 DB ID：`cache/sync.py:325`
  - 仅对 `dirty["conversations"]` / `dirty["cleared_conversations"]` 做了 remap：`cache/sync.py:332`
  - 但 `dirty["deleted_sessions"]` 与 `dirty["dirty_session_titles"]` 未 remap，后续仍用旧 ID 执行：
    - `cache/sync.py:356`
    - `cache/sync.py:364`
- 影响：
  - “创建后立即删除（尚未同步）”的会话，可能被插入数据库后未真正删除。
  - 会话标题更新在 ID 变更时可能静默失败。
- 建议修复：
  - 在 `session["id"] = db_id` 后，补齐对 `dirty["deleted_sessions"]` 和 `dirty["dirty_session_titles"]` 的 ID 重写。
  - 为该流程补充单测：创建->改名->删除（均在一次 sync 前）应最终无残留。

### 4. 中危：Token 限额可通过图片/文件入口绕过
- 证据：
  - 文本入口有显式限额检查：`handlers/messages/text.py:227`
  - 图片入口无对应检查：`handlers/messages/photo.py:30`
  - 文件入口无对应检查：`handlers/messages/document.py:47`
- 影响：
  - 用户达到限额后仍可通过图片/文件继续消耗模型 token，导致配额策略不一致。
- 建议修复：
  - 提取统一 preflight 校验（API Key、限额、群聊触发条件）并在三类 handler 复用。

### 5. 中危：并发更新下 persona/session 上下文可能错位写入
- 证据：
  - 启用了并发更新：`bot.py:105`
  - 文本处理开始读取当前上下文：`handlers/messages/text.py:217`
  - 处理结束再按“当前状态”写入消息与 token：`handlers/messages/text.py:395`、`handlers/messages/text.py:408`
  - 图片/文件也存在同类隐式写入：`handlers/messages/photo.py:167`、`handlers/messages/document.py:221`
- 影响：
  - 若用户在一次长响应中切换 persona/session，数据可能落到非预期 persona/session。
- 建议修复：
  - 在请求开始时固定 `persona_name` 和 `session_id`，后续所有读写都显式传递。
  - 对同一用户引入“单飞”锁（或会话级锁）防止并行请求互相污染。

### 6. 低危：错误信息直接回显给用户，可能暴露内部细节
- 证据：
  - `handlers/messages/text.py:412`
  - `handlers/messages/photo.py:188`
  - `handlers/messages/document.py:129`
- 影响：
  - 外部用户可看到底层异常字符串（供应商、端点、请求细节），增加信息泄露面。
- 建议修复：
  - 用户侧统一返回友好错误文案（如“请求失败，请稍后重试”）。
  - 详细异常仅保留在服务端日志。

## 其他观察
- 项目分层结构清晰（`handlers -> services -> cache/database`），可维护性基础较好。
- 但目前缺少自动化测试，且存在多个“并发+同步落库”的边界路径，建议尽快补齐关键回归测试。

## 建议优先级
1. 先修复 SSRF 与会话 ID remap 缺陷（安全与数据一致性优先）。
2. 修复图片/文件阻塞式流读取与限额绕过（稳定性与成本控制）。
3. 统一并发上下文快照策略，并补充回归测试。
