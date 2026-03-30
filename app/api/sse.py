from __future__ import annotations

import asyncio
import json
from typing import Any

from fastapi import APIRouter, Request
from sse_starlette.sse import EventSourceResponse

from app.config import settings
from app.memory.redis_events import RedisEventSubscriber
from app.runtime.events import make_event
from app.runtime import run_registry

router = APIRouter(tags=["sse"])


@router.get("/api/v1/stream/testing")
async def stream_testing_events(request: Request) -> EventSourceResponse:
    if settings.storage_backend == "docker":
        subscriber = RedisEventSubscriber(
            settings.redis_url,
            channel=settings.redis_events_channel,
        )

        async def redis_generator():
            try:
                await subscriber.connect()
                while True:
                    if await request.is_disconnected():
                        break
                    event = await subscriber.get_event(timeout_seconds=15.0)
                    if event is None:
                        yield {
                            "event": "heartbeat",
                            "data": json.dumps({"event": "heartbeat"}),
                        }
                        continue
                    payload = _normalize_event(event)
                    yield {
                        "event": payload.get("event", "message"),
                        "data": json.dumps(payload),
                    }
            finally:
                await subscriber.close()

        return EventSourceResponse(redis_generator())

    queue = run_registry.subscribe(maxsize=200)

    async def event_generator():
        try:
            while True:
                if await request.is_disconnected():
                    break
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=15.0)
                    payload = _normalize_event(event)
                    yield {
                        "event": payload.get("event", "message"),
                        "data": json.dumps(payload),
                    }
                except asyncio.TimeoutError:
                    yield {
                        "event": "heartbeat",
                        "data": json.dumps({"event": "heartbeat"}),
                    }
        finally:
            run_registry.unsubscribe(queue)

    return EventSourceResponse(event_generator())


@router.get("/api/v1/agui/stream")
async def stream_agui_events(request: Request) -> EventSourceResponse:
    # AG-UI compatible stream shape uses same payload source for now.
    return await stream_testing_events(request)


def _normalize_event(event: dict[str, Any]) -> dict[str, Any]:
    if "event_type" in event and "data" in event:
        return event

    legacy_name = str(event.get("event", "message"))
    if legacy_name == "run_started":
        return make_event(
            "RUN_START",
            {"run_id": event.get("run_id"), "legacy_event": "run_started"},
            run_id=event.get("run_id"),
        )
    if legacy_name == "run_completed":
        return make_event(
            "RUN_COMPLETE",
            {"run_id": event.get("run_id"), "summary": event.get("summary")},
            run_id=event.get("run_id"),
        )
    if legacy_name == "run_failed":
        return make_event(
            "RUN_FAILED",
            {"run_id": event.get("run_id"), "error": event.get("error")},
            run_id=event.get("run_id"),
        )
    return {
        "event": legacy_name,
        "event_type": legacy_name.upper(),
        "timestamp": event.get("timestamp"),
        "data": event,
        "run_id": event.get("run_id"),
    }
