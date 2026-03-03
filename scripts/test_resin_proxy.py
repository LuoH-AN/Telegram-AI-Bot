#!/usr/bin/env python3
"""Quick Resin proxy diagnostics for forward/reverse/Playwright paths."""

from __future__ import annotations

import argparse
import base64
import os
import socket
import ssl
import sys
from dataclasses import dataclass
from typing import Optional
from urllib.parse import quote, urlparse, urlunparse

import requests


def _env(name: str) -> str:
    return (os.getenv(name) or "").strip()


def _first_env(*names: str) -> str:
    for name in names:
        value = _env(name)
        if value:
            return value
    return ""


@dataclass
class ProxyConfig:
    raw_url: str
    scheme: str
    host: str
    port: int
    username: str
    password: str

    @property
    def server(self) -> str:
        return f"{self.scheme}://{self.host}:{self.port}"

    @property
    def auth_enabled(self) -> bool:
        return bool(self.username)

    @property
    def requests_proxy_url(self) -> str:
        if not self.username:
            return self.server
        enc_user = quote(self.username, safe="")
        enc_pass = quote(self.password or "", safe="")
        return f"{self.scheme}://{enc_user}:{enc_pass}@{self.host}:{self.port}"


def _render_account(template: str, user_id: int) -> str:
    if not template:
        return ""
    return template.replace("{user_id}", str(user_id))


def build_proxy_config(user_id: int) -> ProxyConfig:
    raw_proxy_url = _first_env(
        "BROWSER_PROXY_URL",
        "BROWSER_PROXY_SERVER",
        "RESIN_PROXY_URL",
        "RESIN_PROXY_SERVER",
        "PROXY_URL",
    )
    if not raw_proxy_url:
        raise ValueError(
            "Missing proxy URL. Set RESIN_PROXY_URL or BROWSER_PROXY_URL."
        )

    proxy_url = raw_proxy_url if "://" in raw_proxy_url else f"http://{raw_proxy_url}"
    parsed = urlparse(proxy_url)
    scheme = (parsed.scheme or "http").lower()
    if scheme not in {"http", "https"}:
        raise ValueError(f"Unsupported proxy scheme: {scheme}")
    host = parsed.hostname or ""
    if not host:
        raise ValueError("Proxy host is empty")
    port = parsed.port or (443 if scheme == "https" else 80)

    token = _first_env("RESIN_PROXY_TOKEN", "PROXY_TOKEN")
    platform = _first_env("RESIN_PROXY_PLATFORM", "PROXY_PLATFORM")
    account_tpl = _first_env("RESIN_PROXY_ACCOUNT", "PROXY_ACCOUNT")
    account = _render_account(account_tpl, user_id)
    resin_username = f"{token}:{platform}:{account}" if (token or platform or account) else ""
    resin_password = _first_env("RESIN_PROXY_PASSWORD", "PROXY_PASSWORD")

    username = _first_env("BROWSER_PROXY_USERNAME") or resin_username or (parsed.username or "")
    password = _first_env("BROWSER_PROXY_PASSWORD")
    if not password:
        password = resin_password or (parsed.password or "")

    if username and not password and username == resin_username:
        # Resin forward proxy usually uses username only with empty password.
        password = ""

    return ProxyConfig(
        raw_url=raw_proxy_url,
        scheme=scheme,
        host=host,
        port=port,
        username=username,
        password=password,
    )


def _mask_username(username: str) -> str:
    if not username:
        return "(none)"
    if len(username) <= 6:
        return "***"
    return username[:3] + "***" + username[-3:]


def _target_host_port(target_url: str) -> tuple[str, int]:
    parsed = urlparse(target_url)
    if (parsed.scheme or "").lower() not in {"http", "https"}:
        raise ValueError(f"Unsupported target URL scheme: {parsed.scheme}")
    host = parsed.hostname or ""
    if not host:
        raise ValueError("Target URL host is empty")
    port = parsed.port or (443 if parsed.scheme.lower() == "https" else 80)
    return host, port


def _recv_headers(sock: socket.socket, timeout_seconds: float = 8.0) -> str:
    sock.settimeout(timeout_seconds)
    chunks: list[bytes] = []
    while True:
        data = sock.recv(4096)
        if not data:
            break
        chunks.append(data)
        blob = b"".join(chunks)
        if b"\r\n\r\n" in blob:
            break
        if len(blob) > 64 * 1024:
            break
    return b"".join(chunks).decode("utf-8", errors="replace")


def test_connect_tunnel(proxy: ProxyConfig, target_url: str, timeout: float) -> bool:
    host, port = _target_host_port(target_url)
    print("\n[1] CONNECT tunnel test")
    print(f"proxy={proxy.server} auth={proxy.auth_enabled} target={host}:{port}")

    try:
        sock: socket.socket = socket.create_connection((proxy.host, proxy.port), timeout=timeout)
        try:
            if proxy.scheme == "https":
                ctx = ssl.create_default_context()
                sock = ctx.wrap_socket(sock, server_hostname=proxy.host)

            headers = [
                f"CONNECT {host}:{port} HTTP/1.1",
                f"Host: {host}:{port}",
                "Connection: close",
            ]
            if proxy.auth_enabled:
                token = base64.b64encode(f"{proxy.username}:{proxy.password}".encode("utf-8")).decode("ascii")
                headers.append(f"Proxy-Authorization: Basic {token}")
            payload = ("\r\n".join(headers) + "\r\n\r\n").encode("utf-8")
            sock.sendall(payload)
            raw = _recv_headers(sock)
        finally:
            try:
                sock.close()
            except Exception:
                pass
    except Exception as e:
        print(f"error={type(e).__name__}: {e}")
        return False

    first = (raw.splitlines() or [""])[0]
    ok = " 200 " in f" {first} "
    print("response:", first or "(empty)")
    print("ok:", ok)
    return ok


