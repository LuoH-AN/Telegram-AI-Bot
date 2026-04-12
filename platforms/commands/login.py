"""Shared login command handlers."""

from __future__ import annotations

from services.wechat.remote_login import start_wechat_login


async def login_command(ctx, command_prefix: str, *, args: list[str]) -> None:
    target = str(args[0] if args else "").strip().lower()
    if target != "wechat":
        await ctx.reply_text(f"Usage: {command_prefix}login wechat")
        return
    force = any(str(arg).strip().lower() in {"new", "force", "reset", "switch"} for arg in args[1:])
    await ctx.reply_text("Preparing WeChat login QR...")
    try:
        snapshot = await start_wechat_login(force=force)
    except Exception as exc:
        await ctx.reply_text(f"Cannot start WeChat login: {exc}")
        return
    if snapshot.get("logged_in"):
        user_id = str(snapshot.get("user_id") or "").strip() or "(unknown)"
        await ctx.reply_text(f"WeChat is already logged in as {user_id}. Use {command_prefix}login wechat new to switch account.")
        return
    qr_url = str(snapshot.get("qr_url") or "").strip()
    if not qr_url:
        message = str(snapshot.get("message") or snapshot.get("status") or "QR code is not ready yet.").strip()
        await ctx.reply_text(f"WeChat login status: {message}")
        return
    caption = "Scan this WeChat QR code."
    if getattr(ctx, "is_group", False) and hasattr(ctx, "send_private_photo_url"):
        try:
            await ctx.send_private_photo_url(qr_url, caption=caption)
            await ctx.reply_text("WeChat QR code sent to your private chat.")
            return
        except Exception:
            pass
    if hasattr(ctx, "reply_photo_url"):
        try:
            await ctx.reply_photo_url(qr_url, caption=caption)
            return
        except Exception:
            pass
    await ctx.reply_text(f"{caption}\n{qr_url}")
