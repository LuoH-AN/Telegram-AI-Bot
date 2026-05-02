"""Stream update policy helpers."""

from config import (
    STREAM_CHARS_MODE_INTERVAL,
    STREAM_FORCE_UPDATE_INTERVAL,
    STREAM_MIN_UPDATE_CHARS,
    STREAM_TIME_MODE_INTERVAL,
    STREAM_UPDATE_INTERVAL,
)

STREAM_BOUNDARY_CHARS = set(" \n\t.,!?;:)]}，。！？；：）】」》")


def should_update_stream(mode: str, elapsed: float, new_chars: int, ends_with_boundary: bool) -> bool:
    if mode == "time":
        return elapsed >= STREAM_TIME_MODE_INTERVAL
    if mode == "chars":
        return new_chars >= STREAM_CHARS_MODE_INTERVAL
    return (
        (elapsed >= STREAM_UPDATE_INTERVAL and new_chars >= STREAM_MIN_UPDATE_CHARS)
        or (elapsed >= STREAM_UPDATE_INTERVAL and ends_with_boundary)
        or (elapsed >= STREAM_FORCE_UPDATE_INTERVAL)
    )
