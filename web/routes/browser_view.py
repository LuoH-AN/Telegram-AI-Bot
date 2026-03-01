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
  <style>
    :root {{
      --bg-1: #07111f;
      --bg-2: #11233c;
      --card: rgba(11, 18, 34, 0.78);
      --line: rgba(255, 255, 255, 0.12);
      --text: #e9eef8;
      --muted: #9fb0ce;
      --accent: #4dd4ff;
      --ok: #63f2b5;
      --err: #ff8f8f;
      --radius: 16px;
    }}
    * {{ box-sizing: border-box; }}
    html, body {{ height: 100%; }}
    body {{
      margin: 0;
      font-family: "Segoe UI", "Noto Sans SC", "PingFang SC", "Microsoft YaHei", sans-serif;
      color: var(--text);
      background:
        radial-gradient(1200px 900px at 85% -10%, #1f3b67 0%, transparent 58%),
        radial-gradient(1200px 900px at -20% 115%, #17355d 0%, transparent 58%),
        linear-gradient(160deg, var(--bg-1), var(--bg-2));
      padding: clamp(10px, 2vw, 20px);
    }}
    .shell {{
      margin: 0 auto;
      max-width: 1400px;
      display: grid;
      gap: 12px;
    }}
    .panel {{
      background: var(--card);
      border: 1px solid var(--line);
      border-radius: var(--radius);
      backdrop-filter: blur(8px);
      box-shadow: 0 18px 46px rgba(0, 0, 0, 0.35);
    }}
    .head {{
      padding: 12px 14px;
      display: grid;
      gap: 8px;
    }}
    .title {{
      font-size: clamp(15px, 2vw, 19px);
      font-weight: 700;
      letter-spacing: 0.02em;
      white-space: nowrap;
      overflow: hidden;
      text-overflow: ellipsis;
    }}
    .meta {{
      display: grid;
      grid-template-columns: minmax(0, 1fr) auto auto;
      gap: 8px;
      align-items: center;
      font-size: 13px;
      color: var(--muted);
    }}
    .url {{
      white-space: nowrap;
      overflow: hidden;
      text-overflow: ellipsis;
    }}
    .chip {{
      border: 1px solid var(--line);
      border-radius: 999px;
      padding: 4px 9px;
      font-weight: 600;
    }}
    .chip.ok {{ color: var(--ok); border-color: rgba(99, 242, 181, 0.45); }}
    .chip.err {{ color: var(--err); border-color: rgba(255, 143, 143, 0.45); }}
    .viewer {{
      position: relative;
      overflow: hidden;
      border-radius: var(--radius);
      border: 1px solid var(--line);
      background: #060a14;
      min-height: min(68vh, 760px);
      display: flex;
      align-items: center;
      justify-content: center;
    }}
    .viewer.control-on {{
      border-color: rgba(77, 212, 255, 0.65);
      box-shadow: 0 0 0 2px rgba(77, 212, 255, 0.2) inset;
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
    .toolbar {{
      display: flex;
      gap: 8px;
      align-items: center;
      flex-wrap: wrap;
      padding: 10px 12px;
    }}
    .btn {{
      border: 1px solid var(--line);
      border-radius: 10px;
      padding: 7px 12px;
      background: rgba(255, 255, 255, 0.03);
      color: var(--text);
      cursor: pointer;
      font-size: 13px;
      font-weight: 600;
    }}
    .btn.on {{
      border-color: rgba(77, 212, 255, 0.65);
      background: rgba(77, 212, 255, 0.15);
      color: #dff6ff;
    }}
    .action {{
      color: var(--muted);
      font-size: 12px;
      min-height: 16px;
    }}
    .tap {{
      position: absolute;
      width: 16px;
      height: 16px;
      border: 2px solid #4dd4ff;
      border-radius: 50%;
      box-shadow: 0 0 0 3px rgba(77, 212, 255, 0.15);
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
      padding: 10px 12px 14px;
      color: var(--muted);
      font-size: 12px;
      line-height: 1.45;
    }}
    @media (max-width: 760px) {{
      .meta {{
        grid-template-columns: 1fr;
      }}
      .viewer {{
        min-height: 48vh;
      }}
      .toolbar {{
        align-items: stretch;
      }}
      .btn {{
        width: 100%;
      }}
    }}
  </style>
</head>
<body>
  <main class="shell">
    <section class="panel head">
      <div id="pageTitle" class="title">{title}</div>
      <div class="meta">
        <div id="pageUrl" class="url">{url}</div>
        <div id="statusChip" class="chip ok">LIVE</div>
        <div id="timeChip" class="chip">--:--:--</div>
      </div>
    </section>
    <section class="panel toolbar">
      <button id="controlToggle" class="btn" type="button">接管模式：关闭</button>
      <div id="actionText" class="action">默认只读。开启接管后，点击画面会把点击转发到远端浏览器。</div>
    </section>
    <section id="viewerBox" class="viewer">
      <img id="liveFrame" alt="Live browser frame" draggable="false" />
      <div id="tapMarker" class="tap" aria-hidden="true"></div>
    </section>
    <section class="hint panel">
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
