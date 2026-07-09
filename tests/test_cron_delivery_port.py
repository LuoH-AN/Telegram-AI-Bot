"""Tests for the cron delivery port (A2: domain no longer imports adapters)."""

from __future__ import annotations

import importlib
import inspect

from domain.services.cron import delivery as delivery_mod
from domain.services.cron.state import set_delivery_port, set_bot_ref
from domain.services.cron.delivery import platform_label, _send_message


def test_domain_cron_does_not_import_adapters():
    """domain.services.cron must have no static import of adapters.* (cross-ring)."""
    src = inspect.getsource(delivery_mod)
    assert "adapters" not in src
    # also confirm the module object has no adapters sub-imports loaded for cron
    for name, mod in list(vars(importlib.import_module("domain.services.cron")).items()):
        if hasattr(mod, "__name__") and str(getattr(mod, "__name__", "")).startswith("adapters"):
            raise AssertionError(f"domain.services.cron leaks adapter module: {name}")


def test_delivery_via_registered_port():
    sent = []
    set_delivery_port(lambda chat_id, text: sent.append((chat_id, text)), "TestPlatform")
    _send_message(None, 5, "result")
    assert sent == [(5, "result")]


def test_platform_label_uses_port():
    set_delivery_port(lambda c, t: None, "TestPlatform")
    assert platform_label(None) == "TestPlatform"


def test_platform_label_falls_back_to_bot_capability():
    set_delivery_port(None, "")

    class _Bot:
        def send_message(self, *a, **k):
            pass

    set_bot_ref(_Bot())
    assert platform_label(_Bot()) == "Telegram"
