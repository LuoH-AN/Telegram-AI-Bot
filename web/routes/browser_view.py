"""Public browser live-view routes (token-based view + click/input control)."""

import asyncio
import html
import json
import time

from fastapi import APIRouter, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse, JSONResponse

router = APIRouter(tags=["browser-view"])


def _clamp_int(value: int | str | None, low: int, high: int, default: int) -> int:
    try:
        parsed = int(value) if value is not None else default
    except (TypeError, ValueError):
        parsed = default
    return max(low, min(parsed, high))


def _pack_ws_state(
    state: dict,
    *,
    quality: int | None = None,
    target_fps: float | None = None,
    stream_mode: str = "ws",
) -> dict:
    payload = {
        "type": "state",
        "stream_mode": stream_mode,
        "url": state.get("url") or "about:blank",
        "title": state.get("title") or "(untitled)",
        "viewport": state.get("viewport") or {"width": 1366, "height": 768},
        "challenge_active": bool(state.get("challenge_active")),
        "captured_at": state.get("captured_at"),
        "refresh_ms": state.get("refresh_ms"),
    }
    if quality is not None:
        payload["quality"] = int(quality)
    if target_fps is not None:
        payload["target_fps"] = round(float(target_fps), 1)
    return payload


def _build_view_page_html(token: str, state: dict) -> str:
    token_js = json.dumps(token, ensure_ascii=False)
    title = html.escape(str(state.get("title") or "(untitled)"))
    url = html.escape(str(state.get("url") or "about:blank"))

    return f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover" />
  <title>Browser Live View</title>
  <link rel="stylesheet" href="/static/custom.css" />
  <style>
    :root {{
      --status-err: rgba(92, 28, 28, 0.84);
      --viewer-bg: linear-gradient(165deg, rgba(255, 255, 255, 0.68), rgba(255, 255, 255, 0.46));
      --viewer-bg-dark: linear-gradient(165deg, rgba(17, 26, 37, 0.82), rgba(12, 18, 28, 0.58));
      --tap-accent: #2563eb;
      --tap-glow: rgba(37, 99, 235, 0.24);
    }}
    html,
    body {{
      min-height: 100%;
    }}
    body {{
      margin: 0;
      min-height: 100dvh;
      padding: clamp(10px, 2vw, 20px);
      color: var(--text-1);
      background: var(--bg-0);
    }}
    .shell {{
      position: relative;
      z-index: 2;
      margin: 0 auto;
      max-width: 1320px;
      display: grid;
      gap: 12px;
    }}
    .panel {{
      border-radius: var(--radius-lg);
      border: 1px solid var(--line-soft);
      background: var(--panel-bg);
      backdrop-filter: blur(14px) saturate(130%);
      -webkit-backdrop-filter: blur(14px) saturate(130%);
    }}
    .head {{
      padding: 14px 16px;
      display: grid;
      gap: 10px;
    }}
    .eyebrow {{
      margin: 0;
      font-size: 0.72rem;
      text-transform: uppercase;
      letter-spacing: 0.12em;
      color: var(--text-3);
      font-weight: 600;
    }}
    .title {{
      margin: 0;
      font-size: clamp(1rem, 1.9vw, 1.22rem);
      font-weight: 700;
      letter-spacing: 0.01em;
      white-space: nowrap;
      overflow: hidden;
      text-overflow: ellipsis;
    }}
    .meta {{
      display: grid;
      grid-template-columns: minmax(0, 1fr) auto;
      gap: 10px;
      align-items: center;
    }}
    .meta-item {{
      min-width: 0;
      display: grid;
      gap: 4px;
    }}
    .meta-label {{
      font-size: 0.68rem;
      letter-spacing: 0.1em;
      text-transform: uppercase;
      color: var(--text-3);
      font-weight: 600;
    }}
    .meta-compact {{
      display: inline-flex;
      gap: 8px;
      align-items: center;
      flex-wrap: wrap;
    }}
    .url {{
      font-family: "IBM Plex Mono", monospace;
      font-size: 0.83rem;
      color: var(--text-2);
      white-space: nowrap;
      overflow: hidden;
      text-overflow: ellipsis;
    }}
    .chip {{
      border: 1px solid var(--line-soft);
      border-radius: 999px;
      padding: 4px 10px;
      background: var(--soft-fill);
      font-weight: 600;
      font-size: 0.72rem;
      letter-spacing: 0.08em;
      text-transform: uppercase;
      color: var(--text-2);
      font-family: "IBM Plex Mono", monospace;
    }}
    .chip.ok {{
      border-color: var(--pill-active-border);
      background: linear-gradient(140deg, var(--pill-active-start), var(--pill-active-end));
      color: var(--pill-active-text);
    }}
    .chip.err {{
      border-color: rgba(92, 28, 28, 0.44);
      background: var(--status-err);
      color: #ffffff;
    }}
    .toolbar {{
      display: flex;
      gap: 10px;
      align-items: center;
      flex-wrap: wrap;
      padding: 12px 14px;
      min-height: 52px;
    }}
    .toolbar-row {{
      width: 100%;
      display: flex;
      gap: 10px;
      align-items: center;
      flex-wrap: wrap;
    }}
    .toolbar-row.main {{
      min-height: 36px;
    }}
    .toolbar-row.input {{
      align-items: stretch;
    }}
    .btn {{
      border: 1px solid var(--line-soft);
      border-radius: var(--radius-sm);
      background: var(--soft-fill);
      color: var(--text-1);
      padding: 8px 13px;
      white-space: nowrap;
      font-size: 0.88rem;
      font-weight: 600;
      transition: background 0.18s ease, border-color 0.18s ease, color 0.18s ease;
      cursor: pointer;
    }}
    .btn:hover {{
      border-color: var(--line);
      background: var(--hover-fill);
    }}
    .btn:focus-visible {{
      outline: 2px solid var(--pill-focus);
      outline-offset: 2px;
    }}
    .btn.on {{
      border-color: var(--pill-active-border);
      background: linear-gradient(145deg, var(--pill-active-start), var(--pill-active-end));
      color: var(--pill-active-text);
    }}
    .action {{
      color: var(--text-2);
      font-size: 0.8rem;
      min-height: 16px;
      line-height: 1.42;
    }}
    .remote-input {{
      flex: 1;
      min-width: min(100%, 280px);
      border: 1px solid var(--line-soft);
      border-radius: var(--radius-sm);
      background: var(--soft-fill);
      color: var(--text-1);
      padding: 8px 10px;
      font-size: 0.88rem;
      font-family: "IBM Plex Sans", "Noto Sans SC", sans-serif;
    }}
    .remote-input:focus-visible {{
      outline: 2px solid var(--pill-focus);
      outline-offset: 1px;
      border-color: var(--line);
    }}
    .mini-note {{
      width: 100%;
      margin-top: -2px;
      color: var(--text-3);
      font-size: 0.73rem;
      line-height: 1.35;
    }}
    .viewer-panel {{
      padding: 8px;
    }}
    .viewer {{
      position: relative;
      overflow: hidden;
      border-radius: calc(var(--radius-lg) - 4px);
      border: 1px solid var(--line-soft);
      background: var(--viewer-bg);
      min-height: min(68vh, 760px);
      display: flex;
      align-items: center;
      justify-content: center;
    }}
    .viewer.control-on {{
      border-color: var(--pill-active-border);
      background: linear-gradient(
          165deg,
          rgba(255, 255, 255, 0.76),
          rgba(255, 255, 255, 0.52)
        );
    }}
    .viewer.control-on img {{
      cursor: crosshair;
    }}
    img {{
      max-width: 100%;
      max-height: min(68vh, 760px);
      width: auto;
      height: auto;
      display: block;
      object-fit: contain;
      user-select: none;
      -webkit-user-drag: none;
      touch-action: manipulation;
    }}
    .tap {{
      position: absolute;
      width: 18px;
      height: 18px;
      border: 2px solid var(--tap-accent);
      border-radius: 50%;
      box-shadow: 0 0 0 3px var(--tap-glow);
      pointer-events: none;
      transform: translate(-50%, -50%);
      opacity: 0;
    }}
    .tap.show {{
      animation: tapPulse 620ms ease-out;
    }}
    @keyframes tapPulse {{
      0% {{ opacity: 1; transform: translate(-50%, -50%) scale(0.66); }}
      100% {{ opacity: 0; transform: translate(-50%, -50%) scale(1.55); }}
    }}
    .hint {{
      padding: 11px 14px 14px;
      color: var(--text-2);
      font-size: 0.78rem;
      line-height: 1.5;
      border-style: dashed;
    }}
    @media (prefers-color-scheme: dark) {{
      :root {{
        --status-err: rgba(97, 35, 35, 0.92);
        --tap-accent: #8dbdff;
        --tap-glow: rgba(141, 189, 255, 0.28);
      }}
      .viewer {{
        background: var(--viewer-bg-dark);
      }}
      .viewer.control-on {{
        background: linear-gradient(
            165deg,
            rgba(25, 38, 55, 0.9),
            rgba(16, 24, 35, 0.72)
          );
      }}
      .chip.err {{
        border-color: rgba(255, 164, 164, 0.42);
      }}
    }}
    @media (max-width: 920px) {{
      .meta {{
        grid-template-columns: 1fr;
      }}
      .meta-compact {{
        justify-content: flex-start;
      }}
    }}
    @media (max-width: 760px) {{
      .viewer {{
        min-height: 48vh;
      }}
      .toolbar {{
        align-items: stretch;
        flex-direction: column;
      }}
      .toolbar-row {{
        align-items: stretch;
      }}
      .btn {{
        width: 100%;
      }}
      .action {{
        width: 100%;
      }}
      .remote-input {{
        width: 100%;
      }}
    }}
  </style>
