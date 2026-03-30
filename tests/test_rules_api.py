import pytest
from pathlib import Path
from uuid import uuid4

import httpx

from app.main import app


@pytest.mark.asyncio
async def test_rules_approval_flow_via_api() -> None:
    run_root = Path("artifacts") / f"rules_api_{uuid4().hex}"
    run_root.mkdir(parents=True, exist_ok=True)
    db_path = str(run_root / "rules.db")

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        ingest = await client.post(
            "/api/v1/ingestion/ingest",
            json={
                "source": "ticket-77",
                "text": "Shipment weight must not exceed vehicle capacity.",
                "db_path": db_path,
            },
        )
        assert ingest.status_code == 200
        rules = ingest.json()["rules"]
        assert rules
        rule_id = rules[0]["rule_id"]

        pending = await client.get("/api/v1/rules/pending", params={"db_path": db_path})
        assert pending.status_code == 200
        assert pending.json()["count"] >= 1

        approve = await client.post(
            f"/api/v1/rules/{rule_id}/approve",
            json={"db_path": db_path, "approved_by": "rahim"},
        )
        assert approve.status_code == 200
        assert approve.json()["rule"]["status"] == "approved"

        pending_after = await client.get("/api/v1/rules/pending", params={"db_path": db_path})
        assert pending_after.status_code == 200
        assert pending_after.json()["count"] == 0

