"""TTS service — synthesize speech via Microsoft endpoint."""

import base64
import hashlib
import hmac
import html
import json
import logging
import threading
import time
import uuid
from datetime import datetime, timezone
from urllib.parse import quote

import requests
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from config import DEFAULT_TTS_OUTPUT_FORMAT

logger = logging.getLogger(__name__)

# Endpoint constants
ENDPOINT_URL = "https://dev.microsofttranslator.com/apps/endpoint?api-version=1.0"
VOICES_LIST_URL = "https://eastus.api.speech.microsoft.com/cognitiveservices/voices/list"

# Client constants
USER_AGENT = "okhttp/4.5.0"
CLIENT_VERSION = "4.0.530a 5fe1dc6c"
USER_ID = "0f04d16a175c411e"
HOME_GEOGRAPHIC_REGION = "zh-Hans-CN"
CLIENT_TRACE_ID = "aab069b9-70a7-4844-a734-96cd78d94be9"
VOICE_DECODE_KEY = "oik6PdDdMnOXemTbwvMn9de/h9lFnfBaCWbGMMZqqoSaQaqUOqjVGm5NqsmjcBI1x+sS9ugjB55HEJWRiFXYFw=="

# Synthesis defaults
DEFAULT_VOICE_NAME = "zh-CN-XiaoxiaoMultilingualNeural"
DEFAULT_RATE = "0"
DEFAULT_PITCH = "0"
DEFAULT_OUTPUT_FORMAT = DEFAULT_TTS_OUTPUT_FORMAT
DEFAULT_STYLE = "general"

# Runtime behavior
REQUEST_TIMEOUT = (10, 45)
TOKEN_REFRESH_MARGIN = 60
VOICE_LIST_TTL = 60 * 60 * 6
DEFAULT_TTS_HOST_SUFFIX = ".tts.speech.microsoft.com"

_session = requests.Session()
_token_lock = threading.Lock()
_voice_list_lock = threading.Lock()

_endpoint_cache: dict | None = None
_endpoint_expired_at: int | None = None
_voice_list_cache: list[dict] | None = None
_voice_list_cache_expires_at = 0


def _add_base64_padding(raw: str) -> str:
    """Pad base64 string to valid length."""
    return raw + ("=" * (-len(raw) % 4))


def _normalize_percent_value(value: str | int | float | None, default: str) -> str:
    """Normalize prosody value to numeric string, without '%' suffix."""
    if value is None:
        return default

    text = str(value).strip()
    if not text:
        return default

    if text.endswith("%"):
        text = text[:-1].strip()

    try:
        number = float(text)
    except ValueError:
        return default

    if number.is_integer():
        return str(int(number))
    return f"{number:.2f}".rstrip("0").rstrip(".")


def _decode_jwt_expiration(jwt_token: str) -> int:
    """Decode expiration timestamp from JWT token."""
    payload = jwt_token.split(".")[1]
    payload_json = base64.urlsafe_b64decode(_add_base64_padding(payload)).decode("utf-8")
    decoded = json.loads(payload_json)
    return int(decoded["exp"])


def sign(url_str: str) -> str:
    """Generate endpoint signature required by Microsoft translator endpoint."""
    target = url_str.split("://", 1)[1]
    encoded_url = quote(target, safe="")
    request_id = uuid.uuid4().hex
    formatted_date = (
        datetime.now(timezone.utc).strftime("%a, %d %b %Y %H:%M:%S").lower() + "gmt"
    )

    payload = (
        f"MSTranslatorAndroidApp{encoded_url}{formatted_date}{request_id}".lower().encode("utf-8")
    )
    secret = base64.b64decode(VOICE_DECODE_KEY)
    signature = base64.b64encode(hmac.new(secret, payload, hashlib.sha256).digest()).decode("utf-8")
    return f"MSTranslatorAndroidApp::{signature}::{formatted_date}::{request_id}"


