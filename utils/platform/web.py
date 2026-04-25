"""Web/dashboard and generic action messages."""

from __future__ import annotations


def build_web_dashboard_message(url: str) -> str:
    return f"Open Gemen dashboard:\n{url}\n\nThis link expires in 10 minutes."


def build_web_dm_sent_message() -> str:
    return "Dashboard link sent to DM."


def build_web_dm_failed_message() -> str:
    return "Cannot send DM. Please enable DMs and try again."


def build_analyze_uploaded_files_message() -> str:
    return "Please analyze the uploaded files."
