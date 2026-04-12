"""Internal helper routes for WeChat QR login."""

from __future__ import annotations

import asyncio

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import JSONResponse

from services.wechat.runtime import get_wechat_runtime

router = APIRouter(tags=["wechat"])


def _require_runtime():
    runtime = get_wechat_runtime()
    if runtime is None:
        raise HTTPException(status_code=503, detail="WeChat runtime not running")
    return runtime


def _require_access(runtime, access: str) -> None:
    if not access or access != runtime.login_access_token:
        raise HTTPException(status_code=403, detail="Invalid WeChat login access token")


@router.get("/api/wechat/login")
async def wechat_login_status(access: str = Query(default="")):
    runtime = _require_runtime()
    _require_access(runtime, access)
    payload = runtime.get_login_snapshot()
    response = JSONResponse(payload)
    response.headers["Cache-Control"] = "no-store"
    return response


@router.post("/api/wechat/login/new")
async def wechat_login_new(access: str = Query(default="")):
    runtime = _require_runtime()
    _require_access(runtime, access)
    payload = await asyncio.to_thread(runtime.force_new_login_sync)
    response = JSONResponse(payload)
    response.headers["Cache-Control"] = "no-store"
    return response
