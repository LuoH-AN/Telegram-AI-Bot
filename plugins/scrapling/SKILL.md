---
name: scrapling
version: 1.0.0
description: Web scraping skill powered by scrapling. Supports URL fetch/extract, HTML parsing, and cookie vault management.
entry_point: plugins.scrapling.tool:ScraplingTool
capabilities: [status, install, fetch, parse_html, cookie_list, cookie_get, cookie_set, cookie_delete]
platforms: [telegram, wechat, onebot]
---
