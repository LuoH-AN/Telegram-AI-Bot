"""Logs API routes."""

from fastapi import APIRouter, Depends, Query

from services.log_service import get_user_logs
from web.auth import get_current_user

router = APIRouter(prefix="/api/logs", tags=["logs"])


@router.get("")
async def list_logs(
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=200),
    type: str | None = Query(None),
    user_id: int = Depends(get_current_user),
):
    """Return paginated user logs."""
    rows, total = get_user_logs(user_id, log_type=type, page=page, limit=limit)
    # Serialise datetime objects
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
