from __future__ import annotations

import json
from typing import Any

try:
    from redis import asyncio as redis
except ImportError:  # pragma: no cover - optional dependency
    redis = None  # type: ignore[assignment]


class RedisEventEmitter:
    def __init__(self, redis_url: str, channel: str = "events:testing") -> None:
        self._redis_url = redis_url
        self._channel = channel
        self._client: Any = None

    async def init(self) -> None:
        self._ensure_driver()
        self._client = redis.from_url(self._redis_url, decode_responses=True)

    async def close(self) -> None:
        if self._client is not None:
            await self._client.aclose()

    async def emit(self, event: dict) -> None:
        if self._client is None:
            await self.init()
        await self._client.publish(self._channel, json.dumps(event))

    def _ensure_driver(self) -> None:
        if redis is None:  # pragma: no cover
            raise RuntimeError("redis is required for RedisEventEmitter. Install redis>=5.")


class RedisEventSubscriber:
    def __init__(self, redis_url: str, channel: str = "events:testing") -> None:
        self._redis_url = redis_url
        self._channel = channel
        self._client: Any = None
        self._pubsub: Any = None

    async def connect(self) -> None:
        self._ensure_driver()
        self._client = redis.from_url(self._redis_url, decode_responses=True)
        self._pubsub = self._client.pubsub()
        await self._pubsub.subscribe(self._channel)

    async def iter_events(self):
        if self._pubsub is None:
            await self.connect()
        while True:
            event = await self.get_event(timeout_seconds=1.0)
            if event is None:
                continue
            yield event

    async def get_event(self, timeout_seconds: float = 1.0) -> dict | None:
        if self._pubsub is None:
            await self.connect()
        message = await self._pubsub.get_message(
            ignore_subscribe_messages=True,
            timeout=timeout_seconds,
        )
        if not message:
            return None
        data = message.get("data")
        if isinstance(data, str):
            try:
                return json.loads(data)
            except json.JSONDecodeError:
                return {"event": "raw", "data": data}
        return None

    async def close(self) -> None:
        if self._pubsub is not None:
            await self._pubsub.close()
        if self._client is not None:
            await self._client.aclose()

    def _ensure_driver(self) -> None:
        if redis is None:  # pragma: no cover
            raise RuntimeError("redis is required for RedisEventSubscriber. Install redis>=5.")
