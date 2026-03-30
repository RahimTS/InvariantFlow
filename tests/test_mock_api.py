import pytest
import httpx

from app.main import app


@pytest.mark.asyncio
async def test_create_assign_dispatch_success_path() -> None:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        created = await client.post(
            "/api/v1/shipments",
            json={"weight": 500, "origin": "BLR", "destination": "DEL"},
        )
        assert created.status_code == 201
        shipment_id = created.json()["shipment_id"]

        assigned = await client.post(
            f"/api/v1/shipments/{shipment_id}/assign",
            json={"vehicle_id": "VH_001"},
        )
        assert assigned.status_code == 200

        dispatched = await client.post(f"/api/v1/shipments/{shipment_id}/dispatch", json={})
        assert dispatched.status_code == 200
        assert dispatched.json()["status"] == "DISPATCHED"


@pytest.mark.asyncio
async def test_dispatch_without_assign_fails() -> None:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        created = await client.post(
            "/api/v1/shipments",
            json={"weight": 500, "origin": "BLR", "destination": "DEL"},
        )
        shipment_id = created.json()["shipment_id"]

        dispatched = await client.post(f"/api/v1/shipments/{shipment_id}/dispatch", json={})
        assert dispatched.status_code == 400


@pytest.mark.asyncio
async def test_intentional_weight_bug_allows_overweight_dispatch() -> None:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        created = await client.post(
            "/api/v1/shipments",
            json={"weight": 1200, "origin": "BLR", "destination": "DEL"},
        )
        shipment_id = created.json()["shipment_id"]

        assigned = await client.post(
            f"/api/v1/shipments/{shipment_id}/assign",
            json={"vehicle_id": "VH_001"},
        )
        assert assigned.status_code == 200
        assert assigned.json()["vehicle_capacity"] == 1000

        dispatched = await client.post(f"/api/v1/shipments/{shipment_id}/dispatch", json={})
        assert dispatched.status_code == 200
        assert dispatched.json()["status"] == "DISPATCHED"