@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=1, max=5),
    retry=retry_if_exception_type(requests.RequestException),
    reraise=True,
)
def _fetch_endpoint(proxies: dict | None = None) -> dict:
    """Fetch endpoint/token payload from translator endpoint."""
    headers = {
        "Accept-Language": "zh-Hans",
        "X-ClientVersion": CLIENT_VERSION,
        "X-UserId": USER_ID,
        "X-HomeGeographicRegion": HOME_GEOGRAPHIC_REGION,
        "X-ClientTraceId": CLIENT_TRACE_ID,
        "X-MT-Signature": sign(ENDPOINT_URL),
        "User-Agent": USER_AGENT,
        "Content-Type": "application/json; charset=utf-8",
        "Content-Length": "0",
        "Accept-Encoding": "gzip",
    }
    response = _session.post(
        ENDPOINT_URL,
        headers=headers,
        proxies=proxies,
        timeout=REQUEST_TIMEOUT,
    )
    response.raise_for_status()
    return response.json()


def get_endpoint(proxies: dict | None = None, force_refresh: bool = False) -> dict:
    """Get a cached endpoint token, refresh if expired or near expiry."""
    global _endpoint_cache, _endpoint_expired_at

    now = int(time.time())
    with _token_lock:
        if (
            not force_refresh
            and _endpoint_cache
            and _endpoint_expired_at
            and now < _endpoint_expired_at - TOKEN_REFRESH_MARGIN
        ):
            return _endpoint_cache

    endpoint = _fetch_endpoint(proxies=proxies)
    expires_at = _decode_jwt_expiration(endpoint["t"])

    with _token_lock:
        _endpoint_cache = endpoint
        _endpoint_expired_at = expires_at

    return endpoint


def get_ssml(
    text: str,
    voice_name: str,
    rate: str,
    pitch: str,
    style: str,
) -> str:
    """Build SSML payload with safe-escaped text."""
    safe_text = html.escape(text.strip())
    return (
        '<speak xmlns="http://www.w3.org/2001/10/synthesis" '
        'xmlns:mstts="http://www.w3.org/2001/mstts" version="1.0" xml:lang="zh-CN">'
        f'<voice name="{voice_name}">'
        f'<mstts:express-as style="{style}" styledegree="1.0" role="default">'
        f'<prosody rate="{rate}%" pitch="{pitch}%">{safe_text}</prosody>'
        "</mstts:express-as></voice></speak>"
    )


def guess_audio_extension(output_format: str) -> str:
    """Guess file extension from output format."""
    target = (output_format or "").lower()
    if "opus" in target or "ogg" in target:
        return "ogg"
    if "wav" in target:
        return "wav"
    return "mp3"


def normalize_tts_endpoint(value: str | None) -> str:
    """Normalize endpoint input to a host: region or full host."""
    text = (value or "").strip().lower()
    if not text:
        return ""

    for prefix in ("https://", "http://"):
        if text.startswith(prefix):
            text = text[len(prefix):]

    text = text.strip("/ ")

    # region alias: "southeastasia" -> "southeastasia.tts.speech.microsoft.com"
    if "." not in text:
        return f"{text}{DEFAULT_TTS_HOST_SUFFIX}"

    return text


