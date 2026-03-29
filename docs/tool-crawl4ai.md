# crawl4ai 工具归档

## 工具定位
`crawl4ai` 是旧工具系统里另一套浏览器抓取能力，目标不是截图，而是“尽量稳定地提取适合 LLM 阅读的 markdown-like 内容”。

对应实现：`tools/crawl4ai.py`

## 对外暴露的函数
- `crawl4ai_fetch`
- 参数：
  - `url`
  - `max_length`
  - `focus_selector`

## 核心设计
### 1. 参数极简，策略内置
虽然 Crawl4AI 本身支持很多高级参数，但工具层故意只暴露很少几个。

其余高级配置都在代码里写死为稳定默认值，例如：
- timeout
- delay
- cache_mode
- wait_until
- stealth
- simulate_user
- iframe 处理
- overlay 移除
- magic / navigator override

这样做的目的，是防止模型把复杂浏览器参数调用乱掉。

### 2. 多 attempt profile
`execute()` 内会构造 attempt chain：
- 以同一 URL 为中心
- 生成多套稍有差异的 crawl 配置
- 每轮失败则记录错误摘要
- 有内容就立即返回

这让它更像一个“带重试策略的爬取 orchestrator”。

## 执行流程
1. 校验 URL 公网性
2. 解析 `max_length` 和 `focus_selector`
3. 固定高级 crawl kwargs
4. 调 `_build_attempt_chain()` 生成重试配置链
5. 按顺序 `asyncio.run(self._crawl_url(...))`
6. 拿到文本后做样式块清理与截断
7. 返回文本

## 与 Playwright 的差异
虽然底层也可能借助浏览器，但它和 `playwright` 的目标不同：
- `playwright`：截图 + 直接页面内容读取
- `crawl4ai`：面向 LLM 的正文抽取与抗干扰抓取

也就是说，`crawl4ai` 更偏“内容提纯”，`playwright` 更偏“浏览器操作”。

## 预热逻辑
实现里还有：
- `prewarm_crawl4ai_runtime()`

用于启动时预热依赖，避免首次调用太慢或初始化失败。

## 设计特点
### 1. 强默认、弱暴露
只给模型少量参数，把复杂策略锁在代码里。

### 2. 明确的抗机器人重试链
通过多 profile/多参数尝试来提高成功率。

### 3. 输出面向模型而不是人类浏览
最终目标不是还原页面，而是给 LLM 一段尽量干净的可读文本。

## 如果以后要恢复
建议按以下优先级恢复：
1. URL 安全校验
2. `_crawl_url()` 基础链路
3. `_build_attempt_chain()` 重试策略
4. `focus_selector` 定位提取
5. 预热能力

## 恢复时建议
如果未来恢复这一工具，最好把“默认策略模板”和“尝试链构造”继续保留为内部逻辑，不要重新暴露太多浏览器参数给模型。
