"""
Blackboard — the shared task board for the testing swarm.

Safety mechanisms:
  - Atomic claim (asyncio.Lock + compare-and-swap)
  - Stuck task timeout: tasks in claimed/in_progress > timeout_s → revert to posted
  - Max retries: after max_retries → transition to dead
  - Dead task surfacing via get_dead_tasks()

Task lifecycle:  posted → claimed → in_progress → completed
                                                 → dead (after max_retries)
"""

from __future__ import annotations
import asyncio
from datetime import datetime, timezone
from typing import Any


class Blackboard:
    def __init__(
        self,
        timeout_seconds: int = 60,
        max_retries: int = 3,
    ) -> None:
        self._board: dict[str, dict[str, Any]] = {}
        self._lock = asyncio.Lock()
        self._timeout_seconds = timeout_seconds
        self._max_retries = max_retries
        self._watcher_task: asyncio.Task | None = None

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def start_watcher(self) -> None:
        """Start background timeout watcher. Call after event loop is running."""
        self._watcher_task = asyncio.create_task(self._timeout_watcher())

    async def stop_watcher(self) -> None:
        if self._watcher_task:
            self._watcher_task.cancel()
            try:
                await self._watcher_task
            except asyncio.CancelledError:
                pass

    # ------------------------------------------------------------------
    # Task management
    # ------------------------------------------------------------------

    async def post_task(self, task_id: str, task_type: str, data: dict | None = None) -> str:
        """Post a new task. Returns task_id."""
        async with self._lock:
            self._board[task_id] = {
                "task_id": task_id,
                "type": task_type,
                "status": "posted",
                "claimed_by": None,
                "posted_at": _now(),
                "claimed_at": None,
                "completed_at": None,
                "retry_count": 0,
                "data": data or {},
            }
        return task_id

    async def claim_task(
        self,
        task_type: str | None = None,
        agent_id: str = "agent",
    ) -> dict | None:
        """Atomically claim the next available posted task.

        Returns the task dict (with task_id included) or None if nothing available.
        """
        async with self._lock:
            for task_id, task in self._board.items():
                if task["status"] != "posted":
                    continue
                if task_type and task["type"] != task_type:
                    continue
                task["status"] = "claimed"
                task["claimed_by"] = agent_id
                task["claimed_at"] = _now()
                return dict(task)
        return None

    async def start_task(self, task_id: str) -> None:
        async with self._lock:
            if task_id in self._board:
                self._board[task_id]["status"] = "in_progress"

    async def complete_task(self, task_id: str, result: dict | None = None) -> None:
        async with self._lock:
            if task_id in self._board:
                self._board[task_id]["status"] = "completed"
                self._board[task_id]["completed_at"] = _now()
                if result:
                    self._board[task_id]["result"] = result

    async def fail_task(self, task_id: str, error: str) -> None:
        async with self._lock:
            if task_id in self._board:
                task = self._board[task_id]
                task["retry_count"] += 1
                if task["retry_count"] >= self._max_retries:
                    task["status"] = "dead"
                    task["error"] = error
                else:
                    task["status"] = "posted"
                    task["claimed_by"] = None
                    task["claimed_at"] = None

    async def get_task(self, task_id: str) -> dict | None:
        return self._board.get(task_id)

    async def get_pending_tasks(self, task_type: str | None = None) -> list[dict]:
        tasks = [t for t in self._board.values() if t["status"] == "posted"]
        if task_type:
            tasks = [t for t in tasks if t["type"] == task_type]
        return tasks

    async def get_dead_tasks(self) -> list[dict]:
        return [t for t in self._board.values() if t["status"] == "dead"]

    async def get_all(self) -> dict[str, dict]:
        return dict(self._board)

    # ------------------------------------------------------------------
    # Timeout watcher
    # ------------------------------------------------------------------

    async def _timeout_watcher(self) -> None:
        while True:
            await asyncio.sleep(10)
            now_ts = datetime.now(timezone.utc)
            async with self._lock:
                for task in self._board.values():
                    if task["status"] not in ("claimed", "in_progress"):
                        continue
                    claimed_str = task.get("claimed_at")
                    if not claimed_str:
                        continue
                    claimed_dt = datetime.fromisoformat(claimed_str)
                    if (now_ts - claimed_dt).total_seconds() > self._timeout_seconds:
                        task["retry_count"] += 1
                        if task["retry_count"] >= self._max_retries:
                            task["status"] = "dead"
                        else:
                            task["status"] = "posted"
                            task["claimed_by"] = None
                            task["claimed_at"] = None


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()
