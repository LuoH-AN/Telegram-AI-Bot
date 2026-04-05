"""Memories API routes."""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from services import (
    get_memories,
    add_memory,
    update_memory,
    delete_memory,
    clear_memories,
)
from web.auth import get_current_user

router = APIRouter(prefix="/api/memories", tags=["memories"])


class MemoryCreate(BaseModel):
    content: str


class MemoryUpdate(BaseModel):
    content: str


@router.get("")
async def list_memories(user_id: int = Depends(get_current_user)):
    """Return all memories for current user."""
    memories = get_memories(user_id)
    return {
        "count": len(memories),
        "memories": [
            {
                "index": i + 1,
                "id": mem.get("id"),
                "content": mem.get("content", ""),
                "source": mem.get("source", "user"),
            }
            for i, mem in enumerate(memories)
        ],
    }


@router.post("")
async def create_memory(body: MemoryCreate, user_id: int = Depends(get_current_user)):
    """Create a memory."""
    content = (body.content or "").strip()
    if not content:
        raise HTTPException(status_code=400, detail="Memory content cannot be empty")
    memory = add_memory(user_id, content, source="user")
    return {
        "ok": True,
        "memory": {
            "id": memory.get("id"),
            "content": memory.get("content", ""),
            "source": memory.get("source", "user"),
        },
    }


@router.put("/{index}")
async def edit_memory(
    index: int,
    body: MemoryUpdate,
    user_id: int = Depends(get_current_user),
):
    """Update one memory by 1-based index."""
    if index < 1:
        raise HTTPException(status_code=400, detail="Index must be >= 1")
    content = (body.content or "").strip()
    if not content:
        raise HTTPException(status_code=400, detail="Memory content cannot be empty")
    ok = update_memory(user_id, index, content)
    if not ok:
        raise HTTPException(status_code=404, detail="Memory not found")
    return {"ok": True}


@router.delete("/{index}")
async def remove_memory(index: int, user_id: int = Depends(get_current_user)):
    """Delete one memory by 1-based index."""
    if index < 1:
        raise HTTPException(status_code=400, detail="Index must be >= 1")
    ok = delete_memory(user_id, index)
    if not ok:
        raise HTTPException(status_code=404, detail="Memory not found")
    return {"ok": True}


@router.delete("")
async def remove_all_memories(user_id: int = Depends(get_current_user)):
    """Clear all memories for current user."""
    cleared = clear_memories(user_id)
    return {"ok": True, "cleared": cleared}
