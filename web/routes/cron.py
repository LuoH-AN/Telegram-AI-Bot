"""Cron tasks API routes."""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from cache.manager import cache
from config import MAX_CRON_TASKS_PER_USER
from web.auth import get_current_user

router = APIRouter(prefix="/api/cron", tags=["cron"])


class CronTaskCreate(BaseModel):
    name: str
    cron_expression: str
    prompt: str


class CronTaskUpdate(BaseModel):
    cron_expression: str | None = None
    prompt: str | None = None
    enabled: bool | None = None


@router.get("")
async def list_cron_tasks(user_id: int = Depends(get_current_user)):
    """Return all cron tasks for the user."""
    tasks = cache.get_cron_tasks(user_id)
    return {
        "tasks": [
            {
                "name": t["name"],
                "cron_expression": t["cron_expression"],
                "prompt": t["prompt"],
                "enabled": t.get("enabled", True),
                "last_run_at": t["last_run_at"].isoformat() if t.get("last_run_at") and hasattr(t["last_run_at"], "isoformat") else t.get("last_run_at"),
            }
            for t in tasks
        ]
    }


@router.post("")
async def create_cron_task(
    body: CronTaskCreate,
    user_id: int = Depends(get_current_user),
):
    """Create a new cron task."""
    if not body.name.strip():
        raise HTTPException(status_code=400, detail="Task name is required")
    if not body.cron_expression.strip():
        raise HTTPException(status_code=400, detail="Cron expression is required")
    if not body.prompt.strip():
        raise HTTPException(status_code=400, detail="Prompt is required")

    task = cache.add_cron_task(user_id, body.name.strip(), body.cron_expression.strip(), body.prompt.strip())
    if task is None:
        raise HTTPException(status_code=409, detail=f"Task name already exists or limit ({MAX_CRON_TASKS_PER_USER}) reached")
    return {"ok": True}


@router.put("/{name}")
async def update_cron_task(
    name: str,
    body: CronTaskUpdate,
    user_id: int = Depends(get_current_user),
):
    """Update a cron task."""
    updates = body.model_dump(exclude_none=True)
    if not updates:
        return {"ok": True}
    ok = cache.update_cron_task(user_id, name, **updates)
    if not ok:
        raise HTTPException(status_code=404, detail="Task not found")
    return {"ok": True}


@router.delete("/{name}")
async def delete_cron_task(
    name: str,
    user_id: int = Depends(get_current_user),
):
    """Delete a cron task."""
    ok = cache.delete_cron_task(user_id, name)
    if not ok:
        raise HTTPException(status_code=404, detail="Task not found")
    return {"ok": True}


@router.post("/{name}/run")
async def run_cron_task(
    name: str,
    user_id: int = Depends(get_current_user),
):
    """Manually trigger a cron task."""
    from services.cron_service import run_cron_task as _run
    result = _run(user_id, name)
    if result.startswith("Error"):
        raise HTTPException(status_code=400, detail=result)
    return {"ok": True, "message": result}
