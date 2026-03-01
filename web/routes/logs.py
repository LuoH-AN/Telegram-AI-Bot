"""Logs API routes."""

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from services.log_service import (
    get_user_logs,
    delete_log_by_id,
    delete_logs_filtered,
    keep_latest_logs,
)
from web.auth import get_current_user

router = APIRouter(prefix="/api/logs", tags=["logs"])


class LogsDeleteRequest(BaseModel):
    type: str | None = None
    before: datetime | None = None
    after: datetime | None = None
    keep_latest: int | None = Field(default=None, ge=0)
    clear_all: bool = False


@router.get("")
async def list_logs(
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=200),
    type: str | None = Query(None),
    user_id: int = Depends(get_current_user),
):
    """Return paginated user logs."""
    rows, total = get_user_logs(user_id, log_type=type, page=page, limit=limit)
    for row in rows:
        if row.get("created_at"):
            row["created_at"] = row["created_at"].isoformat()
    return {
        "logs": rows,
        "total": total,
        "page": page,
        "limit": limit,
        "pages": max(1, -(-total // limit)),
    }


@router.delete("/{log_id}")
async def delete_log_route(
    log_id: int,
    user_id: int = Depends(get_current_user),
):
    """Delete one log entry by id."""
    deleted = delete_log_by_id(user_id, log_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Log not found")
    return {"ok": True}


@router.post("/delete")
async def delete_logs_route(
    body: LogsDeleteRequest,
    user_id: int = Depends(get_current_user),
):
    """Delete logs by filters, or keep latest N."""
    if body.keep_latest is not None:
        deleted = keep_latest_logs(user_id, body.keep_latest, log_type=body.type)
        return {"ok": True, "deleted": deleted}

    if body.clear_all:
        deleted = delete_logs_filtered(user_id, log_type=body.type)
        return {"ok": True, "deleted": deleted}

    if body.before is None and body.after is None:
        raise HTTPException(
            status_code=400,
            detail="Provide keep_latest, clear_all, or at least one of before/after",
        )

    deleted = delete_logs_filtered(
        user_id,
        log_type=body.type,
        before=body.before,
        after=body.after,
    )
    return {"ok": True, "deleted": deleted}
