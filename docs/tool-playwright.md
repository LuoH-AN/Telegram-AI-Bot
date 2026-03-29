# playwright 工具归档

## 工具定位
`playwright` 是旧工具系统里的浏览器渲染型抓取工具，提供两类能力：
- `page_screenshot`：截图
- `page_content`：读取 JS 渲染后的页面正文

对应实现：`tools/playwright.py`

## 关键设计
### 1. 独立 worker 线程
这是该工具最核心的实现点。

原因：Playwright sync API 依赖 greenlet，必须固定在线程里运行；如果每次 tool 调用都落在不同线程，会出现：
- `Cannot switch to a different thread`

解决方式：
- 建一个长期存活的 daemon worker
- worker 持有 browser 实例
- 外部调用通过 queue 提交任务

所以它不是“每次调用开浏览器”，而是“单线程持有浏览器 + 队列派发”。

### 2. 挂起截图队列
截图不会直接由工具发送，而是入队到：
- `_PENDING_SCREENSHOTS`

再由外层消息 handler 统一投递。

## 对外暴露的函数
- `page_screenshot`
- `page_content`

## `page_screenshot` 思路
大致流程：
1. 校验 URL 是否为公网 http(s)
2. 把任务提交给 Playwright worker
3. worker 内打开独立 context/page
4. 导航到目标页面
5. 使用更拟人的上下文设置与页面停留策略
6. 生成截图字节流
7. 把截图任务压入 pending queue
8. 返回文本确认

## `page_content` 思路
与截图共用浏览器 worker，但最终目标是：
- 获取渲染后的 HTML
- 转 Markdown / 纯文本
- 去 style 垃圾内容
- 截断到上限长度

适合处理：
- 需要 JS 才能渲染内容的页面
- 静态 fetch 难以提取的站点

## 反爬与真实浏览器策略
依赖 `utils.browser_realism`：
- 选取浏览器 profile
- 注入更真实的 context 参数
- 模拟更自然的页面存在感

并支持：
- headed/headless 自动判断
- DISPLAY 不可用时回退 headless
- Chromium 可执行路径探测
- `goto` 多 wait_until 重试
- Cloudflare challenge 检测与等待

## 安全边界
和 `fetch`/`crawl4ai` 一样，也会校验 URL：
- 拒绝 localhost
- 拒绝私网 IP
- 只允许公网 http(s)

## 如果以后要恢复
恢复重点不是 schema，而是这个顺序：
1. 先恢复 worker 线程模型
2. 再恢复 URL 安全校验
3. 再恢复 `page_content`
4. 最后再恢复 screenshot side-channel 投递

## 恢复时建议
如果未来只想保留一种浏览器型工具，`playwright` 与 `crawl4ai` 最好二选一做主实现，避免双实现长期重复维护。
