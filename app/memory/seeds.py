"""
Starter logistics rules from the architecture document.
"""

from __future__ import annotations

from app.memory.rule_store import RuleStore
from app.schemas.rules import BusinessRule, RuleTrigger


def starter_rules() -> list[BusinessRule]:
    return [
        BusinessRule(
            rule_id="SHIP_001",
            type="constraint",
            description="Shipment weight must not exceed assigned vehicle capacity",
            entities=["Shipment", "Vehicle"],
            conditions=["scenario.shipment_weight <= entities.vehicle.capacity"],
            expected_effect=["dispatch should be rejected if weight exceeds capacity"],
            invalid_scenarios=["shipment_weight > vehicle_capacity should fail dispatch"],
            edge_cases=["shipment_weight == vehicle_capacity", "vehicle_capacity == 0"],
            status="approved",
            created_by="seed",
            requires_llm=False,
        ),
        BusinessRule(
            rule_id="SHIP_002",
            type="precondition",
            description="Shipment must be ASSIGNED before dispatch",
            entities=["Shipment"],
            conditions=["entities.shipment.status == 'ASSIGNED'"],
            trigger=RuleTrigger(endpoint="POST /shipments/{id}/dispatch"),
            expected_effect=["dispatch should fail if not ASSIGNED"],
            invalid_scenarios=["dispatch a CREATED shipment without assigning"],
            status="approved",
            created_by="seed",
            requires_llm=False,
        ),
        BusinessRule(
            rule_id="SHIP_003",
            type="postcondition",
            description="After dispatch, status must be DISPATCHED and dispatched_at set",
            entities=["Shipment"],
            conditions=[
                "entities.shipment.status == 'DISPATCHED'",
                "entities.shipment.dispatched_at != null",
            ],
            trigger=RuleTrigger(endpoint="POST /shipments/{id}/dispatch"),
            expected_effect=["status transitions to DISPATCHED", "dispatched_at is populated"],
            invalid_scenarios=["dispatch response missing timestamp"],
            status="approved",
            created_by="seed",
            requires_llm=False,
        ),
    ]


async def seed_starter_rules(rule_store: RuleStore) -> None:
    for rule in starter_rules():
        await rule_store.insert_rule(rule)

