"""Public helper routes for WeChat QR login."""

from __future__ import annotations

import asyncio
import html
from urllib.parse import urlencode

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse

from services.wechat_runtime import get_wechat_runtime

router = APIRouter(tags=["wechat"])


def _require_runtime():
    runtime = get_wechat_runtime()
    if runtime is None:
        raise HTTPException(status_code=503, detail="WeChat runtime not running")
    return runtime


def _require_access(runtime, access: str) -> None:
    if not access or access != runtime.login_access_token:
        raise HTTPException(status_code=403, detail="Invalid WeChat login access token")


@router.get("/api/wechat/login")
async def wechat_login_status(access: str = Query(default="")):
    runtime = _require_runtime()
    _require_access(runtime, access)
    payload = runtime.get_login_snapshot()
    response = JSONResponse(payload)
    response.headers["Cache-Control"] = "no-store"
    return response


@router.post("/api/wechat/login/new")
async def wechat_login_new(access: str = Query(default="")):
    runtime = _require_runtime()
    _require_access(runtime, access)
    payload = await asyncio.to_thread(runtime.force_new_login_sync)
    response = JSONResponse(payload)
    response.headers["Cache-Control"] = "no-store"
    return response


@router.get("/wechat/login")
async def wechat_login_page(access: str = Query(default="")):
    runtime = _require_runtime()
    _require_access(runtime, access)
    payload = runtime.get_login_snapshot()
    image_url = payload.get("public_image_url") or ""
    refresh_url = "/api/wechat/login?" + urlencode({"access": access})
    force_url = "/api/wechat/login/new?" + urlencode({"access": access})
    safe_status = html.escape(str(payload.get("status") or "unknown"))
    safe_message = html.escape(str(payload.get("message") or ""))
    safe_user = html.escape(str(payload.get("user_id") or ""))
    safe_image_url = html.escape(str(image_url))
    safe_force_url = html.escape(force_url)
    safe_refresh_url = html.escape(refresh_url)

    body = f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>WeChat Login</title>
  <style>
    body {{
      margin: 0;
      min-height: 100vh;
      display: grid;
      place-items: center;
      background: #0f172a;
      color: #e5eefc;
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
    }}
    .card {{
      width: min(92vw, 520px);
      background: #111c32;
      border: 1px solid rgba(148, 163, 184, 0.28);
      border-radius: 18px;
      padding: 20px;
    }}
    h1 {{
      margin: 0 0 12px;
      font-size: 1.25rem;
    }}
    .meta {{
      color: #bfd0ea;
      line-height: 1.6;
      margin-bottom: 16px;
      word-break: break-word;
    }}
    .qr {{
      width: min(100%, 360px);
      aspect-ratio: 1 / 1;
      background: #fff;
      border-radius: 16px;
      overflow: hidden;
      display: grid;
      place-items: center;
      margin: 0 auto 16px;
    }}
    .qr img {{
      width: 100%;
      height: 100%;
      object-fit: contain;
      display: block;
    }}
    .actions {{
      display: flex;
      gap: 10px;
      flex-wrap: wrap;
    }}
    button, a {{
      border: 0;
      border-radius: 12px;
      padding: 10px 14px;
      text-decoration: none;
      background: #38bdf8;
      color: #082032;
      font-weight: 700;
      cursor: pointer;
    }}
    .muted {{
      background: #24324d;
      color: #dbe7f7;
    }}
  </style>
</head>
<body>
  <div class="card">
    <h1>WeChat 扫码登录</h1>
    <div class="meta">
      状态：{safe_status}<br />
      说明：{safe_message or "-"}<br />
      已登录用户：{safe_user or "-"}
    </div>
    <div class="qr">
      {f'<img src="{safe_image_url}" alt="WeChat QR" />' if safe_image_url else '<span style="color:#0f172a">当前没有可用二维码</span>'}
    </div>
    <div class="actions">
      <a href="{safe_image_url}" target="_blank" rel="noreferrer" class="muted">打开二维码图片</a>
      <button type="button" id="newLogin">切换新账号二维码</button>
      <button type="button" id="refreshBtn" class="muted">刷新状态</button>
    </div>
  </div>
  <script>
    const refreshUrl = {safe_refresh_url!r};
    const newUrl = {safe_force_url!r};
    document.getElementById("refreshBtn").addEventListener("click", async () => {{
      const res = await fetch(refreshUrl, {{ cache: "no-store" }});
      if (res.ok) location.reload();
    }});
    document.getElementById("newLogin").addEventListener("click", async () => {{
      const res = await fetch(newUrl, {{ method: "POST" }});
      if (res.ok) location.reload();
    }});
    setInterval(async () => {{
      try {{
        const res = await fetch(refreshUrl, {{ cache: "no-store" }});
        if (!res.ok) return;
        const data = await res.json();
        if (data.logged_in) {{
          location.reload();
          return;
        }}
        if (data.public_image_url && data.public_image_url !== {safe_image_url!r}) {{
          location.reload();
        }}
      }} catch (_err) {{}}
    }}, 5000);
  </script>
</body>
</html>"""
    response = HTMLResponse(body)
    response.headers["Cache-Control"] = "no-store"
    return response


@router.get("/wechat/login/qr")
async def wechat_login_qr(access: str = Query(default="")):
    runtime = _require_runtime()
    _require_access(runtime, access)
    payload = runtime.get_login_snapshot()
    qr_url = str(payload.get("qr_url") or "").strip()
    if not qr_url:
        raise HTTPException(status_code=404, detail="QR code not available")
    return RedirectResponse(qr_url, status_code=307)
