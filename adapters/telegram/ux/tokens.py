"""Stable short identifiers for callback payloads."""

from hashlib import blake2s


def stable_token(value: str) -> str:
    return blake2s(value.encode("utf-8"), digest_size=16).hexdigest()
