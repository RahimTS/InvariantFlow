from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from uuid import uuid4

from app.runtime.events import make_event


class RunRegistry:
    def __init__(self, max_runs: int = 200) -> None:
        self._max_runs = max_runs
        self._runs: dict[str, dict] = {}
        self._run_order: list[str] = []
        self._subscribers: set[asyncio.Queue] = set()
        self._lock = asyncio.Lock()

    async def create_run(self, metadata: dict | None = None) -> str:
        run_id = f"run_{uuid4().hex}"
        now = _now()
        async with self._lock:
            self._runs[run_id] = {
                "run_id": run_id,
                "status": "started",
                "created_at": now,
                "updated_at": now,
                "metadata": metadata or {},
            }
            self._run_order.append(run_id)
            self._trim()
        await self.publish(make_event("RUN_START", {"run_id": run_id}, run_id=run_id))
        return run_id

    async def complete_run(self, run_id: str, summary: dict) -> None:
        now = _now()
        async with self._lock:
            current = self._runs.get(run_id, {"run_id": run_id, "created_at": now})
            current["status"] = "completed"
            current["updated_at"] = now
            current["summary"] = summary
            self._runs[run_id] = current
            if run_id not in self._run_order:
                self._run_order.append(run_id)
                self._trim()
        await self.publish(
            make_event(
                "RUN_COMPLETE",
                {"run_id": run_id, "summary": summary},
                run_id=run_id,
            )
        )

    async def fail_run(self, run_id: str, error: str) -> None:
        now = _now()
        async with self._lock:
            current = self._runs.get(run_id, {"run_id": run_id, "created_at": now})
            current["status"] = "failed"
            current["updated_at"] = now
            current["error"] = error
            self._runs[run_id] = current
            if run_id not in self._run_order:
                self._run_order.append(run_id)
                self._trim()
        await self.publish(
            make_event(
                "RUN_FAILED",
                {"run_id": run_id, "error": error},
                run_id=run_id,
            )
        )

    async def list_runs(self, limit: int = 50) -> list[dict]:
        async with self._lock:
            ids = list(reversed(self._run_order))[:limit]
            return [self._runs[i] for i in ids if i in self._runs]

    async def get_run(self, run_id: str) -> dict | None:
        async with self._lock:
            return self._runs.get(run_id)

    async def latest_dead_tasks(self) -> list[dict]:
        runs = await self.list_runs(limit=50)
        dead: list[dict] = []
        for run in runs:
            summary = run.get("summary") or {}
            for task in summary.get("dead_task_details", []):
                dead.append(task)
        return dead

    async def publish(self, event: dict) -> None:
        stale: list[asyncio.Queue] = []
        for queue in list(self._subscribers):
            try:
                queue.put_nowait(event)
            except asyncio.QueueFull:
                stale.append(queue)
        for queue in stale:
            self._subscribers.discard(queue)

    def subscribe(self, maxsize: int = 100) -> asyncio.Queue:
        queue: asyncio.Queue = asyncio.Queue(maxsize=maxsize)
        self._subscribers.add(queue)
        return queue

    def unsubscribe(self, queue: asyncio.Queue) -> None:
        self._subscribers.discard(queue)

    def _trim(self) -> None:
        overflow = len(self._run_order) - self._max_runs
        if overflow <= 0:
            return
        for _ in range(overflow):
            rid = self._run_order.pop(0)
            self._runs.pop(rid, None)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


run_registry = RunRegistry()
