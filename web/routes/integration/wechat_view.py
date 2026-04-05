"""HTML rendering helpers for WeChat login."""

import html
from urllib.parse import urlencode


def render_wechat_login_page(payload: dict, access: str) -> str:
    image_url = payload.get("public_image_url") or ""
    safe = {
        "status": html.escape(str(payload.get("status") or "unknown")),
        "message": html.escape(str(payload.get("message") or "")),
        "user": html.escape(str(payload.get("user_id") or "")),
        "image": html.escape(str(image_url)),
        "refresh": html.escape("/api/wechat/login?" + urlencode({"access": access})),
        "force": html.escape("/api/wechat/login/new?" + urlencode({"access": access})),
    }
    qr_html = (
        f'<img src="{safe["image"]}" alt="WeChat QR" />'
        if safe["image"]
        else '<span style="color:#0f172a">当前没有可用二维码</span>'
    )
    return f"""<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8"/><meta name="viewport" content="width=device-width, initial-scale=1"/>
<title>WeChat Login</title><style>
body{{margin:0;min-height:100vh;display:grid;place-items:center;background:#0f172a;color:#e5eefc;font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif}}
.card{{width:min(92vw,520px);background:#111c32;border:1px solid rgba(148,163,184,.28);border-radius:18px;padding:20px}}
h1{{margin:0 0 12px;font-size:1.25rem}}.meta{{color:#bfd0ea;line-height:1.6;margin-bottom:16px;word-break:break-word}}
.qr{{width:min(100%,360px);aspect-ratio:1/1;background:#fff;border-radius:16px;overflow:hidden;display:grid;place-items:center;margin:0 auto 16px}}
.qr img{{width:100%;height:100%;object-fit:contain;display:block}}.actions{{display:flex;gap:10px;flex-wrap:wrap}}
button,a{{border:0;border-radius:12px;padding:10px 14px;text-decoration:none;background:#38bdf8;color:#082032;font-weight:700;cursor:pointer}}
.muted{{background:#24324d;color:#dbe7f7}}
</style></head><body><div class="card"><h1>WeChat 扫码登录</h1>
<div class="meta">状态：{safe["status"]}<br/>说明：{safe["message"] or "-"}<br/>已登录用户：{safe["user"] or "-"}</div>
<div class="qr">{qr_html}</div><div class="actions">
<a href="{safe["image"]}" target="_blank" rel="noreferrer" class="muted">打开二维码图片</a>
<button type="button" id="newLogin">切换新账号二维码</button>
<button type="button" id="refreshBtn" class="muted">刷新状态</button></div></div>
<script>
const refreshUrl={safe["refresh"]!r},newUrl={safe["force"]!r},currentImage={safe["image"]!r};
document.getElementById("refreshBtn").onclick=async()=>{{if((await fetch(refreshUrl,{{cache:"no-store"}})).ok)location.reload();}};
document.getElementById("newLogin").onclick=async()=>{{if((await fetch(newUrl,{{method:"POST"}})).ok)location.reload();}};
setInterval(async()=>{{try{{const res=await fetch(refreshUrl,{{cache:"no-store"}});if(!res.ok)return;const d=await res.json();if(d.logged_in||(d.public_image_url&&d.public_image_url!==currentImage))location.reload();}}catch(_err){{}}}},5000);
</script></body></html>"""

