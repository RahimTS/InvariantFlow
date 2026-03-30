"""
Phase 5 groundwork: V2 storage adapters.
These adapters are intentionally lightweight and optional in V1 environments.
"""

from __future__ import annotations

from typing import Any


class PostgresRuleStore:
    def __init__(self, dsn: str) -> None:
        self._dsn = dsn

    async def init(self) -> None:
        raise NotImplementedError("PostgresRuleStore requires asyncpg integration in V2 deployment.")


class RedisStateStore:
    def __init__(self, redis_url: str) -> None:
        self._redis_url = redis_url

    async def get_entity(self, run_id: str, entity_id: str) -> dict | None:
        raise NotImplementedError("RedisStateStore requires redis async client in V2 deployment.")

    async def update_entity(self, run_id: str, entity_id: str, fields: dict) -> None:
        raise NotImplementedError("RedisStateStore requires redis async client in V2 deployment.")

    async def get_status_history(self, run_id: str, entity_id: str) -> list[str]:
        raise NotImplementedError("RedisStateStore requires redis async client in V2 deployment.")

    async def get_entities_by_type(self, run_id: str, entity_type: str) -> list[dict]:
        raise NotImplementedError("RedisStateStore requires redis async client in V2 deployment.")

    async def get_related_entities(self, run_id: str, entity_id: str) -> list[dict]:
        raise NotImplementedError("RedisStateStore requires redis async client in V2 deployment.")

    async def snapshot(self, run_id: str) -> dict:
        raise NotImplementedError("RedisStateStore requires redis async client in V2 deployment.")

    async def clear(self, run_id: str) -> None:
        raise NotImplementedError("RedisStateStore requires redis async client in V2 deployment.")


class RedisBlackboard:
    def __init__(self, redis_url: str) -> None:
        self._redis_url = redis_url

    async def post_task(self, task: dict[str, Any]) -> str:
        raise NotImplementedError("RedisBlackboard requires Redis Streams implementation in V2 deployment.")

