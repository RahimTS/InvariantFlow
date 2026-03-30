from __future__ import annotations

import json
from typing import Any

try:
    from redis import asyncio as redis
except ImportError:  # pragma: no cover - optional dependency
    redis = None  # type: ignore[assignment]


class RedisStateStore:
    def __init__(self, redis_url: str, ttl_seconds: int = 3600) -> None:
        self._redis_url = redis_url
        self._ttl_seconds = ttl_seconds
        self._client: Any = None

    async def init(self) -> None:
        self._ensure_driver()
        self._client = redis.from_url(self._redis_url, decode_responses=True)

    async def close(self) -> None:
        if self._client is not None:
            await self._client.aclose()

    async def get_entity(self, run_id: str, entity_id: str) -> dict | None:
        await self._ensure_client()
        data = await self._client.hgetall(_state_key(run_id, entity_id))
        if not data:
            return None
        return _deserialize_hash(data)

    async def update_entity(self, run_id: str, entity_id: str, fields: dict) -> None:
        await self._ensure_client()
        key = _state_key(run_id, entity_id)
        encoded = {k: _encode(v) for k, v in fields.items()}
        if encoded:
            await self._client.hset(key, mapping=encoded)
            await self._client.expire(key, self._ttl_seconds)

    async def get_status_history(self, run_id: str, entity_id: str) -> list[str]:
        entity = await self.get_entity(run_id, entity_id)
        if not entity:
            return []
        hist = entity.get("status_history", [])
        return hist if isinstance(hist, list) else []

    async def get_entities_by_type(self, run_id: str, entity_type: str) -> list[dict]:
        await self._ensure_client()
        pattern = _state_key(run_id, "*")
        keys = await self._client.keys(pattern)
        out: list[dict] = []
        for key in keys:
            row = _deserialize_hash(await self._client.hgetall(key))
            if str(row.get("type", "")).lower() == entity_type.lower():
                out.append(row)
        return out

    async def get_related_entities(self, run_id: str, entity_id: str) -> list[dict]:
        await self._ensure_client()
        pattern = _state_key(run_id, "*")
        keys = await self._client.keys(pattern)
        out: list[dict] = []
        for key in keys:
            row = _deserialize_hash(await self._client.hgetall(key))
            if row.get("id") == entity_id:
                continue
            if any(v == entity_id for v in row.values()):
                out.append(row)
        return out

    async def snapshot(self, run_id: str) -> dict:
        await self._ensure_client()
        pattern = _state_key(run_id, "*")
        keys = await self._client.keys(pattern)
        out: dict[str, dict] = {}
        for key in keys:
            row = _deserialize_hash(await self._client.hgetall(key))
            entity_id = str(row.get("id") or key.rsplit(":", 1)[-1])
            out[entity_id] = row
        return out

    async def clear(self, run_id: str) -> None:
        await self._ensure_client()
        pattern = _state_key(run_id, "*")
        keys = await self._client.keys(pattern)
        if keys:
            await self._client.delete(*keys)

    def _ensure_driver(self) -> None:
        if redis is None:  # pragma: no cover
            raise RuntimeError("redis is required for RedisStateStore. Install redis>=5.")

    async def _ensure_client(self) -> None:
        if self._client is None:
            await self.init()


def _state_key(run_id: str, entity_id: str) -> str:
    return f"state:{run_id}:{entity_id}"


def _encode(value: Any) -> str:
    if isinstance(value, (dict, list)):
        return json.dumps(value)
    return str(value)


def _deserialize_hash(data: dict[str, str]) -> dict:
    out: dict[str, Any] = {}
    for k, v in data.items():
        out[k] = _maybe_json(v)
    return out


def _maybe_json(value: str) -> Any:
    try:
        return json.loads(value)
    except (json.JSONDecodeError, TypeError):
        return value
