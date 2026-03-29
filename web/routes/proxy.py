"""Reverse proxy for internal services started via shell tool.

When AI starts a web service inside the container (e.g. Flask, Gradio,
Streamlit), it listens on 127.0.0.1:<port> which is unreachable from outside.
This route forwards ``/proxy/<port>/...`` to the internal service so users
can access it through the existing WEB_BASE_URL.
"""

import asyncio
import logging
import re
from urllib.parse import urlsplit

import requests as _requests
from fastapi import APIRouter, Request, Response, WebSocket, WebSocketDisconnect
from fastapi.responses import RedirectResponse

logger = logging.getLogger(__name__)

router = APIRouter(tags=["proxy"])

_TARGET_HOST = "127.0.0.1"
_MIN_PORT = 1024
_MAX_PORT = 65535
_PROXY_TIMEOUT = 60
_TEXT_CONTENT_TYPES = {
    "text/html",
    "application/xhtml+xml",
    "text/css",
    "application/javascript",
    "text/javascript",
    "application/x-javascript",
}
_HTML_ATTR_RE = re.compile(
    r'(?P<attr>src|href|action|poster)=(?P<quote>["\'])(?P<value>.*?)(?P=quote)',
    re.IGNORECASE,
)
_HTML_SRCSET_RE = re.compile(r'srcset=(?P<quote>["\'])(?P<value>.*?)(?P=quote)', re.IGNORECASE)
_HTML_META_REFRESH_RE = re.compile(
    r'(<meta[^>]+http-equiv=["\']refresh["\'][^>]+content=["\'][^"\']*?url=)([^"\'>]+)',
    re.IGNORECASE,
)
_CSS_URL_RE = re.compile(r'url\(\s*(?P<quote>["\']?)(?P<value>/[^)"\']*)(?P=quote)\s*\)', re.IGNORECASE)
_CSS_IMPORT_RE = re.compile(r'(@import\s+(?:url\()?["\'])(?P<value>/[^"\']*)(["\']\)?)', re.IGNORECASE)


def _self_port() -> int:
    from config.settings import HEALTH_CHECK_PORT
    return HEALTH_CHECK_PORT


def _proxy_prefix(port: int) -> str:
    return f"/proxy/{port}"


def _rewrite_url_value(value: str, port: int) -> str:
    raw = (value or "").strip()
    if not raw:
        return value

    prefix = _proxy_prefix(port)
    lower = raw.lower()
    if (
        raw.startswith(prefix)
        or raw.startswith("#")
        or raw.startswith("//")
        or lower.startswith(("data:", "blob:", "mailto:", "javascript:", "tel:"))
    ):
        return value

    if raw.startswith("/"):
        return f"{prefix}{raw}"

    parsed = urlsplit(raw)
    hostname = (parsed.hostname or "").lower()
    if parsed.scheme in {"http", "https", "ws", "wss"} and hostname in {"127.0.0.1", "localhost"}:
        if parsed.port == port:
            proxied_path = parsed.path if parsed.path.startswith("/") else f"/{parsed.path}"
            return f"{prefix}{proxied_path}{('?' + parsed.query) if parsed.query else ''}{('#' + parsed.fragment) if parsed.fragment else ''}"

    return value


def _rewrite_srcset_value(value: str, port: int) -> str:
    parts = []
    for item in value.split(","):
        candidate = item.strip()
        if not candidate:
            continue
        tokens = candidate.split()
        tokens[0] = _rewrite_url_value(tokens[0], port)
        parts.append(" ".join(tokens))
    return ", ".join(parts)


