from app.agents.testing.scenario_generator import ScenarioGenerator
from app.schemas.rules import BusinessRule


def test_scenario_generator_for_ship_001_includes_invalid_case() -> None:
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
    scenarios = ScenarioGenerator().generate(rule)
    invalid = [s for s in scenarios if s.label == "invalid"]
    assert invalid
    assert invalid[0].expected_outcome == "fail"
    assert invalid[0].inputs["shipment_weight"] > 1000

