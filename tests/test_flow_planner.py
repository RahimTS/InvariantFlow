import pytest

from app.agents.testing.flow_planner import FlowPlanner, KNOWN_ROUTES
from app.schemas.rules import BusinessRule
from app.schemas.scenarios import FlowPlan, FlowStep, Scenario


def test_flow_planner_builds_precondition_invalid_flow_without_assign() -> None:
    rule = BusinessRule(
        rule_id="SHIP_002",
        type="precondition",
        description="Shipment must be ASSIGNED before dispatch",
        entities=["Shipment"],
        conditions=["entities.shipment.status == 'ASSIGNED'"],
        expected_effect=["dispatch should fail if not ASSIGNED"],
        invalid_scenarios=["dispatch without assign"],
        status="approved",
    )
    scenario = Scenario(
        scenario_id="SHIP_002_SCN_002",
        rule_id="SHIP_002",
        label="invalid",
        inputs={
            "shipment_weight": 500,
            "origin": "BLR",
            "destination": "DEL",
            "vehicle_id": "VH_001",
            "assign_before_dispatch": False,
        },
        expected_outcome="fail",
        rationale="skip assign",
    )

    plan = FlowPlanner().generate(rule, scenario)
    endpoints = [step.endpoint for step in plan.steps]
    assert "/api/v1/shipments/{shipment_id}/assign" not in endpoints
    assert plan.steps[-1].expected_status == [400]


def test_flow_validation_catches_missing_state_dependency() -> None:
    plan = FlowPlan(
        flow_id="BAD_FLOW",
        rule_id="SHIP_001",
        name="bad flow",
        description="missing extraction before state reference",
        steps=[
            FlowStep(
                step_number=1,
                endpoint="/api/v1/shipments",
                method="POST",
                payload_map={"weight": "$scenario.shipment_weight"},
                extract={},
                expected_status=[201],
            ),
            FlowStep(
                step_number=2,
                endpoint="/api/v1/shipments/{shipment_id}/dispatch",
                method="POST",
                path_params={"shipment_id": "$state.shipment_id"},
                payload_map={},
                extract={},
                expected_status=[400],
            ),
        ],
    )

    issues = FlowPlanner.validate_flow_plan(plan, known_routes=KNOWN_ROUTES)
    assert any("missing state dependency 'shipment_id'" in issue for issue in issues)


def test_flow_planner_rejects_unknown_route() -> None:
    planner = FlowPlanner(known_routes={"/api/v1/shipments"})
    rule = BusinessRule(
        rule_id="SHIP_001",
        type="constraint",
        description="Shipment weight must not exceed assigned vehicle capacity",
        entities=["Shipment", "Vehicle"],
        conditions=["scenario.shipment_weight <= entities.vehicle.capacity"],
        expected_effect=["dispatch should be rejected if weight exceeds capacity"],
        invalid_scenarios=["shipment_weight > vehicle_capacity should fail dispatch"],
        status="approved",
    )
    scenario = Scenario(
        scenario_id="SHIP_001_SCN_001",
        rule_id="SHIP_001",
        label="valid",
        inputs={
            "shipment_weight": 500,
            "origin": "BLR",
            "destination": "DEL",
            "vehicle_id": "VH_001",
        },
        expected_outcome="pass",
        rationale="baseline",
    )

    with pytest.raises(ValueError, match="unknown endpoint"):
        planner.generate(rule, scenario)
