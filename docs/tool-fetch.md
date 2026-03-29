# fetch 工具归档

## 工具定位
`fetch` 是旧工具系统里的“单 URL 内容抓取器”，适合在模型已经拿到链接后进一步读取页面正文。和 `search` 不同，它不负责检索，只负责把一个 URL 的内容取回来并转换成更适合 LLM 消费的文本。

对应实现：`tools/fetch.py`

## 对外暴露的函数
- 工具名：`url_fetch`
- 参数：
  - `url: string`
  - `max_length: integer`，默认 10000

## 核心实现策略
它不是自己抓 HTML 再解析，而是复用了 Jina Reader：
- 基础地址：`https://r.jina.ai/`
- 最终请求形式：`https://r.jina.ai/<原始URL>`

也就是说，本工具本质上是一个 **Jina Reader 代理封装层**。

## 执行流程
1. `execute()` 校验工具名必须是 `url_fetch`
2. 提取并校验 `url`
3. 校验 `max_length`
4. 通过 `emit_tool_progress()` 上报“正在抓取 URL”
5. 调 `_fetch_via_jina(url)`
6. 若返回文本超长，则截断并追加 `...(truncated)`
7. 返回文本结果

## URL 安全校验
这是该工具的重要安全设计点。

### `_validate_external_url()` 做了什么
- 只允许 `http` / `https`
- 禁止空 host
- 禁止 `localhost`
- 禁止 `.local`
- 对 host 做 DNS 解析
- 将结果 IP 全部做 `ipaddress.ip_address()` 校验
- 如果任意解析结果不是 global IP，则拒绝

### 目的
防 SSRF。

它明确阻止模型通过工具访问：
- 内网
- 本机服务
- 私有地址
- 本地开发域名

这是旧工具系统里安全意识比较强的一块。

## Jina Reader 调用细节
`_fetch_via_jina()`：
- 支持可选 `JINA_API_KEY`
- 通过 `Authorization: Bearer <key>` 传递
- `timeout=30s`
- 只要 HTTP 状态码 >= 400 就报错
- 空响应也报错

## 错误处理策略
对用户/模型侧返回的信息非常克制：
- URL 不合法 → `Error. Please retry with a valid public http(s) URL.`
- 抓取失败 → `Error. Please retry.`

也就是内部日志详细、外部提示模糊，避免暴露过多底层失败细节。

## 依赖关系
- `requests`
- `JINA_API_KEY`（可选）
- DNS 解析 / IP 校验
- `emit_tool_progress`

## 设计特点
### 1. 极简职责边界
只做“给定 URL → 返回正文文本”。

### 2. 把内容提纯责任外包给 Jina
自己不做 HTML 清洗，这降低了代码复杂度，但也让质量依赖第三方输出。

### 3. 安全边界明确
URL 校验是该工具最值得保留的部分。

## 如果以后要恢复
建议恢复时保留以下结构：
1. 先做严格 public URL 校验
2. 抓取层与清洗层解耦
3. 保留长度限制和超长截断
4. 工具层仍只返回适合模型消费的文本

## 恢复时建议
如果未来替换 Jina Reader，可以把抓取抽象成：
- `fetch_provider.fetch(url) -> text`

这样就能在：
- Jina Reader
- 自建 readability 服务
- 浏览器渲染抓取
之间自由切换。
