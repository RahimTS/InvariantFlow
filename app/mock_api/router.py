"""
Mock logistics API with three endpoints.

INTENTIONAL BUG: POST /dispatch does NOT check shipment_weight > vehicle_capacity.
Overweight shipments are dispatched successfully. The swarm must catch this.
"""

from fastapi import APIRouter, HTTPException
from app.mock_api import store
from app.mock_api.models import CreateShipmentRequest, AssignVehicleRequest

router = APIRouter(prefix="/api/v1", tags=["mock-logistics"])


@router.post("/shipments", status_code=201)
async def create_shipment(body: CreateShipmentRequest) -> dict:
    if body.weight <= 0:
        raise HTTPException(status_code=400, detail="Weight must be positive")
    shipment = store.create_shipment(body.weight, body.origin, body.destination)
    return {
        "shipment_id": shipment["id"],
        "status": shipment["status"],
        "weight": shipment["weight"],
    }


@router.post("/shipments/{shipment_id}/assign", status_code=200)
async def assign_shipment(shipment_id: str, body: AssignVehicleRequest) -> dict:
    shipment = store.get_shipment(shipment_id)
    if not shipment:
        raise HTTPException(status_code=404, detail="Shipment not found")

    vehicle = store.get_vehicle(body.vehicle_id)
    if not vehicle:
        raise HTTPException(status_code=404, detail="Vehicle not found")

    if shipment["status"] != "CREATED":
        raise HTTPException(status_code=400, detail="Only CREATED shipments can be assigned")

    store.assign_vehicle(shipment_id, body.vehicle_id)
    return {
        "shipment_id": shipment_id,
        "vehicle_id": body.vehicle_id,
        "vehicle_capacity": vehicle["capacity"],
        "status": "ASSIGNED",
    }


@router.post("/shipments/{shipment_id}/dispatch", status_code=200)
async def dispatch_shipment(shipment_id: str) -> dict:
    shipment = store.get_shipment(shipment_id)
    if not shipment:
        raise HTTPException(status_code=404, detail="Shipment not found")

    if shipment["status"] != "ASSIGNED":
        raise HTTPException(status_code=400, detail="Shipment must be ASSIGNED before dispatch")

    # -----------------------------------------------------------------------
    # INTENTIONAL BUG: weight check is deliberately omitted.
    # The correct check would be:
    #   if shipment["weight"] > shipment["vehicle_capacity"]:
    #       raise HTTPException(400, "Shipment weight exceeds vehicle capacity")
    # -----------------------------------------------------------------------

    updated = store.dispatch_shipment(shipment_id)
    return {
        "shipment_id": shipment_id,
        "status": updated["status"],
        "dispatched_at": updated["dispatched_at"],
    }
