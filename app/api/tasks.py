from __future__ import annotations

from fastapi import APIRouter

from app.runtime import run_registry

router = APIRouter(prefix="/api/v1/tasks", tags=["tasks"])


@router.get("/dead")
async def get_dead_tasks() -> dict:
    tasks = await run_registry.latest_dead_tasks()
    return {"count": len(tasks), "tasks": tasks}

