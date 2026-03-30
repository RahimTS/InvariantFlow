from __future__ import annotations

import asyncio
import json

from fastapi import APIRouter, Request
from sse_starlette.sse import EventSourceResponse

from app.runtime import run_registry

router = APIRouter(tags=["sse"])


@router.get("/api/v1/stream/testing")
async def stream_testing_events(request: Request) -> EventSourceResponse:
    queue = run_registry.subscribe(maxsize=200)

    async def event_generator():
        try:
            while True:
                if await request.is_disconnected():
                    break
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=15.0)
                    yield {
                        "event": event.get("event", "message"),
                        "data": json.dumps(event),
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

