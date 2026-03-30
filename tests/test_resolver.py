from app.eval.resolver import build_eval_context, resolve
from app.schemas.scenarios import Scenario


def test_resolve_returns_value_for_valid_path() -> None:
    context = {"entities": {"shipment": {"status": "ASSIGNED"}}}
    assert resolve("entities.shipment.status", context) == "ASSIGNED"


def test_resolve_returns_none_for_missing_path() -> None:
    context = {"entities": {"shipment": {"status": "ASSIGNED"}}}
    assert resolve("entities.vehicle.capacity", context) is None


def test_build_eval_context_shapes_entities_and_includes_sections() -> None:
    scenario = Scenario(
        scenario_id="S1",
        rule_id="R1",
        label="valid",
        inputs={"shipment_weight": 100},
        expected_outcome="pass",
        rationale="base case",
    )
    state_snapshot = {
        "SHIP_0001": {"id": "SHIP_0001", "type": "Shipment", "status": "CREATED"},
        "VH_001": {"id": "VH_001", "type": "Vehicle", "capacity": 1000},
    }
    response = {"status": "ASSIGNED"}

    context = build_eval_context(state_snapshot, scenario, response)

    assert context["scenario"]["shipment_weight"] == 100
    assert context["response"]["status"] == "ASSIGNED"
    assert context["entities"]["shipment"]["id"] == "SHIP_0001"
    assert context["entities"]["vehicle"]["capacity"] == 1000

