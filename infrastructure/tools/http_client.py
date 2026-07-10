"""Bounded HTTP downloads with SSRF-safe URL and redirect validation."""

from __future__ import annotations

import ipaddress
import socket
import urllib.parse
import urllib.request
from dataclasses import dataclass
from email.message import Message

_ALLOWED_SCHEMES = {"http", "https"}
_BLOCKED_HOSTS = {"localhost", "metadata.google.internal", "metadata", "ip-ranges.amazonaws.com"}


@dataclass(frozen=True)
class FetchedResource:
    data: bytes
    final_url: str
    content_type: str
    headers: Message


def _is_private_ip(ip: str) -> bool:
    try:
        address = ipaddress.ip_address(ip.split("%")[0])
    except ValueError:
        return True
    return (
        address.is_private
        or address.is_loopback
        or address.is_link_local
        or address.is_reserved
        or address.is_multicast
        or address.is_unspecified
    )


def assert_safe_url(url: str) -> None:
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme.lower() not in _ALLOWED_SCHEMES:
        raise ValueError(f"unsupported scheme: {parsed.scheme!r}")
    if parsed.username or parsed.password:
        raise ValueError("credentials in URL are not allowed")
    host = (parsed.hostname or "").lower()
    if not host:
        raise ValueError("url has no host")
    if host in _BLOCKED_HOSTS or host.endswith(".internal") or host.endswith(".local"):
        raise ValueError(f"blocked host: {host}")
    try:
        addresses = socket.getaddrinfo(host, None)
    except socket.gaierror as exc:
        raise ValueError(f"cannot resolve host {host!r}: {exc}") from exc
    for address in addresses:
        if _is_private_ip(address[4][0]):
            raise ValueError(f"blocked private/internal address: {host}")


class SafeRedirectHandler(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        assert_safe_url(newurl)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def download_url(
    url: str,
    *,
    max_bytes: int,
    timeout: int,
    user_agent: str,
) -> FetchedResource:
    assert_safe_url(url)
    request = urllib.request.Request(url, headers={"User-Agent": user_agent})
    opener = urllib.request.build_opener(SafeRedirectHandler())
    with opener.open(request, timeout=timeout) as response:
        final_url = response.geturl()
        assert_safe_url(final_url)
        content_length = response.headers.get("Content-Length")
        if content_length:
            try:
                declared_size = int(content_length)
            except ValueError:
                declared_size = None
            if declared_size is not None and declared_size > max_bytes:
                raise ValueError(f"response too large: {content_length} bytes (limit {max_bytes})")
        data = response.read(max_bytes + 1)
        if len(data) > max_bytes:
            raise ValueError(f"response too large: > {max_bytes} bytes")
        content_type = response.headers.get("Content-Type", "")
        headers = response.headers
    return FetchedResource(data=data, final_url=final_url, content_type=content_type, headers=headers)