@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=1, max=5),
    retry=retry_if_exception_type((requests.RequestException, ValueError)),
    reraise=True,
)
def get_voice(
    text: str,
    voice_name: str = "",
    rate: str | int | float = "",
    pitch: str | int | float = "",
    output_format: str = "",
    style: str = "",
    endpoint_host: str = "",
    proxies: dict | None = None,
) -> bytes:
    """Synthesize TTS audio from text."""
    if not text or not text.strip():
        raise ValueError("Text is empty")

    voice_name = (voice_name or DEFAULT_VOICE_NAME).strip()
    rate = _normalize_percent_value(rate, DEFAULT_RATE)
    pitch = _normalize_percent_value(pitch, DEFAULT_PITCH)
    output_format = (output_format or DEFAULT_OUTPUT_FORMAT).strip()
    style = (style or DEFAULT_STYLE).strip()

    endpoint = get_endpoint(proxies=proxies)
    requested_host = normalize_tts_endpoint(endpoint_host)
    token_host = f"{endpoint['r']}{DEFAULT_TTS_HOST_SUFFIX}"
    host = requested_host or token_host
    url = f"https://{host}/cognitiveservices/v1"
    headers = {
        "Authorization": endpoint["t"],
        "Content-Type": "application/ssml+xml",
        "X-Microsoft-OutputFormat": output_format,
    }
    ssml = get_ssml(text, voice_name, rate, pitch, style)

    response = _session.post(
        url,
        headers=headers,
        data=ssml.encode("utf-8"),
        proxies=proxies,
        timeout=REQUEST_TIMEOUT,
    )

    if response.status_code == 401:
        endpoint = get_endpoint(proxies=proxies, force_refresh=True)
        token_host = f"{endpoint['r']}{DEFAULT_TTS_HOST_SUFFIX}"
        headers["Authorization"] = endpoint["t"]
        response = _session.post(
            url,
            headers=headers,
            data=ssml.encode("utf-8"),
            proxies=proxies,
            timeout=REQUEST_TIMEOUT,
        )

        # Custom host may reject translator token; fallback to token region host.
        if (
            response.status_code == 401
            and requested_host
            and requested_host != token_host
        ):
            fallback_url = f"https://{token_host}/cognitiveservices/v1"
            logger.warning(
                "Custom TTS endpoint unauthorized: %s; fallback to token host: %s",
                requested_host,
                token_host,
            )
            response = _session.post(
                fallback_url,
                headers=headers,
                data=ssml.encode("utf-8"),
                proxies=proxies,
                timeout=REQUEST_TIMEOUT,
            )

    response.raise_for_status()
    return response.content


def synthesize_voice(
    text: str,
    voice_name: str = "",
    style: str = "",
    rate: str | int | float = "",
    pitch: str | int | float = "",
    output_format: str = "",
    endpoint_host: str = "",
    proxies: dict | None = None,
) -> bytes:
    """Alias for get_voice() with friendlier argument order."""
    return get_voice(
        text=text,
        voice_name=voice_name,
        rate=rate,
        pitch=pitch,
        output_format=output_format,
        style=style,
        endpoint_host=endpoint_host,
        proxies=proxies,
    )


@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=1, max=5),
    retry=retry_if_exception_type(requests.RequestException),
    reraise=True,
)
def _fetch_voice_list(proxies: dict | None = None) -> list[dict]:
    """Fetch available voice list from Microsoft speech endpoint."""
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/107.0.0.0 Safari/537.36 Edg/107.0.1418.26"
        ),
        "X-Ms-Useragent": "SpeechStudio/2021.05.001",
        "Content-Type": "application/json",
        "Origin": "https://azure.microsoft.com",
        "Referer": "https://azure.microsoft.com",
    }
    response = _session.get(
        VOICES_LIST_URL,
        headers=headers,
        proxies=proxies,
        timeout=REQUEST_TIMEOUT,
    )
    response.raise_for_status()
    return response.json()


def get_voice_list(force_refresh: bool = False, proxies: dict | None = None) -> list[dict] | None:
    """Get available voice list with in-memory TTL cache."""
    global _voice_list_cache, _voice_list_cache_expires_at

    now = int(time.time())
    with _voice_list_lock:
        if (
            not force_refresh
            and _voice_list_cache is not None
            and now < _voice_list_cache_expires_at
        ):
            return _voice_list_cache

    try:
        voice_list = _fetch_voice_list(proxies=proxies)
    except requests.RequestException as e:
        logger.error("获取语音列表失败: %s", e)
        return None

    with _voice_list_lock:
        _voice_list_cache = voice_list
        _voice_list_cache_expires_at = now + VOICE_LIST_TTL

    return voice_list
