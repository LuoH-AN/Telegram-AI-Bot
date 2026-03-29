# browser_agent 工具归档

## 工具定位
`browser_agent` 是旧工具系统里最复杂的浏览器类工具。和 `playwright`/`crawl4ai` 不同，它不是一次性抓取，而是一个 **有状态、分步执行的浏览器代理**。

对应实现：`tools/browser_agent.py`

## 对外暴露的函数族
它暴露的不是单一函数，而是一整套会话式 API：
- `browser_start_session`
- `browser_list_sessions`
- `browser_get_view_url`
- `browser_close_session`
- `browser_goto`
- `browser_click`
- `browser_type`
- `browser_press`
- `browser_wait_for`
- `browser_get_state`

## 核心设计
### 1. Session 驱动
整个工具围绕 `_sessions: dict[str, dict]` 运转。

模型不是每次独立开浏览器，而是：
1. 先 `browser_start_session`
2. 拿到 `session_id`
3. 后续所有动作都带着 `session_id`
4. 直到 `browser_close_session`

这使它具备连续浏览、跨步骤操作页面的能力。

### 2. Viewer URL
工具会生成只读 viewer 链接：
- `_create_viewer_link()`
- `_get_or_create_viewer_link()`

返回给模型/用户后，可以在外部实时查看当前浏览器会话状态。

这是该工具区别于普通 browser automation 的一个很强特性。

### 3. 真实用户行为模拟
实现里包含大量人类化细节，例如：
- 鼠标移动轨迹不是直线瞬移
- 点击前有 jitter
- click 是 down/up 序列
- context realism / profile 注入
- 页面停留更自然

它不是“能点就行”的自动化，而是在尽量降低反爬和行为异常概率。

## 各动作的职责
### `browser_start_session`
- 启动或复用会话
- 可选起始 URL
- 返回 `session_id` / `viewer_url` / 当前标题和 URL

### `browser_goto`
- 在既有 session 中导航到新页面

### `browser_click`
- 支持 selector/text 定位
- 支持 index/frame_selector
- 内部走更拟人的点击策略

### `browser_type`
- 在输入框键入文本
- 可选先 click，再 type，再回车

### `browser_press`
- 发键盘键，如 Enter/Tab/Escape

### `browser_wait_for`
- 等元素状态，或简单 sleep 等待

### `browser_get_state`
- 返回当前页面快照
- 包括：URL、标题、body_text、可交互元素、iframe 信息等

这通常是模型做下一步决策的关键依据。

## 存储状态恢复
实现还带有 HF dataset store 的状态持久化：
- storage_state 可按 session/user 恢复
- 浏览器状态可在一定程度上跨调用延续

这使它不只是短期 session，还试图保留更长期的登录态/上下文。

## 设计特点
### 1. 它本质上是一个小型浏览器状态机
不是普通工具，而是一组有顺序约束的动作 API。

### 2. 与 viewer 系统深度耦合
会话不仅要跑，还要能可视化。

### 3. 复杂度极高
相比其他工具，它同时包含：
- worker 模型
- session 管理
- viewer token 管理
- 存储状态持久化
- 反爬/真实性策略
- 多种动作 schema

## 如果以后要恢复
恢复顺序建议非常严格：
1. 先恢复 `browser_start_session` / `browser_close_session`
2. 再恢复 `browser_goto`
3. 再恢复 `browser_get_state`
4. 再恢复 `click/type/press/wait_for`
5. 最后恢复 viewer URL 和持久化状态

## 恢复时建议
如果只是想保留“能操作网页”的能力，建议优先恢复：
- start_session
- goto
- get_state
- click
- type

viewer、HF 持久化、多会话上限控制等高级能力可以后补。否则一开始就恢复完整 `browser_agent`，维护和调试成本会非常高。