def _proxy_runtime_script(port: int) -> str:
    prefix = _proxy_prefix(port)
    return (
        "<script>"
        "(()=>{"
        f"const PREFIX={prefix!r};"
        "const ORIGIN=window.location.origin;"
        "const SAFE_PREFIXES=['data:','blob:','mailto:','javascript:','tel:','#'];"
        "function shouldSkip(v){const s=String(v||'');return !s||s.startsWith(PREFIX)||s.startsWith('//')||SAFE_PREFIXES.some(p=>s.startsWith(p));}"
        "function proxify(v){const s=String(v||'');if(shouldSkip(s))return s;"
        "if(s.startsWith('/'))return PREFIX+s;"
        "try{const u=new URL(s,window.location.href);if(u.origin===ORIGIN&&!u.pathname.startsWith(PREFIX+'/'))return PREFIX+u.pathname+u.search+u.hash;}catch(_e){}return s;}"
        "function proxifySrcset(v){return String(v||'').split(',').map(i=>{const t=i.trim();if(!t)return t;const p=t.split(/\\s+/);p[0]=proxify(p[0]);return p.join(' ');}).join(', ');}"
        "const origFetch=window.fetch; if(origFetch){window.fetch=function(input,init){if(typeof input==='string')return origFetch.call(this,proxify(input),init);if(input instanceof Request)return origFetch.call(this,new Request(proxify(input.url),input),init);return origFetch.call(this,input,init);};}"
        "const xhrOpen=XMLHttpRequest.prototype.open;XMLHttpRequest.prototype.open=function(method,url,...rest){return xhrOpen.call(this,method,proxify(url),...rest);};"
        "if(window.EventSource){const NativeES=window.EventSource;window.EventSource=function(url,config){return new NativeES(proxify(url),config);};window.EventSource.prototype=NativeES.prototype;}"
        "if(window.WebSocket){const NativeWS=window.WebSocket;window.WebSocket=function(url,protocols){let next=url;try{const s=String(url||'');if(s.startsWith('/')){const proto=window.location.protocol==='https:'?'wss://':'ws://';next=proto+window.location.host+PREFIX+s;}else if(/^wss?:\\/\\//i.test(s)){const u=new URL(s);if(u.origin.replace(/^http/,'ws')===window.location.origin.replace(/^http/,'ws')){const proto=u.protocol;next=proto+'//'+u.host+PREFIX+u.pathname+u.search+u.hash;}}}catch(_e){}return protocols===undefined?new NativeWS(next):new NativeWS(next,protocols);};window.WebSocket.prototype=NativeWS.prototype;}"
        "function patchProp(proto,prop,mapper){if(!proto)return;const d=Object.getOwnPropertyDescriptor(proto,prop);if(!d||!d.set||!d.get)return;Object.defineProperty(proto,prop,{configurable:true,enumerable:d.enumerable,get:d.get,set(v){return d.set.call(this,mapper(v));}});}"
        "patchProp(window.HTMLScriptElement&&HTMLScriptElement.prototype,'src',proxify);"
        "patchProp(window.HTMLLinkElement&&HTMLLinkElement.prototype,'href',proxify);"
        "patchProp(window.HTMLImageElement&&HTMLImageElement.prototype,'src',proxify);"
        "patchProp(window.HTMLIFrameElement&&HTMLIFrameElement.prototype,'src',proxify);"
        "patchProp(window.HTMLSourceElement&&HTMLSourceElement.prototype,'src',proxify);"
        "patchProp(window.HTMLAnchorElement&&HTMLAnchorElement.prototype,'href',proxify);"
        "patchProp(window.HTMLFormElement&&HTMLFormElement.prototype,'action',proxify);"
        "patchProp(window.HTMLScriptElement&&HTMLScriptElement.prototype,'srcset',proxifySrcset);"
        "const setAttr=Element.prototype.setAttribute;Element.prototype.setAttribute=function(name,value){const key=String(name||'').toLowerCase();let next=value;if(['src','href','action','poster'].includes(key))next=proxify(value);else if(key==='srcset')next=proxifySrcset(value);return setAttr.call(this,name,next);};"
        "})();"
        "</script>"
    )


def _rewrite_html_body(text: str, port: int) -> str:
    def _attr_repl(match: re.Match[str]) -> str:
        attr = match.group("attr")
        quote = match.group("quote")
        value = match.group("value")
        return f"{attr}={quote}{_rewrite_url_value(value, port)}{quote}"

    def _srcset_repl(match: re.Match[str]) -> str:
        quote = match.group("quote")
        value = match.group("value")
        return f"srcset={quote}{_rewrite_srcset_value(value, port)}{quote}"

    text = _HTML_ATTR_RE.sub(_attr_repl, text)
    text = _HTML_SRCSET_RE.sub(_srcset_repl, text)
    text = _HTML_META_REFRESH_RE.sub(lambda m: f"{m.group(1)}{_rewrite_url_value(m.group(2), port)}", text)

    injection = _proxy_runtime_script(port)
    if "<head" in text.lower():
        return re.sub(r"(<head[^>]*>)", lambda m: m.group(1) + injection, text, count=1, flags=re.IGNORECASE)
    return injection + text


def _rewrite_css_body(text: str, port: int) -> str:
    text = _CSS_URL_RE.sub(
        lambda m: f"url({m.group('quote')}{_rewrite_url_value(m.group('value'), port)}{m.group('quote')})",
        text,
    )
    return _CSS_IMPORT_RE.sub(lambda m: f"{m.group(1)}{_rewrite_url_value(m.group('value'), port)}{m.group(3)}", text)


def _rewrite_response_body(content: bytes, content_type: str, port: int) -> tuple[bytes, bool]:
    mime = (content_type or "").split(";", 1)[0].strip().lower()
    if mime not in _TEXT_CONTENT_TYPES:
        return content, False

    charset = "utf-8"
    match = re.search(r"charset=([^;]+)", content_type or "", flags=re.IGNORECASE)
    if match:
        charset = match.group(1).strip() or "utf-8"

    try:
        text = content.decode(charset, errors="replace")
    except Exception:
        text = content.decode("utf-8", errors="replace")
        charset = "utf-8"

    if mime in {"text/html", "application/xhtml+xml"}:
        rewritten = _rewrite_html_body(text, port)
    elif mime == "text/css":
        rewritten = _rewrite_css_body(text, port)
    else:
        rewritten = text

    if rewritten == text:
        return content, False
    return rewritten.encode(charset, errors="replace"), True


def _rewrite_location_header(value: str, port: int) -> str:
    return _rewrite_url_value(value, port)


