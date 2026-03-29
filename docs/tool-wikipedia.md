# wikipedia 工具归档

## 工具定位
`wikipedia` 是旧工具系统里的“百科型知识补充工具”。和泛搜索工具不同，它只面向 Wikipedia / MediaWiki API，适合模型在需要相对稳定、百科式资料时调用。

对应实现：`tools/wikipedia.py`

## 对外暴露的函数
- 工具名：`wikipedia_search`
- 参数：
  - `query: string`
  - `language: string`，支持 `en` / `zh`，默认 `en`

## 执行流程
1. `WikipediaTool.execute()` 校验工具名
2. 取 `query`
3. 读取 `language`
4. 若语言不在 `en/zh` 中，则回退到 `en`
5. 调 `_search_and_summarize(query, language)`
6. 返回整理好的结果文本

## API 调用策略
### 第一步：搜索
通过 MediaWiki API 执行：
- `action=query`
- `list=search`
- `srsearch=query`
- `srlimit=3`

### 第二步：取摘要
拿到 pageid 后，再次请求：
- `action=query`
- `prop=extracts`
- `exintro=true`
- `explaintext=true`

### 第三步：格式化输出
每条结果包含：
- 序号
- 标题
- Wikipedia URL
- intro extract

## 输出特征
- 只取前 3 条
- 每条摘要最大 500 字符
- 超长时截断到单词边界并追加省略号

这让输出更适合直接作为模型上下文，而不是原始百科全文。

## 依赖关系
- `urllib.request`
- `urllib.parse`
- MediaWiki API

没有额外第三方依赖，也不依赖浏览器环境，属于很“轻”的网络工具。

## 设计特点
### 1. 双阶段 API
先 search，再 fetch extract，是一个典型的“搜索页 → 内容摘要”结构。

### 2. 明确限制语言范围
只支持 `en/zh`，体现出该项目主要面向中英双语使用场景。

### 3. 结果高度压缩
不追求全量文章，只给模型最小可用摘要。

## 如果以后要恢复
最小恢复所需：
1. 恢复 `wikipedia_search` schema
2. 恢复 `_api_get()`
3. 恢复 `_search_and_summarize()` 双阶段逻辑
4. 保留 3 条结果 + 摘要截断

## 恢复时建议
如果以后重建，可以把这个工具继续保留成“专用知识源工具”，不要和通用 `search` 混成一个大工具。因为它的优势就在于：
- 来源相对可信
- 结构稳定
- 对模型更友好
- 输出成本更低
