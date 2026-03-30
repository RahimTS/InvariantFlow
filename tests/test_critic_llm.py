import pytest

from app.agents.testing.critic import Critic
from app.schemas.rules import BusinessRule
from app.schemas.scenarios import Scenario
from app.schemas.validation import OracleVerdict


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


def _scenarios() -> list[Scenario]:
    return [
        Scenario(
            scenario_id="SHIP_001_SCN_001",
            rule_id="SHIP_001",
            label="valid",
            inputs={"shipment_weight": 800},
            expected_outcome="pass",
            rationale="valid case",
        )
    ]


def _verdicts() -> list[OracleVerdict]:
    return [
        OracleVerdict(
            trace_id="t1",
            rule_id="SHIP_001",
            scenario_id="SHIP_001_SCN_001",
            result="pass",
            violated_conditions=[],
            evaluation_method="deterministic",
            reproducible=True,
            evidence={},
            confidence=1.0,
        )
    ]


@pytest.mark.asyncio
async def test_critic_uses_llm_structured_feedback() -> None:
    client = _FakeStructuredClient(
        payload={
            "summary": "LLM critic summary",
            "findings": [
                {
                    "type": "missing_edge_case",
                    "target": "scenario_generator",
                    "detail": "Need edge coverage",
                    "action": "add_edge_case",
                    "payload": {"rule_id": "SHIP_001"},
                }
            ],
        }
    )
    critic = Critic(llm_client=client)
    feedback = await critic.analyze_for_rule(
        test_run_id="run_1",
        rule=_rule(),
        scenarios=_scenarios(),
        verdicts=_verdicts(),
        iteration=1,
        max_iterations=3,
    )

    assert client.called
    assert feedback.summary == "LLM critic summary"
    assert len(feedback.findings) == 1
    assert feedback.findings[0].type == "missing_edge_case"


@pytest.mark.asyncio
async def test_critic_falls_back_to_deterministic_when_llm_fails() -> None:
    client = _FakeStructuredClient(raises=True)
    critic = Critic(llm_client=client)
    feedback = await critic.analyze_for_rule(
        test_run_id="run_1",
        rule=_rule(),
        scenarios=_scenarios(),
        verdicts=_verdicts(),
        iteration=1,
        max_iterations=3,
    )

    assert client.called
    assert feedback.rule_id == "SHIP_001"
    assert any(f.type == "missing_edge_case" for f in feedback.findings)