# ── HTTP proxy ────────────────────────────────────────────────────

@router.api_route(
    "/proxy/{port}/{path:path}",
    methods=["GET", "POST", "PUT", "DELETE", "PATCH", "HEAD", "OPTIONS"],
)
async def proxy_http(port: int, path: str, request: Request):
    if port < _MIN_PORT or port > _MAX_PORT:
        return Response(
            content=f"Port must be {_MIN_PORT}-{_MAX_PORT}",
            status_code=400,
        )
    if port == _self_port():
        return Response(content="Cannot proxy to self", status_code=400)

    target = f"http://{_TARGET_HOST}:{port}/{path}"
    qs = str(request.query_params)
    if qs:
        target += f"?{qs}"

    # Forward headers, drop hop-by-hop
    fwd_headers: dict[str, str] = {}
    skip = {"host", "transfer-encoding", "connection", "keep-alive", "upgrade", "accept-encoding"}
    for k, v in request.headers.items():
        if k.lower() not in skip:
            fwd_headers[k] = v
    fwd_headers["X-Forwarded-Host"] = request.headers.get("host", "")
    fwd_headers["X-Forwarded-Proto"] = request.url.scheme
    fwd_headers["X-Forwarded-Prefix"] = _proxy_prefix(port)

    body = await request.body()

    def _do():
        return _requests.request(
            method=request.method,
            url=target,
            headers=fwd_headers,
            data=body or None,
            timeout=_PROXY_TIMEOUT,
            stream=True,
            allow_redirects=False,
        )

    try:
        resp = await asyncio.to_thread(_do)
    except _requests.ConnectionError:
        return Response(
            content="Cannot connect to internal service, please confirm service is running.",
            status_code=502,
        )
    except _requests.Timeout:
        return Response(content="Internal service response timeout.", status_code=504)
    except Exception as exc:
        logger.warning("proxy error port=%d path=%s: %s", port, path, exc)
        return Response(content="Proxy request failed.", status_code=502)

    # Build response, drop hop-by-hop headers
    drop = {"transfer-encoding", "connection", "keep-alive"}
    resp_headers: dict[str, str] = {}
    for k, v in resp.headers.items():
        if k.lower() not in drop:
            resp_headers[k] = v

    body = resp.content
    body, rewritten = _rewrite_response_body(body, resp.headers.get("content-type", ""), port)
    if rewritten:
        resp_headers.pop("content-length", None)
        resp_headers.pop("Content-Length", None)
        resp_headers.pop("content-encoding", None)
        resp_headers.pop("Content-Encoding", None)
        resp_headers.pop("content-security-policy", None)
        resp_headers.pop("Content-Security-Policy", None)
        resp_headers.pop("content-security-policy-report-only", None)
        resp_headers.pop("Content-Security-Policy-Report-Only", None)
    if "location" in {k.lower() for k in resp_headers}:
        for key in list(resp_headers):
            if key.lower() == "location":
                resp_headers[key] = _rewrite_location_header(resp_headers[key], port)

    return Response(
        content=body,
        status_code=resp.status_code,
        headers=resp_headers,
    )


# ── Convenience: /proxy/{port} without trailing slash ─────────────

@router.api_route(
    "/proxy/{port}",
    methods=["GET", "POST", "PUT", "DELETE", "PATCH", "HEAD", "OPTIONS"],
)
async def proxy_http_root(port: int, request: Request):
    if request.method in {"GET", "HEAD"}:
        location = f"{request.url.path}/"
        qs = str(request.query_params)
        if qs:
            location += f"?{qs}"
        return RedirectResponse(url=location, status_code=307)
    return await proxy_http(port, "", request)


# ── WebSocket proxy ──────────────────────────────────────────────

@router.websocket("/proxy/{port}/{path:path}")
@router.websocket("/proxy/{port}")
async def proxy_ws(port: int, websocket: WebSocket, path: str = ""):
    if port < _MIN_PORT or port > _MAX_PORT or port == _self_port():
        await websocket.close(code=4400)
        return

    import websockets  # type: ignore[import-untyped]

    target = f"ws://{_TARGET_HOST}:{port}/{path}"
    qs = str(websocket.query_params) if websocket.query_params else ""
    if qs:
        target += f"?{qs}"

    await websocket.accept()
    try:
        async with websockets.connect(target) as upstream:

            async def client_to_upstream():
                try:
                    while True:
                        data = await websocket.receive()
                        if "text" in data:
                            await upstream.send(data["text"])
                        elif "bytes" in data:
                            await upstream.send(data["bytes"])
                except WebSocketDisconnect:
                    pass

            async def upstream_to_client():
                try:
                    async for msg in upstream:
                        if isinstance(msg, str):
                            await websocket.send_text(msg)
                        else:
                            await websocket.send_bytes(msg)
                except Exception:
                    pass

            await asyncio.gather(client_to_upstream(), upstream_to_client())
    except ImportError:
        await websocket.send_text("WebSocket proxy requires 'websockets' package.")
        await websocket.close(code=4500)
    except Exception:
        try:
            await websocket.close(code=1011)
        except Exception:
            pass
