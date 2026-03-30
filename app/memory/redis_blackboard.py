from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any
import inspect
import logging

try:
    from redis import asyncio as redis
except ImportError:  # pragma: no cover - optional dependency
    redis = None  # type: ignore[assignment]

from app.runtime.events import make_event

logger = logging.getLogger(__name__)


class RedisBlackboard:
    def __init__(
        self,
        redis_url: str,
        stream_key: str = "blackboard:tasks",
        group_name: str = "swarm_workers",
        task_prefix: str = "task",
        max_retries: int = 3,
        event_emitter: Any | None = None,
    ) -> None:
        self._redis_url = redis_url
        self._stream_key = stream_key
        self._group_name = group_name
        self._task_prefix = task_prefix
        self._max_retries = max_retries
        self._event_emitter = event_emitter
        self._client: Any = None

    async def init(self) -> None:
        self._ensure_driver()
        self._client = redis.from_url(self._redis_url, decode_responses=True)
        try:
            await self._client.xgroup_create(self._stream_key, self._group_name, id="$", mkstream=True)
        except Exception:
            pass

    async def close(self) -> None:
        if self._client is not None:
            await self._client.aclose()

    async def post_task(self, task_id: str, task_type: str, data: dict | None = None) -> str:
        await self._ensure_client()
        payload = {
            "task_id": task_id,
            "type": task_type,
            "status": "posted",
            "claimed_by": "",
            "posted_at": _now(),
            "claimed_at": "",
            "completed_at": "",
            "retry_count": "0",
            "data": json.dumps(data or {}),
        }
        await self._client.hset(self._task_key(task_id), mapping=payload)
        await self._client.xadd(self._stream_key, {"task_id": task_id, "type": task_type})
        await self._emit(
            make_event(
                "TASK_POSTED",
                {"task_id": task_id, "type": task_type, "data": data or {}},
            )
        )
        return task_id

    async def claim_task(self, task_type: str | None = None, agent_id: str = "agent") -> dict | None:
        await self._ensure_client()
        messages = await self._client.xreadgroup(
            groupname=self._group_name,
            consumername=agent_id,
            streams={self._stream_key: ">"},
            count=10,
            block=50,
        )
        if not messages:
            return None
        for _, entries in messages:
            for stream_id, fields in entries:
                task_id = fields.get("task_id")
                if not task_id:
                    continue
                task = await self._read_task(task_id)
                if not task or task.get("status") != "posted":
                    await self._client.xack(self._stream_key, self._group_name, stream_id)
                    continue
                if task_type and task.get("type") != task_type:
                    await self._client.xack(self._stream_key, self._group_name, stream_id)
                    await self._client.xadd(
                        self._stream_key,
                        {"task_id": task_id, "type": task.get("type", "")},
                    )
                    continue
                task["status"] = "claimed"
                task["claimed_by"] = agent_id
                task["claimed_at"] = _now()
                await self._write_task(task_id, task)
                await self._client.xack(self._stream_key, self._group_name, stream_id)
                await self._emit(
                    make_event(
                        "TASK_CLAIMED",
                        {
                            "task_id": task_id,
                            "type": task.get("type"),
                            "agent_id": agent_id,
                        },
                    )
                )
                return task
        return None

    async def start_task(self, task_id: str) -> None:
        await self._patch_task(task_id, {"status": "in_progress"})

    async def complete_task(self, task_id: str, result: dict | None = None) -> None:
        patch = {"status": "completed", "completed_at": _now()}
        if result is not None:
            patch["result"] = result
        await self._patch_task(task_id, patch)
        task = await self._read_task(task_id)
        await self._emit(
            make_event(
                "TASK_COMPLETED",
                {
                    "task_id": task_id,
                    "type": task.get("type") if task else None,
                    "result": result or {},
                },
            )
        )

    async def fail_task(self, task_id: str, error: str) -> None:
        task = await self._read_task(task_id)
        if not task:
            return
        retries = int(task.get("retry_count", 0)) + 1
        task["retry_count"] = retries
        if retries >= self._max_retries:
            task["status"] = "dead"
            task["error"] = error
            await self._emit(
                make_event(
                    "TASK_DEAD",
                    {
                        "task_id": task_id,
                        "type": task.get("type"),
                        "error": error,
                    },
                )
            )
        else:
            task["status"] = "posted"
            task["claimed_by"] = ""
            task["claimed_at"] = ""
            await self._client.xadd(
                self._stream_key,
                {"task_id": task_id, "type": task.get("type", "")},
            )
        await self._write_task(task_id, task)

    async def get_pending_tasks(self, task_type: str | None = None) -> list[dict]:
        await self._ensure_client()
        keys = await self._client.keys(f"{self._task_prefix}:*")
        out: list[dict] = []
        for key in keys:
            task = _deserialize(await self._client.hgetall(key))
            if task.get("status") != "posted":
                continue
            if task_type and task.get("type") != task_type:
                continue
            out.append(task)
        return out

    async def get_dead_tasks(self) -> list[dict]:
        await self._ensure_client()
        keys = await self._client.keys(f"{self._task_prefix}:*")
        out: list[dict] = []
        for key in keys:
            task = _deserialize(await self._client.hgetall(key))
            if task.get("status") == "dead":
                out.append(task)
        return out

    async def _read_task(self, task_id: str) -> dict | None:
        raw = await self._client.hgetall(self._task_key(task_id))
        if not raw:
            return None
        return _deserialize(raw)

    async def _write_task(self, task_id: str, task: dict) -> None:
        encoded = {k: _encode(v) for k, v in task.items()}
        await self._client.hset(self._task_key(task_id), mapping=encoded)

    async def _patch_task(self, task_id: str, patch: dict) -> None:
        task = await self._read_task(task_id)
        if not task:
            return
        task.update(patch)
        await self._write_task(task_id, task)

    def _ensure_driver(self) -> None:
        if redis is None:  # pragma: no cover
            raise RuntimeError("redis is required for RedisBlackboard. Install redis>=5.")

    async def _ensure_client(self) -> None:
        if self._client is None:
            await self.init()

    def _task_key(self, task_id: str) -> str:
        return f"{self._task_prefix}:{task_id}"

    async def _emit(self, event: dict[str, Any]) -> None:
        if self._event_emitter is None:
            return
        try:
            result = self._event_emitter(event)
            if inspect.isawaitable(result):
                await result
        except Exception:
            logger.exception("redis blackboard event emission failed")


def _encode(value: Any) -> str:
    if isinstance(value, (dict, list)):
        return json.dumps(value)
    return str(value)


def _deserialize(data: dict[str, str]) -> dict:
    out: dict[str, Any] = {}
    for k, v in data.items():
        if k in {"data", "result"}:
            try:
                out[k] = json.loads(v)
            except json.JSONDecodeError:
                out[k] = v
        elif k == "retry_count":
            out[k] = int(v)
        else:
            out[k] = v
    return out


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()
