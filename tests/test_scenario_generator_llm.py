import pytest

from app.agents.testing.scenario_generator import ScenarioGenerator
from app.schemas.rules import BusinessRule


class _FakeStructuredClient:
    def __init__(self, payload: dict | None = None, raises: bool = False) -> None:
        self.payload = payload or {}
        self.raises = raises
        self.called = False

    async def generate_structured(
        self,
        *,
        model: str,
        system_prompt: str,
        user_prompt: str,
        schema_name: str,
        schema: dict,
        temperature: float = 0.0,
    ) -> dict:
        self.called = True
        if self.raises:
            raise RuntimeError("llm failure")
        return self.payload


def _rule() -> BusinessRule:
    return BusinessRule(
        rule_id="SHIP_001",
        type="constraint",
        description="Shipment weight must not exceed assigned vehicle capacity",
        entities=["Shipment", "Vehicle"],
        conditions=["scenario.shipment_weight <= entities.vehicle.capacity"],
        expected_effect=["dispatch should be rejected if weight exceeds capacity"],
        invalid_scenarios=["shipment_weight > vehicle_capacity should fail dispatch"],
        status="approved",
    )


@pytest.mark.asyncio
async def test_scenario_generator_prefers_llm_output() -> None:
    client = _FakeStructuredClient(
        payload={
            "scenarios": [
                {
                    "scenario_id": "SHIP_001_SCN_LLM_001",
                    "label": "invalid",
                    "inputs": {
                        "shipment_weight": 1500,
                        "origin": "BLR",
                        "destination": "DEL",
                        "vehicle_id": "VH_001",
                    },
                    "expected_outcome": "fail",
                    "rationale": "llm-generated invalid case",
                }
            ]
        }
    )
    generator = ScenarioGenerator(llm_client=client)
    scenarios = await generator.generate_for_rule(_rule())

    assert client.called
    assert len(scenarios) == 1
    assert scenarios[0].scenario_id == "SHIP_001_SCN_LLM_001"
    assert scenarios[0].label == "invalid"


@pytest.mark.asyncio
async def test_scenario_generator_falls_back_when_llm_fails() -> None:
    client = _FakeStructuredClient(raises=True)
    generator = ScenarioGenerator(llm_client=client)
    scenarios = await generator.generate_for_rule(_rule())

    assert client.called
    assert len(scenarios) >= 1
    assert any(s.label == "invalid" for s in scenarios)

