import pytest

from app.agents.testing.executor import Executor
from app.agents.testing.oracle import Oracle
from app.main import app
from app.schemas.rules import BusinessRule
from app.schemas.scenarios import FlowPlan, FlowStep, Scenario


def _rule_ship_001() -> BusinessRule:
    return BusinessRule(
        rule_id="SHIP_001",
        type="constraint",
        description="Shipment weight must not exceed assigned vehicle capacity",
        entities=["Shipment", "Vehicle"],
        conditions=["scenario.shipment_weight <= entities.vehicle.capacity"],
        expected_effect=["dispatch should be rejected if weight exceeds capacity"],
        invalid_scenarios=["shipment_weight > vehicle_capacity should fail dispatch"],
        edge_cases=["shipment_weight == vehicle_capacity", "vehicle_capacity == 0"],
        status="approved",
    )


def _flow_for_dispatch(expected_dispatch_status: list[int]) -> FlowPlan:
    return FlowPlan(
        flow_id="FLOW_001",
        rule_id="SHIP_001",
        name="Create -> Assign -> Dispatch",
        description="Deterministic logistics flow",
        steps=[
            FlowStep(
                step_number=1,
                endpoint="/api/v1/shipments",
                method="POST",
                payload_map={
                    "weight": "$scenario.shipment_weight",
                    "origin": "$scenario.origin",
                    "destination": "$scenario.destination",
                },
                extract={"shipment_id": "$.response.shipment_id"},
                expected_status=[201],
            ),
            FlowStep(
                step_number=2,
                endpoint="/api/v1/shipments/{shipment_id}/assign",
                method="POST",
                path_params={"shipment_id": "$state.shipment_id"},
                payload_map={"vehicle_id": "$scenario.vehicle_id"},
                extract={
                    "vehicle_id": "$.response.vehicle_id",
                    "vehicle_capacity": "$.response.vehicle_capacity",
                },
                expected_status=[200],
            ),
            FlowStep(
                step_number=3,
                endpoint="/api/v1/shipments/{shipment_id}/dispatch",
                method="POST",
                path_params={"shipment_id": "$state.shipment_id"},
                payload_map={},
                extract={
                    "status": "$.response.status",
                    "dispatched_at": "$.response.dispatched_at",
                },
                expected_status=expected_dispatch_status,
            ),
        ],
    )


@pytest.mark.asyncio
async def test_pipeline_catches_intentional_overweight_bug() -> None:
    scenario = Scenario(
        scenario_id="SCN_INVALID_001",
        rule_id="SHIP_001",
        label="invalid",
        inputs={
            "shipment_weight": 1200,
            "origin": "BLR",
            "destination": "DEL",
            "vehicle_id": "VH_001",
        },
        expected_outcome="fail",
        rationale="overweight shipment should be rejected at dispatch",
    )
    flow = _flow_for_dispatch(expected_dispatch_status=[400])
    executor = Executor(app=app)
    trace = await executor.execute(rule_id="SHIP_001", scenario=scenario, flow_plan=flow)

    verdict = Oracle().evaluate(_rule_ship_001(), scenario, trace)

    assert trace.overall_status == "error"
    assert verdict.result == "fail"
    assert "scenario.shipment_weight <= entities.vehicle.capacity" in verdict.violated_conditions


@pytest.mark.asyncio
async def test_pipeline_passes_when_within_capacity() -> None:
    scenario = Scenario(
        scenario_id="SCN_VALID_001",
        rule_id="SHIP_001",
        label="valid",
        inputs={
            "shipment_weight": 800,
            "origin": "BLR",
            "destination": "DEL",
            "vehicle_id": "VH_001",
        },
        expected_outcome="pass",
        rationale="shipment under capacity should dispatch successfully",
    )
    flow = _flow_for_dispatch(expected_dispatch_status=[200])
    executor = Executor(app=app)
    trace = await executor.execute(rule_id="SHIP_001", scenario=scenario, flow_plan=flow)

    verdict = Oracle().evaluate(_rule_ship_001(), scenario, trace)

    assert trace.overall_status == "completed"
    assert verdict.result == "pass"
    assert verdict.violated_conditions == []

