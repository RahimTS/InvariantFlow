import pytest
from pathlib import Path
from uuid import uuid4

import httpx

from app.main import app


@pytest.mark.asyncio
async def test_run_rules_endpoint_blackboard_mode() -> None:
    run_root = Path("artifacts") / f"api_bb_{uuid4().hex}"
    run_root.mkdir(parents=True, exist_ok=True)

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.post(
            "/api/v1/testing/run",
            json={
                "mode": "blackboard",
                "seed_starter": True,
                "entity": "Shipment",
                "db_path": str(run_root / "rules.db"),
                "artifacts_dir": str(run_root / "exec"),
            },
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["mode"] == "blackboard"
    assert payload["total_rules"] == 3
    assert payload["failed"] >= 1
    assert payload["dead_tasks"] == 0


@pytest.mark.asyncio
async def test_run_rules_endpoint_direct_mode() -> None:
    run_root = Path("artifacts") / f"api_direct_{uuid4().hex}"
    run_root.mkdir(parents=True, exist_ok=True)

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.post(
            "/api/v1/testing/run",
            json={
                "mode": "direct",
                "seed_starter": True,
                "entity": "Shipment",
                "db_path": str(run_root / "rules.db"),
                "artifacts_dir": str(run_root / "exec"),
            },
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["mode"] == "direct"
    assert payload["total_rules"] == 3
    assert payload["failed"] >= 1


@pytest.mark.asyncio
async def test_run_rules_endpoint_langgraph_mode() -> None:
    run_root = Path("artifacts") / f"api_langgraph_{uuid4().hex}"
    run_root.mkdir(parents=True, exist_ok=True)

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.post(
            "/api/v1/testing/run",
            json={
                "mode": "langgraph",
                "seed_starter": True,
                "entity": "Shipment",
                "db_path": str(run_root / "rules.db"),
                "artifacts_dir": str(run_root / "exec"),
            },
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["mode"] == "langgraph"
    assert payload["total_rules"] == 3
    assert payload["failed"] >= 1
    assert payload["feedback"]