def test_requests_forward(proxy: ProxyConfig, target_url: str, timeout: float) -> bool:
    print("\n[2] Forward proxy GET test (requests)")
    proxies = {"http": proxy.requests_proxy_url, "https": proxy.requests_proxy_url}
    print(f"requests_proxy={proxy.requests_proxy_url}")
    try:
        resp = requests.get(target_url, proxies=proxies, timeout=timeout)
        body = (resp.text or "").strip().replace("\n", " ")
        print(f"status={resp.status_code} body_preview={body[:200]}")
        return 200 <= resp.status_code < 400
    except Exception as e:
        print(f"error={type(e).__name__}: {e}")
        return False


def _build_reverse_proxy_url(proxy: ProxyConfig, target_url: str, user_id: int) -> Optional[str]:
    token = _first_env("RESIN_PROXY_TOKEN", "PROXY_TOKEN")
    platform = _first_env("RESIN_PROXY_PLATFORM", "PROXY_PLATFORM")
    account_tpl = _first_env("RESIN_PROXY_ACCOUNT", "PROXY_ACCOUNT")
    account = _render_account(account_tpl, user_id)
    if not token and not platform and not account:
        return None

    parsed_target = urlparse(target_url)
    target_scheme = (parsed_target.scheme or "").lower()
    target_host = parsed_target.netloc
    target_path = parsed_target.path or "/"
    if parsed_target.query:
        target_path = f"{target_path}?{parsed_target.query}"

    base = urlparse(proxy.raw_url if "://" in proxy.raw_url else f"http://{proxy.raw_url}")
    base_path = (base.path or "").rstrip("/")
    platform_account = f"{platform}:{account}"
    token_seg = f"/{token}" if token else ""
    new_path = f"{base_path}{token_seg}/{platform_account}/{target_scheme}/{target_host}{target_path}"
    return urlunparse((base.scheme, base.netloc, new_path, "", "", ""))


def test_reverse_proxy(proxy: ProxyConfig, target_url: str, timeout: float, user_id: int) -> bool:
    reverse_url = _build_reverse_proxy_url(proxy, target_url, user_id)
    if not reverse_url:
        print("\n[3] Reverse proxy GET test skipped (token/platform/account all empty)")
        return False

    print("\n[3] Reverse proxy GET test (Resin path mode)")
    print(f"url={reverse_url}")
    try:
        resp = requests.get(reverse_url, timeout=timeout)
        body = (resp.text or "").strip().replace("\n", " ")
        print(f"status={resp.status_code} body_preview={body[:200]}")
        return 200 <= resp.status_code < 400
    except Exception as e:
        print(f"error={type(e).__name__}: {e}")
        return False


def test_playwright(proxy: ProxyConfig, target_url: str, timeout: float) -> bool:
    print("\n[4] Playwright context proxy test")
    try:
        from playwright.sync_api import sync_playwright
    except Exception as e:
        print(f"skip: playwright unavailable ({e})")
        return False

    proxy_cfg = {"server": proxy.server}
    if proxy.auth_enabled:
        proxy_cfg["username"] = proxy.username
        proxy_cfg["password"] = proxy.password

    ms = int(timeout * 1000)
    try:
        with sync_playwright() as pw:
            browser = pw.chromium.launch(
                headless=True,
                args=["--no-sandbox", "--disable-dev-shm-usage"],
            )
            context = browser.new_context(proxy=proxy_cfg)
            page = context.new_page()
            page.goto(target_url, timeout=ms, wait_until="domcontentloaded")
            title = page.title()
            print(f"ok: page title='{title[:120]}'")
            context.close()
            browser.close()
            return True
    except Exception as e:
        print(f"error={type(e).__name__}: {e}")
        return False


def main() -> int:
    parser = argparse.ArgumentParser(description="Diagnose Resin proxy connectivity.")
    parser.add_argument("--user-id", type=int, default=6285496408, help="Used for {user_id} account template.")
    parser.add_argument("--target", default="https://api.ipify.org", help="Target URL for proxy tests.")
    parser.add_argument("--timeout", type=float, default=12.0, help="Timeout seconds for each test.")
    parser.add_argument(
        "--skip-playwright",
        action="store_true",
        help="Skip Playwright proxy test.",
    )
    args = parser.parse_args()

    try:
        proxy = build_proxy_config(args.user_id)
    except Exception as e:
        print(f"[config] invalid: {e}")
        return 2

    print("[config]")
    print(f"raw_url={proxy.raw_url}")
    print(f"server={proxy.server}")
    print(f"username={_mask_username(proxy.username)}")
    print(f"password={'(set)' if proxy.password != '' else '(empty)'}")
    print(f"user_id={args.user_id}")
    print(f"target={args.target}")

    ok_connect = test_connect_tunnel(proxy, args.target, args.timeout)
    ok_forward = test_requests_forward(proxy, args.target, args.timeout)
    ok_reverse = test_reverse_proxy(proxy, args.target, args.timeout, args.user_id)
    ok_pw = True
    if not args.skip_playwright:
        ok_pw = test_playwright(proxy, args.target, args.timeout)

    print("\n[summary]")
    print(f"connect_tunnel_ok={ok_connect}")
    print(f"forward_requests_ok={ok_forward}")
    print(f"reverse_proxy_ok={ok_reverse}")
    print(f"playwright_ok={ok_pw if not args.skip_playwright else 'skipped'}")

    if ok_reverse and not ok_connect:
        print(
            "\nHint: Reverse proxy works but CONNECT tunnel fails. "
            "This endpoint likely does not support forward-proxy CONNECT, "
            "so Playwright proxy mode cannot use it."
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