</head>
<body>
  <div class="bg-layer" aria-hidden="true"></div>
  <main class="shell">
    <section class="panel glass head">
      <p class="eyebrow">Browser Live View</p>
      <div id="pageTitle" class="title">{title}</div>
      <div class="meta">
        <div class="meta-item">
          <span class="meta-label">Current URL</span>
          <div id="pageUrl" class="url">{url}</div>
        </div>
        <div class="meta-compact">
          <div id="statusChip" class="chip ok">LIVE</div>
          <div id="timeChip" class="chip">--:--:--</div>
        </div>
      </div>
    </section>
    <section class="panel glass toolbar">
      <div class="toolbar-row main">
        <button id="controlToggle" class="btn" type="button">接管模式：关闭</button>
        <div id="actionText" class="action">默认只读。开启接管后，点击画面会把点击转发到远端浏览器。</div>
      </div>
      <div class="toolbar-row input">
        <input id="remoteInput" class="remote-input" type="text" autocomplete="off" spellcheck="false" placeholder="发送文本到当前焦点输入框（先点击输入框再发送）" />
        <button id="sendInputBtn" class="btn" type="button">发送文本</button>
        <button id="sendEnterBtn" class="btn" type="button">回车</button>
        <button id="sendBackspaceBtn" class="btn" type="button">退格</button>
      </div>
      <div class="mini-note">接管模式支持左/中/右键点击。输入有两种方式：1) 点击画面后直接敲键盘（常用键） 2) 在上方输入框批量发送文本（适合中文输入法）。</div>
    </section>
    <section class="panel glass viewer-panel">
      <div id="viewerBox" class="viewer">
        <img id="liveFrame" alt="Live browser frame" draggable="false" />
        <div id="tapMarker" class="tap" aria-hidden="true"></div>
      </div>
    </section>
    <section class="hint panel glass">
      支持手机和桌面浏览器。开启“接管模式”可远程点击与输入；会话结束后链接会失效。
    </section>
  </main>
  <script>
    const token = {token_js};
    const viewerBox = document.getElementById("viewerBox");
    const frameImg = document.getElementById("liveFrame");
    const controlToggle = document.getElementById("controlToggle");
    const actionText = document.getElementById("actionText");
    const tapMarker = document.getElementById("tapMarker");
    const remoteInput = document.getElementById("remoteInput");
    const sendInputBtn = document.getElementById("sendInputBtn");
    const sendEnterBtn = document.getElementById("sendEnterBtn");
    const sendBackspaceBtn = document.getElementById("sendBackspaceBtn");
    const pageTitle = document.getElementById("pageTitle");
    const pageUrl = document.getElementById("pageUrl");
    const statusChip = document.getElementById("statusChip");
    const timeChip = document.getElementById("timeChip");
    let clickBusy = false;
    let inputBusy = false;
    const inputQueue = [];
    let controlEnabled = false;
    let streamSocket = null;
    let reconnectTimer = null;
    let activeObjectUrl = null;
    let viewport = {{ width: 1366, height: 768 }};

    function setStatus(ok, text) {{
      statusChip.className = ok ? "chip ok" : "chip err";
      statusChip.textContent = text;
    }}

    function setControl(on) {{
      controlEnabled = !!on;
      controlToggle.textContent = controlEnabled ? "接管模式：开启" : "接管模式：关闭";
      controlToggle.className = controlEnabled ? "btn on" : "btn";
      viewerBox.className = controlEnabled ? "viewer control-on" : "viewer";
      remoteInput.disabled = !controlEnabled;
      sendInputBtn.disabled = !controlEnabled;
      sendEnterBtn.disabled = !controlEnabled;
      sendBackspaceBtn.disabled = !controlEnabled;
    }}

    function stampNow() {{
      const now = new Date();
      timeChip.textContent = now.toLocaleTimeString();
    }}

    function markTap(clientX, clientY) {{
      const viewerRect = viewerBox.getBoundingClientRect();
      tapMarker.style.left = `${{Math.max(0, Math.min(clientX - viewerRect.left, viewerRect.width))}}px`;
      tapMarker.style.top = `${{Math.max(0, Math.min(clientY - viewerRect.top, viewerRect.height))}}px`;
      tapMarker.classList.remove("show");
      // Trigger animation restart.
      void tapMarker.offsetWidth;
      tapMarker.classList.add("show");
    }}

    function updateStateFromPayload(data, fromStream = false) {{
      pageTitle.textContent = data.title || "(untitled)";
      pageUrl.textContent = data.url || "about:blank";
      if (data.viewport && data.viewport.width && data.viewport.height) {{
        viewport = {{
          width: Number(data.viewport.width) || viewport.width,
          height: Number(data.viewport.height) || viewport.height,
        }};
      }}
      if (data.challenge_active) {{
        actionText.textContent = "检测到人机验证挑战，可开启接管并点击验证区域。";
      }} else if (fromStream && !clickBusy) {{
        const fps = Number(data.target_fps) || 0;
        const quality = Number(data.quality) || 0;
        if (fps > 0 && quality > 0) {{
          actionText.textContent = `实时流已连接（约 ${{fps.toFixed(1)}} FPS，质量 ${{Math.round(quality)}}）。`;
        }}
      }}
    }}

    function releaseFrameUrl() {{
      if (activeObjectUrl) {{
        URL.revokeObjectURL(activeObjectUrl);
        activeObjectUrl = null;
      }}
    }}

    function scheduleReconnect() {{
      if (reconnectTimer) return;
      reconnectTimer = window.setTimeout(() => {{
        reconnectTimer = null;
        connectStream();
      }}, 1200);
    }}

    function connectStream() {{
      if (!("WebSocket" in window)) {{
        setStatus(false, "UNSUPPORTED");
        actionText.textContent = "当前浏览器不支持 WebSocket，无法显示实时画面。";
        return;
      }}
      if (streamSocket && (streamSocket.readyState === WebSocket.OPEN || streamSocket.readyState === WebSocket.CONNECTING)) {{
        return;
      }}

      const proto = window.location.protocol === "https:" ? "wss" : "ws";
      const wsUrl = `${{proto}}://${{window.location.host}}/browser-view/${{encodeURIComponent(token)}}/ws`;
      streamSocket = new WebSocket(wsUrl);
      streamSocket.binaryType = "blob";

      streamSocket.onopen = () => {{
        setStatus(true, "LIVE");
      }};

      streamSocket.onmessage = async (event) => {{
        if (typeof event.data === "string") {{
          try {{
            const packet = JSON.parse(event.data);
            if (packet.type === "state") {{
              updateStateFromPayload(packet, true);
              setStatus(true, "LIVE");
              stampNow();
              return;
            }}
            if (packet.type === "expired") {{
              setStatus(false, "EXPIRED");
              actionText.textContent = "会话已过期，请重新发起 browser_start_session。";
              return;
            }}
            if (packet.type === "error") {{
              setStatus(false, "STREAM ERR");
              if (packet.message) {{
                actionText.textContent = `实时流异常：${{packet.message}}`;
              }}
            }}
          }} catch (_) {{
            // Ignore malformed text packets.
          }}
          return;
        }}

        const blob = event.data instanceof Blob ? event.data : new Blob([event.data], {{ type: "image/jpeg" }});
        if (!blob || blob.size < 1) return;
        const nextUrl = URL.createObjectURL(blob);
        const prevUrl = activeObjectUrl;
        activeObjectUrl = nextUrl;
        frameImg.src = nextUrl;
        if (prevUrl) {{
          window.setTimeout(() => URL.revokeObjectURL(prevUrl), 3000);
        }}
      }};

      streamSocket.onclose = () => {{
        setStatus(false, "RECONNECT");
        actionText.textContent = "实时流中断，正在重连。";
        scheduleReconnect();
      }};

      streamSocket.onerror = () => {{
        setStatus(false, "STREAM ERR");
      }};
    }}

    async function sendRemoteClick(x, y, button = "left") {{
      if (clickBusy) return;
      clickBusy = true;
      actionText.textContent = `正在发送${{button}}点击 (${{Math.round(x * 100)}}%, ${{Math.round(y * 100)}}%)...`;
      setStatus(true, "CLICKING");
      try {{
        const resp = await fetch(`/browser-view/${{encodeURIComponent(token)}}/control/click`, {{
          method: "POST",
          headers: {{
            "Content-Type": "application/json",
          }},
          body: JSON.stringify({{ rx: x, ry: y, button, click_count: 1, wait_ms: 1200 }}),
        }});
        if (!resp.ok) {{
          setStatus(false, "CLICK FAILED");
          actionText.textContent = "点击失败：会话可能已过期或目标不可点击。";
          return;
        }}
        const data = await resp.json();
        if (data.url) pageUrl.textContent = data.url;
        if (data.title) pageTitle.textContent = data.title;
        if (data.challenge_active) {{
          actionText.textContent = data.challenge_message || "挑战仍在进行中，可继续点击或等待。";
        }} else {{
          actionText.textContent = "点击已发送，页面状态已刷新。";
        }}
        setStatus(true, "LIVE");
        stampNow();
      }} catch (_) {{
        setStatus(false, "CLICK FAILED");
        actionText.textContent = "点击失败：网络异常。";
      }} finally {{
        clickBusy = false;
      }}
    }}

    function isEditableTarget(el) {{
      if (!el) return false;
      const tag = (el.tagName || "").toLowerCase();
      return el.isContentEditable || tag === "input" || tag === "textarea" || tag === "select";
    }}

    async function sendRemoteInput(payload, label = "输入") {{
      inputQueue.push({{ payload, label }});
      if (inputBusy) return;
      inputBusy = true;
      try {{
        while (inputQueue.length > 0) {{
          const next = inputQueue.shift() || {{}};
          const nextPayload = next.payload || {{}};
          const nextLabel = next.label || "输入";
          setStatus(true, "INPUT");
          actionText.textContent = `${{nextLabel}}已发送到远端浏览器...`;
          try {{
            const resp = await fetch(`/browser-view/${{encodeURIComponent(token)}}/control/input`, {{
              method: "POST",
              headers: {{
                "Content-Type": "application/json",
              }},
              body: JSON.stringify(nextPayload),
            }});
            if (!resp.ok) {{
              setStatus(false, "INPUT FAILED");
              actionText.textContent = "输入失败：会话可能已过期或页面暂不可输入。";
              continue;
            }}
            const data = await resp.json();
            if (data.url) pageUrl.textContent = data.url;
            if (data.title) pageTitle.textContent = data.title;
            if (data.challenge_active) {{
              actionText.textContent = data.challenge_message || "挑战仍在进行中，可继续点击或输入。";
            }} else {{
              actionText.textContent = `${{nextLabel}}已发送。`;
            }}
            setStatus(true, "LIVE");
            stampNow();
          }} catch (_) {{
            setStatus(false, "INPUT FAILED");
            actionText.textContent = "输入失败：网络异常。";
          }}
        }}
      }} finally {{
        inputBusy = false;
      }}
    }}

    frameImg.onerror = () => {{
      setStatus(false, "STREAM ERR");
    }};

    controlToggle.addEventListener("click", () => {{
      setControl(!controlEnabled);
    }});

    sendInputBtn.addEventListener("click", async () => {{
      if (!controlEnabled) return;
      const text = remoteInput.value || "";
      if (!text) {{
        actionText.textContent = "请输入要发送到远端输入框的文本。";
        return;
      }}
      await sendRemoteInput({{ text, delay_ms: 42 }}, "文本");
    }});

    sendEnterBtn.addEventListener("click", async () => {{
      if (!controlEnabled) return;
      await sendRemoteInput({{ key: "Enter" }}, "回车");
    }});

    sendBackspaceBtn.addEventListener("click", async () => {{
      if (!controlEnabled) return;
      await sendRemoteInput({{ key: "Backspace" }}, "退格");
    }});

    window.addEventListener("beforeunload", () => {{
      releaseFrameUrl();
      if (reconnectTimer) {{
        clearTimeout(reconnectTimer);
      }}
      if (streamSocket && streamSocket.readyState <= 1) {{
        streamSocket.close();
      }}
    }});

    viewerBox.addEventListener("pointerdown", (event) => {{
      if (!controlEnabled || clickBusy) return;
      const rect = frameImg.getBoundingClientRect();
      if (rect.width < 2 || rect.height < 2) return;

      const insideX = event.clientX >= rect.left && event.clientX <= rect.right;
      const insideY = event.clientY >= rect.top && event.clientY <= rect.bottom;
      if (!insideX || !insideY) {{
        actionText.textContent = "请点击网页画面区域（不要点黑边留白）。";
        return;
      }}

      const displayX = event.clientX - rect.left;
      const displayY = event.clientY - rect.top;
      const px = Math.max(0, Math.min(1, displayX / rect.width));
      const py = Math.max(0, Math.min(1, displayY / rect.height));
      let button = "left";
      if (event.pointerType === "mouse") {{
        if (event.button === 2) button = "right";
        else if (event.button === 1) button = "middle";
        else if (event.button !== 0) return;
      }}
      markTap(event.clientX, event.clientY);
      sendRemoteClick(px, py, button);
      event.preventDefault();
    }});

    viewerBox.addEventListener("contextmenu", (event) => {{
      if (!controlEnabled) return;
      event.preventDefault();
    }});

    window.addEventListener("keydown", (event) => {{
      if (!controlEnabled) return;
      const active = document.activeElement;
      if (isEditableTarget(active) && active !== remoteInput) {{
        return;
      }}
      if (active === remoteInput) {{
        return;
      }}
      if (event.ctrlKey || event.metaKey || event.altKey) {{
        return;
      }}

      const key = event.key || "";
      if (!key) return;

      const passKeys = new Set([
        "Enter", "Backspace", "Tab", "Escape", "Delete",
        "ArrowLeft", "ArrowRight", "ArrowUp", "ArrowDown",
        "Home", "End", "PageUp", "PageDown",
      ]);
      if (key.length === 1) {{
        sendRemoteInput({{ text: key }}, "按键");
        event.preventDefault();
        return;
      }}
      if (passKeys.has(key)) {{
        sendRemoteInput({{ key }}, `按键 ${{key}}`);
        event.preventDefault();
      }}
    }});

    setControl(false);
    connectStream();
  </script>
