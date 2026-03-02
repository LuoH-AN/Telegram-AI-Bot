"""Public browser live-view routes (token-based view + click control)."""

import html
import json

from fastapi import APIRouter, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse, Response

router = APIRouter(tags=["browser-view"])


def _build_view_page_html(token: str, state: dict) -> str:
    token_js = json.dumps(token, ensure_ascii=False)
    title = html.escape(str(state.get("title") or "(untitled)"))
    url = html.escape(str(state.get("url") or "about:blank"))
    refresh_ms = int(state.get("refresh_ms") or 1200)

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
      .btn {{
        width: 100%;
      }}
      .action {{
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
      <button id="controlToggle" class="btn" type="button">接管模式：关闭</button>
      <div id="actionText" class="action">默认只读。开启接管后，点击画面会把点击转发到远端浏览器。</div>
    </section>
    <section class="panel glass viewer-panel">
      <div id="viewerBox" class="viewer">
        <img id="liveFrame" alt="Live browser frame" draggable="false" />
        <div id="tapMarker" class="tap" aria-hidden="true"></div>
      </div>
    </section>
    <section class="hint panel glass">
      支持手机和桌面浏览器。开启“接管模式”可远程点击（仅左键单击）；会话结束后链接会失效。
    </section>
  </main>
  <script>
    const token = {token_js};
    const viewerBox = document.getElementById("viewerBox");
    const frameImg = document.getElementById("liveFrame");
    const controlToggle = document.getElementById("controlToggle");
    const actionText = document.getElementById("actionText");
    const tapMarker = document.getElementById("tapMarker");
    const pageTitle = document.getElementById("pageTitle");
    const pageUrl = document.getElementById("pageUrl");
    const statusChip = document.getElementById("statusChip");
    const timeChip = document.getElementById("timeChip");
    let frameBusy = false;
    let clickBusy = false;
    let controlEnabled = false;
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

    async function sendRemoteClick(x, y) {{
      if (clickBusy) return;
      clickBusy = true;
      actionText.textContent = `正在点击远端位置 (${{Math.round(x * 100)}}%, ${{Math.round(y * 100)}}%)...`;
      setStatus(true, "CLICKING");
      try {{
        const resp = await fetch(`/browser-view/${{encodeURIComponent(token)}}/control/click`, {{
          method: "POST",
          headers: {{
            "Content-Type": "application/json",
          }},
          body: JSON.stringify({{ rx: x, ry: y, wait_ms: 1200 }}),
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
        refreshState();
        refreshFrame();
      }}
    }}

    async function refreshState() {{
      try {{
        const resp = await fetch(`/browser-view/${{encodeURIComponent(token)}}/state?ts=${{Date.now()}}`, {{
          cache: "no-store",
        }});
        if (!resp.ok) {{
          setStatus(false, "OFFLINE");
          return;
        }}
        const data = await resp.json();
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
        }}
        setStatus(true, "LIVE");
        stampNow();
      }} catch (_) {{
        setStatus(false, "OFFLINE");
      }}
    }}

    function refreshFrame() {{
      if (frameBusy) return;
      frameBusy = true;
      frameImg.src = `/browser-view/${{encodeURIComponent(token)}}/frame?ts=${{Date.now()}}`;
    }}

    frameImg.onload = () => {{
      frameBusy = false;
      setStatus(true, "LIVE");
      stampNow();
    }};
    frameImg.onerror = () => {{
      frameBusy = false;
      setStatus(false, "OFFLINE");
    }};

    controlToggle.addEventListener("click", () => {{
      setControl(!controlEnabled);
    }});

    viewerBox.addEventListener("pointerdown", (event) => {{
      if (!controlEnabled || clickBusy) return;
      if (event.pointerType === "mouse" && event.button !== 0) return;
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
      markTap(event.clientX, event.clientY);
      sendRemoteClick(px, py);
      event.preventDefault();
    }});

    setControl(false);
    refreshState();
    refreshFrame();
    setInterval(refreshState, Math.max({refresh_ms}, 1200) * 2);
    setInterval(refreshFrame, Math.max({refresh_ms}, 1200));
  </script>
</body>
</html>
"""


@router.get("/browser-view/{token}", response_class=HTMLResponse)
async def browser_view_page(token: str):
    from tools.browser_agent import get_browser_view_state_by_token

    state = get_browser_view_state_by_token(token)
    if not state:
        raise HTTPException(status_code=404, detail="Live view not found or expired")
    return HTMLResponse(
        content=_build_view_page_html(token, state),
        headers={"Cache-Control": "no-store"},
    )


@router.get("/browser-view/{token}/state")
async def browser_view_state(token: str):
    from tools.browser_agent import get_browser_view_state_by_token

    state = get_browser_view_state_by_token(token)
    if not state:
        raise HTTPException(status_code=404, detail="Live view not found or expired")
    return JSONResponse(
        state,
        headers={"Cache-Control": "no-store"},
    )


@router.get("/browser-view/{token}/frame")
async def browser_view_frame(token: str):
    from tools.browser_agent import get_browser_view_frame_by_token

    frame = get_browser_view_frame_by_token(token)
    if not frame:
        raise HTTPException(status_code=404, detail="Live view not found or expired")
    image = frame.get("image")
    if not image:
        raise HTTPException(status_code=500, detail="No frame available")

    headers = {
        "Cache-Control": "no-store, no-cache, must-revalidate, max-age=0",
        "Pragma": "no-cache",
    }
    return Response(content=image, media_type="image/jpeg", headers=headers)


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

    result = click_browser_view_by_token(token, x=x, y=y, rx=rx, ry=ry, wait_ms=wait_ms)
    if not result:
        raise HTTPException(status_code=404, detail="Live view not found or expired")
    return JSONResponse(result, headers={"Cache-Control": "no-store"})
