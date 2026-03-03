# Resin 代理连通性排查记录（2026-03-03）

## 背景

浏览器工具 `browser_agent` 启动会话时报错：

```text
Page.goto: net::ERR_TUNNEL_CONNECTION_FAILED
```

对应调用：

```json
browser_start_session({"start_url": "https://duckduckgo.com"})
```

## 什么是反向代理（Reverse Proxy）

反向代理可以理解为“中间转发站”：

1. 客户端先请求代理服务器。
2. 代理服务器再去请求真正的目标网站。
3. 代理服务器把目标网站的响应转回给客户端。

链路示意：

```text
客户端 -> 反向代理 -> 目标网站 -> 反向代理 -> 客户端
```

在 Resin 的反向代理模式里，客户端通常通过一个特定路径来表达目标地址，例如：

```text
https://your-resin/{TOKEN}/{Platform:Account}/https/duckduckgo.com/
```

这表示“访问 Resin，再由 Resin 代你访问 `https://duckduckgo.com/`”。

---

与正向代理（Forward Proxy）的差异：

- 正向代理：客户端配置 `proxy`，并通过 `CONNECT` 建立隧道（浏览器自动化常用）。
- 反向代理：客户端不走 `CONNECT`，而是直接请求代理的路径入口，由服务端转发。

这也是本次报错的核心：浏览器工具需要正向代理 CONNECT，而当前入口只表现出反向代理可用。

## 使用的配置

```env
RESIN_PROXY_URL=https://luowuyin-qwen3-5-9b.hf.space
RESIN_PROXY_TOKEN=EnLtLH
RESIN_PROXY_PLATFORM=Default
RESIN_PROXY_ACCOUNT=EnLtLH
```

## 测试脚本

已新增脚本：`scripts/test_resin_proxy.py`  
用于同时测试：

1. Forward Proxy 的 `CONNECT` 隧道能力（浏览器工具依赖此能力）
2. `requests` 通过代理访问目标站
3. Resin Reverse Proxy（路径模式）可用性
4. （可选）Playwright 实测

## 复现命令

```bash
RESIN_PROXY_URL=https://luowuyin-qwen3-5-9b.hf.space \
RESIN_PROXY_TOKEN=EnLtLH \
RESIN_PROXY_PLATFORM=Default \
RESIN_PROXY_ACCOUNT=EnLtLH \
python scripts/test_resin_proxy.py --user-id 6285496408 --target https://duckduckgo.com --timeout 12 --skip-playwright
```

## 关键结果

### 场景 A：`https://luowuyin-qwen3-5-9b.hf.space`（443）

- CONNECT 隧道测试：`HTTP/1.1 400 Bad Request`
- Forward Proxy 请求：失败（`Tunnel connection failed: 400 Bad Request`）
- Reverse Proxy（路径模式）请求：`200`（成功）

结论：该入口在当前形态下**可反向代理**，但**不支持（或被拦截）正向代理 CONNECT**。

---

### 场景 B：`https://luowuyin-qwen3-5-9b.hf.space:2260`

- 连接代理端口：超时（Timeout）
- Forward / Reverse 请求均失败（连接超时）

结论：`:2260` 对当前运行环境不可达。

## 根因说明

`browser_agent` / `playwright` / `crawl4ai` 使用的是浏览器级 Forward Proxy（需要 `CONNECT target:443`）。  
当前 `hf.space` 地址只表现为 Reverse Proxy 可用，不满足浏览器工具的 Forward Proxy 需求，因此出现：

```text
ERR_TUNNEL_CONNECTION_FAILED
```

## 建议方案

1. 提供一个真正可 `CONNECT` 的正向代理入口（例如 Resin 文档中的 `http://host:2260`，且外网可达）。
2. 若只能使用当前 `hf.space` 域名入口，则不要给浏览器工具配置代理，仅在支持 Reverse Proxy 的请求链路使用该入口。

## 备注

- 本文档用于排查结论归档，便于后续对照配置与环境。
- 如需避免用户侧再次遇到同类报错，可在代码中增加“CONNECT 自检失败后自动禁用浏览器代理并返回友好提示”的保护逻辑。
