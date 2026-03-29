# search 工具归档

## 工具定位
`search` 是旧工具系统里的通用联网检索工具，用来获取“当前网络信息”。它同时封装了两个不同来源：
- Browserless + Bing HTML 抓取
- Ollama 原生 web search API

对应实现：`tools/search.py`

## 对外暴露的函数
- 工具名：`web_search`
- 参数：
  - `query: string`：搜索词
  - `provider: string`：`browserless` / `ollama` / `all`
  - `max_results: integer`：1~10，默认 5

## 运行时执行流程
1. 模型调用 `web_search`
2. `SearchTool.execute()` 校验工具名
3. 读取 `query`
4. 解析 provider：
   - `all/both/auto` → 同时走两个 provider
   - 单 provider → 只调用对应实现
5. 解析 `max_results`
6. 逐个 provider 执行检索
7. 合并结果并按 URL 去重
8. 返回格式化后的文本列表

输出格式大致是：
- 序号
- provider 名
- 标题
- URL
- snippet

## Browserless 路径
### 实现方式
`_browserless_search()` 并没有直接调用搜索 API，而是：
1. 用 Bing 搜索 URL 模板拼接查询
2. 调 Browserless `/content`
3. 拿到搜索结果 HTML
4. 通过正则拆分 `<li class="b_algo">` 结果块
5. 提取标题、链接、摘要
6. 解析 Bing 跳转 URL

### 特点
- 优点：不需要单独的 Bing Search API
- 缺点：依赖 HTML 结构，脆弱，页面结构变化就可能失效

## Ollama 路径
### 实现方式
`_ollama_search()` 直接请求：
- `POST https://ollama.com/api/web_search`

请求体：
- `query`
- `max_results`

认证依赖：
- `OLLAMA_API_KEY`

### 特点
- 比 HTML 解析更稳定
- 结构化返回更干净
- 但依赖 Ollama 的服务可用性和接口兼容性

## 合并策略
两路搜索结果统一合并后，会：
1. 以 URL 小写值作为 dedup key
2. 保持先到先保留
3. 最终只保留 `max_results` 条

这说明它不是严格排序融合，而是一个简单的“拼接 + 去重 + 截断”模型。

## 进度事件
工具内部会通过 `emit_tool_progress()` 上报进度，例如：
- 当前使用哪个 provider 搜索

这在旧 UI 里可用于显示“正在搜索中”的状态文案。

## 依赖关系
- `requests`
- `Browserless API token`
- `OLLAMA_API_KEY`
- `tools.registry.emit_tool_progress`

## 设计特点
### 1. 双 provider 冗余
这是该工具最核心的设计点：
- 单一 provider 失败时，另一个 provider 仍可能返回结果
- `all` 模式下有天然冗余

### 2. 结果统一为纯文本
虽然内部数据结构是 dict，但最终交给模型的是格式化文本，不是 JSON。

### 3. 偏向“给模型阅读”而非“给程序二次处理”
它的返回结果适合直接喂回模型，让模型继续总结，而不是给上层代码做强结构化处理。

## 如果以后要恢复
建议至少恢复以下能力：
1. `web_search` schema
2. `execute()` 主流程
3. 一个稳定 provider（优先 Ollama 或正式搜索 API）
4. provider 失败时的错误聚合
5. URL 去重逻辑

## 恢复时建议
如果重建，建议优先改造成：
- 统一抽象 provider 接口
- 返回结构化结果对象
- 最后再单独提供“转文本给模型”的格式化层

这样比旧版把 provider 调用、融合和文本格式化全部耦合在一起更容易维护。
