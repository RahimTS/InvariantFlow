import pytest
from pathlib import Path
from uuid import uuid4

import httpx

from app.main import app


@pytest.mark.asyncio
async def test_protocol_and_agent_endpoints() -> None:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        card = await client.get("/.well-known/agent-card.json")
        assert card.status_code == 200
        assert card.json()["agents"]

        tools = await client.get("/api/v1/mcp/tools")
        assert tools.status_code == 200
        assert tools.json()["count"] >= 1

        statuses = await client.get("/api/v1/agents/status")
        assert statuses.status_code == 200
        assert statuses.json()["count"] >= 1

        beat = await client.post("/api/v1/agents/executor/heartbeat")
        assert beat.status_code == 200
        assert beat.json()["agent_id"] == "executor"

        mem_path = str(Path("artifacts") / f"mem0_{uuid4().hex}.json")
        wrote = await client.post(
            "/api/v1/mem0/critic",
            json={"run_id": "run_1", "memory": {"note": "found edge case"}, "path": mem_path},
        )
        assert wrote.status_code == 200
        got = await client.get("/api/v1/mem0/critic", params={"run_id": "run_1", "path": mem_path})
        assert got.status_code == 200
        assert got.json()["items"]

        dead = await client.get("/api/v1/tasks/dead")
        assert dead.status_code == 200
