"""
In-memory store for the mock logistics API.

Pre-seeded vehicles:
  VH_001 — capacity 1000 kg
  VH_002 — capacity 2000 kg
  VH_003 — capacity  500 kg

Reset via reset() between tests.
"""

from __future__ import annotations
import itertools
from datetime import datetime, timezone

_counter = itertools.count(1)

_shipments: dict[str, dict] = {}
_vehicles: dict[str, dict] = {
    "VH_001": {"id": "VH_001", "type": "Vehicle", "capacity": 1000, "assigned_shipments": []},
    "VH_002": {"id": "VH_002", "type": "Vehicle", "capacity": 2000, "assigned_shipments": []},
    "VH_003": {"id": "VH_003", "type": "Vehicle", "capacity": 500, "assigned_shipments": []},
}


def reset() -> None:
    """Reset store to initial seeded state (call between tests)."""
    global _counter
    _counter = itertools.count(1)
    _shipments.clear()
    _vehicles.clear()
    _vehicles.update(
        {
            "VH_001": {"id": "VH_001", "type": "Vehicle", "capacity": 1000, "assigned_shipments": []},
            "VH_002": {"id": "VH_002", "type": "Vehicle", "capacity": 2000, "assigned_shipments": []},
            "VH_003": {"id": "VH_003", "type": "Vehicle", "capacity": 500, "assigned_shipments": []},
        }
    )


def next_shipment_id() -> str:
    return f"SHIP_{next(_counter):04d}"


def create_shipment(weight: int, origin: str, destination: str) -> dict:
    sid = next_shipment_id()
    shipment = {
        "id": sid,
        "type": "Shipment",
        "weight": weight,
        "origin": origin,
        "destination": destination,
        "status": "CREATED",
        "status_history": ["CREATED"],
        "assigned_vehicle": None,
        "vehicle_capacity": None,
        "dispatched_at": None,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    _shipments[sid] = shipment
    return shipment


def get_shipment(shipment_id: str) -> dict | None:
    return _shipments.get(shipment_id)


def get_vehicle(vehicle_id: str) -> dict | None:
    return _vehicles.get(vehicle_id)


def assign_vehicle(shipment_id: str, vehicle_id: str) -> dict:
    shipment = _shipments[shipment_id]
    vehicle = _vehicles[vehicle_id]
    shipment["status"] = "ASSIGNED"
    shipment["status_history"].append("ASSIGNED")
    shipment["assigned_vehicle"] = vehicle_id
    shipment["vehicle_capacity"] = vehicle["capacity"]
    vehicle["assigned_shipments"].append(shipment_id)
    return shipment


def dispatch_shipment(shipment_id: str) -> dict:
    shipment = _shipments[shipment_id]
    shipment["status"] = "DISPATCHED"
    shipment["status_history"].append("DISPATCHED")
    shipment["dispatched_at"] = datetime.now(timezone.utc).isoformat()
    return shipment