</body>
</html>
"""


@router.get("/browser-view/{token}", response_class=HTMLResponse)
async def browser_view_page(token: str):
    from tools.browser_agent import get_browser_view_state_by_token

    state = await asyncio.to_thread(get_browser_view_state_by_token, token)
    if not state:
        raise HTTPException(status_code=404, detail="Live view not found or expired")
    return HTMLResponse(
        content=_build_view_page_html(token, state),
        headers={"Cache-Control": "no-store"},
    )


@router.websocket("/browser-view/{token}/ws")
async def browser_view_stream(token: str, websocket: WebSocket):
    from tools.browser_agent import get_browser_view_frame_by_token, get_browser_view_state_by_token

    await websocket.accept()
    min_quality = 52
    max_quality = 82
    quality = _clamp_int(websocket.query_params.get("quality"), min_quality, max_quality, 72)
    min_fps = 4.0
    max_fps = 12.0
    target_fps = float(_clamp_int(websocket.query_params.get("fps"), int(min_fps), int(max_fps), 8))
    last_state_sent = 0.0

    async def _send_state(force: bool = False) -> bool:
        nonlocal last_state_sent, quality, target_fps
        now = time.monotonic()
        if not force and now - last_state_sent < 2.0:
            return True
        state = await asyncio.to_thread(get_browser_view_state_by_token, token)
        if not state:
            await websocket.send_text(
                json.dumps({"type": "expired", "message": "Live view not found or expired"}, ensure_ascii=False)
            )
            await websocket.close(code=4404)
            return False
        packet = _pack_ws_state(state, quality=quality, target_fps=target_fps, stream_mode="ws")
        await websocket.send_text(json.dumps(packet, ensure_ascii=False))
        last_state_sent = now
        return True

    try:
        if not await _send_state(force=True):
            return

        while True:
            tick = time.perf_counter()
            frame = await asyncio.to_thread(get_browser_view_frame_by_token, token, quality=quality)
            capture_ms = (time.perf_counter() - tick) * 1000.0
            if not frame or not frame.get("image"):
                await websocket.send_text(
                    json.dumps({"type": "expired", "message": "Live view not found or expired"}, ensure_ascii=False)
                )
                await websocket.close(code=4404)
                return

            send_start = time.perf_counter()
            await websocket.send_bytes(frame["image"])
            send_ms = (time.perf_counter() - send_start) * 1000.0

            if capture_ms > 190 or send_ms > 95:
                quality = max(min_quality, quality - 4)
                target_fps = max(min_fps, target_fps - 1.0)
            elif capture_ms > 135 or send_ms > 60:
                quality = max(min_quality, quality - 2)
                target_fps = max(min_fps, target_fps - 0.5)
            elif capture_ms < 78 and send_ms < 30:
                quality = min(max_quality, quality + 2)
                target_fps = min(max_fps, target_fps + 0.4)

            if not await _send_state():
                return

            frame_time = time.perf_counter() - tick
            sleep_for = max(0.0, (1.0 / max(target_fps, 1.0)) - frame_time)
            if sleep_for > 0:
                await asyncio.sleep(sleep_for)
    except WebSocketDisconnect:
        return
    except Exception as e:
        try:
            await websocket.send_text(json.dumps({"type": "error", "message": str(e)}, ensure_ascii=False))
        except Exception:
            pass
        try:
            await websocket.close(code=1011)
        except Exception:
            pass


@router.post("/browser-view/{token}/control/click")
async def browser_view_control_click(token: str, body: dict):
    from tools.browser_agent import click_browser_view_by_token

    raw_x = body.get("x")
    raw_y = body.get("y")
    raw_rx = body.get("rx")
    raw_ry = body.get("ry")
    if (raw_rx is None or raw_ry is None) and (raw_x is None or raw_y is None):
        raise HTTPException(status_code=400, detail="Provide rx/ry or x/y")

    x = None
    y = None
    rx = None
    ry = None

    if raw_rx is not None and raw_ry is not None:
        try:
            rx = float(raw_rx)
            ry = float(raw_ry)
        except (TypeError, ValueError):
            raise HTTPException(status_code=400, detail="rx and ry must be numbers")
    else:
        try:
            x = float(raw_x)
            y = float(raw_y)
        except (TypeError, ValueError):
            raise HTTPException(status_code=400, detail="x and y must be numbers")

    try:
        wait_ms = int(body.get("wait_ms", 1200))
    except (TypeError, ValueError):
        wait_ms = 1200
    button = str(body.get("button") or "left").strip().lower()
    if button not in {"left", "right", "middle"}:
        button = "left"
    try:
        click_count = int(body.get("click_count", 1))
    except (TypeError, ValueError):
        click_count = 1

    result = await asyncio.to_thread(
        click_browser_view_by_token,
        token,
        x=x,
        y=y,
        rx=rx,
        ry=ry,
        wait_ms=wait_ms,
        button=button,
        click_count=click_count,
    )
    if not result:
        raise HTTPException(status_code=404, detail="Live view not found or expired")
    return JSONResponse(result, headers={"Cache-Control": "no-store"})


@router.post("/browser-view/{token}/control/input")
async def browser_view_control_input(token: str, body: dict):
    from tools.browser_agent import input_browser_view_by_token

    text = str(body.get("text") or "")
    key = str(body.get("key") or "")
    clear = bool(body.get("clear", False))
    press_enter = bool(body.get("press_enter", False))

    if not text and not key and not clear and not press_enter:
        raise HTTPException(status_code=400, detail="Provide text, key, clear, or press_enter")

    try:
        wait_ms = int(body.get("wait_ms", 0))
    except (TypeError, ValueError):
        wait_ms = 0
    try:
        delay_ms = int(body.get("delay_ms", 0))
    except (TypeError, ValueError):
        delay_ms = 0

    result = await asyncio.to_thread(
        input_browser_view_by_token,
        token,
        text=text,
        key=key,
        clear=clear,
        press_enter=press_enter,
        wait_ms=wait_ms,
        delay_ms=delay_ms,
    )
    if not result:
        raise HTTPException(status_code=404, detail="Live view not found or expired")
    return JSONResponse(result, headers={"Cache-Control": "no-store"})
