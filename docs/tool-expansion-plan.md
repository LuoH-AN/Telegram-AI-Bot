# Tool 扩展方案

> 基于现有 `BaseTool` + `ToolRegistry` 框架，提出可新增的 tool 候选列表。
> 所有候选 tool 均遵循现有模式：继承 `BaseTool`、实现 `definitions()` / `execute()` / `get_instruction()`，在 `tools/__init__.py` 中注册，无需改动 handler 层。

**现有 tools：** `MemoryTool`、`SearchTool`（DuckDuckGo）、`FetchTool`（URL抓取）、`WikipediaTool`

---

## 候选 Tool 列表

### 1. WeatherTool — 天气查询

| 项目 | 内容 |
|------|------|
| 函数名 | `get_weather` |
| 参数 | `location`（string，必填）、`units`（enum: `metric`/`imperial`，默认 `metric`） |
| API | [wttr.in](https://wttr.in) — 免费，无需 API key |
| 实现 | `urllib.request` 请求 `https://wttr.in/{location}?format=j1`，解析 JSON 返回当前温度、体感温度、天气状况、湿度、风速、未来3天预报 |
| 依赖 | 无新增（标准库 `urllib`） |
| 价值 | 天气是最高频的实用查询之一，几乎所有聊天机器人都支持 |

---

### 2. CalculatorTool — 数学计算

| 项目 | 内容 |
|------|------|
| 函数名 | `calculate` |
| 参数 | `expression`（string，必填）— 数学表达式 |
| 实现 | 用 Python `ast.parse` + 白名单节点遍历安全求值，支持四则运算、幂运算、常用数学函数（`sin`/`cos`/`sqrt`/`log` 等，通过 `math` 模块） |
| 依赖 | 无新增（标准库 `ast` + `math`） |
| 价值 | LLM 的数学计算经常出错，让 tool 来算能大幅提升准确率 |

**安全说明：** 不使用 `eval()`，通过 AST 白名单严格限制可执行节点，杜绝代码注入。

---

### 3. DateTimeTool — 日期时间与时区

| 项目 | 内容 |
|------|------|
| 函数名 | `get_datetime` |
| 参数 | `timezone`（string，可选，默认 `UTC`）— IANA 时区名（如 `Asia/Shanghai`、`America/New_York`） |
| 实现 | 使用 `datetime` + `zoneinfo`（Python 3.9+）获取指定时区的当前日期时间，返回格式化的日期、时间、星期、UTC偏移 |
| 依赖 | 无新增（标准库 `datetime` + `zoneinfo`） |
| 价值 | LLM 无法知道当前真实时间，这是一个基础但关键的能力补全 |

---

### 4. TranslateTool — 文本翻译

| 项目 | 内容 |
|------|------|
| 函数名 | `translate` |
| 参数 | `text`（string，必填）、`source`（string，可选，默认 `auto`）、`target`（string，必填，如 `en`/`zh`/`ja`/`ko`/`fr`/`de`） |
| API | [MyMemory API](https://mymemory.translated.net/doc/spec.php) — 免费，无需 API key，每天 5000 词 |
| 实现 | `urllib.request` 请求 `https://api.mymemory.translated.net/get?q={text}&langpair={source}|{target}` |
| 依赖 | 无新增（标准库 `urllib`） |
| 价值 | 用户群体中英文混合，专用翻译工具比 LLM 直接翻译更可靠（尤其对于专业术语） |

---

### 5. CurrencyTool — 汇率查询

| 项目 | 内容 |
|------|------|
| 函数名 | `convert_currency` |
| 参数 | `amount`（number，必填）、`from_currency`（string，必填，如 `USD`）、`to_currency`（string，必填，如 `CNY`） |
| API | [Frankfurter](https://www.frankfurter.app/) — 免费开源，无需 API key，数据来自欧洲央行 |
| 实现 | `urllib.request` 请求 `https://api.frankfurter.app/latest?amount={amount}&from={from}&to={to}` |
| 依赖 | 无新增（标准库 `urllib`） |
| 价值 | 汇率实时变动，LLM 训练数据中的汇率早已过时 |

---

### 6. DictionaryTool — 英语词典

| 项目 | 内容 |
|------|------|
| 函数名 | `define_word` |
| 参数 | `word`（string，必填）、`language`（enum: `en`/`zh`，默认 `en`） |
| API（英文） | [Free Dictionary API](https://dictionaryapi.dev/) — 免费，无需 API key |
| API（中文） | 汉典或其他中文词典 API（备选） |
| 实现 | 请求 `https://api.dictionaryapi.dev/api/v2/entries/{language}/{word}`，返回音标、词性、释义、例句 |
| 依赖 | 无新增（标准库 `urllib`） |
| 价值 | 提供权威词典释义，比 LLM 生成的定义更精确规范 |

---

### 7. CryptoTool — 加密货币价格

| 项目 | 内容 |
|------|------|
| 函数名 | `get_crypto_price` |
| 参数 | `coin`（string，必填，如 `bitcoin`/`ethereum`）、`currency`（string，可选，默认 `usd`） |
| API | [CoinGecko](https://www.coingecko.com/en/api) — 免费，无需 API key（限频 10-30次/分钟） |
| 实现 | `urllib.request` 请求 `https://api.coingecko.com/api/v3/simple/price?ids={coin}&vs_currencies={currency}&include_24hr_change=true`，返回当前价格和24h涨跌幅 |
| 依赖 | 无新增（标准库 `urllib`） |
| 价值 | 加密货币价格波动大，实时查询需求高 |

---

### 8. ImageGenTool — AI 图片生成

| 项目 | 内容 |
|------|------|
| 函数名 | `generate_image` |
| 参数 | `prompt`（string，必填）、`size`（enum: `1024x1024`/`1024x1792`/`1792x1024`，默认 `1024x1024`） |
| 实现 | 使用已有 `openai` SDK，调用用户配置的 API（兼容 DALL-E 等接口），生成图片后将 URL 返回给 AI，AI 在回复中发送给用户 |
| 依赖 | 无新增（已有 `openai` SDK） |
| 注意 | 需要用户的 API 支持图片生成端点；需考虑 token 消耗提示 |
| 价值 | 文生图是 AI 聊天的热门功能，用户无需切换应用 |

---

### 9. HackerNewsTool — Hacker News 热榜

| 项目 | 内容 |
|------|------|
| 函数名 | `get_hackernews` |
| 参数 | `category`（enum: `top`/`new`/`best`/`ask`/`show`，默认 `top`）、`limit`（integer，可选，默认 `5`，最大 `10`） |
| API | [HN Official API](https://github.com/HackerNews/API) — 免费，无需 API key |
| 实现 | 请求 `https://hacker-news.firebaseio.com/v0/{category}stories.json` 获取 ID 列表，再批量获取 story 详情，返回标题 + URL + 分数 + 评论数 |
| 依赖 | 无新增（标准库 `urllib`） |
| 价值 | 面向技术用户，快速获取科技圈动态 |

---

### 10. CodeRunnerTool — Python 代码执行

| 项目 | 内容 |
|------|------|
| 函数名 | `run_python` |
| 参数 | `code`（string，必填）— Python 代码片段 |
| 实现 | 使用 `subprocess` 在受限环境中执行 Python 代码，设置超时（5s）、限制内存、禁止网络和文件系统访问 |
| 依赖 | 无新增（标准库 `subprocess`） |
| 价值 | 让 AI 可以实际运行代码验证结果，对编程问答场景极有价值 |

**安全说明：** 这是最高风险的 tool，需要严格的沙箱隔离。建议使用 Docker 内的 `--network=none` + `--read-only` + `ulimit` 限制。如果部署环境不支持嵌套容器，可考虑使用 `RestrictedPython` 库或跳过此 tool。

---

## 优先级建议

### 第一梯队：立刻可做（零依赖，高价值）

| Tool | 理由 |
|------|------|
| **DateTimeTool** | 纯标准库，5分钟实现，填补 LLM 无法获取当前时间的根本缺陷 |
| **CalculatorTool** | 纯标准库，解决 LLM 数学不准的经典痛点 |
| **WeatherTool** | 免费 API，最高频的实用查询 |

### 第二梯队：实用增强（免费 API，无需 key）

| Tool | 理由 |
|------|------|
| **CurrencyTool** | 免费 API，汇率查询需求明确 |
| **TranslateTool** | 免费 API，中英文用户群刚需 |
| **DictionaryTool** | 免费 API，学习英语场景常用 |

### 第三梯队：特定场景（按需决定）

| Tool | 理由 |
|------|------|
| **CryptoTool** | 取决于用户群体是否关注加密货币 |
| **HackerNewsTool** | 取决于用户群体是否为技术人员 |
| **ImageGenTool** | 依赖用户 API 是否支持图片生成 |
| **CodeRunnerTool** | 安全风险最高，需要评估部署环境的沙箱能力 |

---

## 共性设计原则

1. **零新增依赖** — 除 ImageGenTool 复用已有 `openai` 外，全部使用标准库 `urllib.request`
2. **统一错误处理** — `try/except` + `logger.exception()` + 返回友好错误信息
3. **超时控制** — 所有外部 API 调用设置 `timeout=10`
4. **User-Agent** — 统一使用 `GemenBot/1.0` 标识
5. **结果截断** — 长文本截断到合理长度，避免 token 浪费

---

*最后更新：2025-02-08*
