"""
Scenario generator with LLM-first mode and deterministic fallback.
"""

from __future__ import annotations

from app.config import settings
from app.llm.client import StructuredLLMClient
from app.schemas.rules import BusinessRule
from app.schemas.scenarios import Scenario


class ScenarioGenerator:
    def __init__(
        self,
        max_scenarios: int | None = None,
        llm_client: StructuredLLMClient | None = None,
        model: str | None = None,
    ) -> None:
        self._max_scenarios = max_scenarios or settings.max_scenarios_per_rule
        self._llm_client = llm_client
        self._model = model or settings.scenario_generator_model

    async def generate_for_rule(self, rule: BusinessRule) -> list[Scenario]:
        if self._llm_client is not None:
            try:
                scenarios = await self._generate_with_llm(rule)
                if scenarios:
                    return scenarios[: self._max_scenarios]
            except Exception:
                pass
        return self.generate(rule)

    def generate(self, rule: BusinessRule) -> list[Scenario]:
        scenarios = self._for_known_rule(rule)
        if not scenarios:
            scenarios = [
                Scenario(
                    scenario_id=f"{rule.rule_id}_SCN_001",
                    rule_id=rule.rule_id,
                    label="valid",
                    inputs={},
                    expected_outcome="pass",
                    rationale="fallback scenario for generic rule shape",
                )
            ]
        return scenarios[: self._max_scenarios]

    async def _generate_with_llm(self, rule: BusinessRule) -> list[Scenario]:
        payload = await self._llm_client.generate_structured(
            model=self._model,
            system_prompt=_SCENARIO_SYSTEM_PROMPT,
            user_prompt=_build_scenario_prompt(rule, self._max_scenarios),
            schema_name="scenario_generation",
            schema=_SCENARIO_SCHEMA,
            temperature=0.2,
        )
        raw_scenarios = payload.get("scenarios")
        if not isinstance(raw_scenarios, list):
            raise ValueError("LLM structured output missing 'scenarios' list")

        validated: list[Scenario] = []
        for index, row in enumerate(raw_scenarios):
            if not isinstance(row, dict):
                continue
            row = dict(row)
            row["rule_id"] = rule.rule_id
            if "scenario_id" not in row or not row["scenario_id"]:
                row["scenario_id"] = f"{rule.rule_id}_SCN_{index + 1:03d}"
            validated.append(Scenario.model_validate(row))
        return validated[: self._max_scenarios]

    def _for_known_rule(self, rule: BusinessRule) -> list[Scenario]:
        if rule.rule_id == "SHIP_001":
            return _ship_001_scenarios(rule.rule_id)
        if rule.rule_id == "SHIP_002":
            return _ship_002_scenarios(rule.rule_id)
        if rule.rule_id == "SHIP_003":
            return _ship_003_scenarios(rule.rule_id)
        return []


def _ship_001_scenarios(rule_id: str) -> list[Scenario]:
    return [
        Scenario(
            scenario_id=f"{rule_id}_SCN_001",
            rule_id=rule_id,
            label="valid",
            inputs={
                "shipment_weight": 800,
                "origin": "BLR",
                "destination": "DEL",
                "vehicle_id": "VH_001",
            },
            expected_outcome="pass",
            rationale="well below capacity should dispatch",
        ),
        Scenario(
            scenario_id=f"{rule_id}_SCN_002",
            rule_id=rule_id,
            label="boundary",
            inputs={
                "shipment_weight": 1000,
                "origin": "BLR",
                "destination": "DEL",
                "vehicle_id": "VH_001",
            },
            expected_outcome="pass",
            rationale="exact capacity boundary should dispatch",
        ),
        Scenario(
            scenario_id=f"{rule_id}_SCN_003",
            rule_id=rule_id,
            label="invalid",
            inputs={
                "shipment_weight": 1200,
                "origin": "BLR",
                "destination": "DEL",
                "vehicle_id": "VH_001",
            },
            expected_outcome="fail",
            rationale="overweight shipment should be rejected at dispatch",
        ),
    ]


def _ship_002_scenarios(rule_id: str) -> list[Scenario]:
    return [
        Scenario(
            scenario_id=f"{rule_id}_SCN_001",
            rule_id=rule_id,
            label="valid",
            inputs={
                "shipment_weight": 500,
                "origin": "BLR",
                "destination": "DEL",
                "vehicle_id": "VH_001",
                "assign_before_dispatch": True,
            },
            expected_outcome="pass",
            rationale="assigned shipment dispatch should succeed",
        ),
        Scenario(
            scenario_id=f"{rule_id}_SCN_002",
            rule_id=rule_id,
            label="invalid",
            inputs={
                "shipment_weight": 500,
                "origin": "BLR",
                "destination": "DEL",
                "vehicle_id": "VH_001",
                "assign_before_dispatch": False,
            },
            expected_outcome="fail",
            rationale="dispatch without assignment should fail",
        ),
    ]


def _ship_003_scenarios(rule_id: str) -> list[Scenario]:
    return [
        Scenario(
            scenario_id=f"{rule_id}_SCN_001",
            rule_id=rule_id,
            label="valid",
            inputs={
                "shipment_weight": 700,
                "origin": "BLR",
                "destination": "DEL",
                "vehicle_id": "VH_001",
                "assign_before_dispatch": True,
            },
            expected_outcome="pass",
            rationale="successful dispatch should set status and dispatched_at",
        )
    ]


_SCENARIO_SYSTEM_PROMPT = """You generate API test scenarios from business rules.
Output STRICT JSON matching the schema. Do not include prose."""


_SCENARIO_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "scenarios": {
            "type": "array",
            "minItems": 1,
            "items": {
                "type": "object",
                "additionalProperties": True,
                "properties": {
                    "scenario_id": {"type": "string"},
                    "label": {"type": "string", "enum": ["valid", "boundary", "invalid", "edge"]},
                    "inputs": {"type": "object"},
                    "expected_outcome": {"type": "string", "enum": ["pass", "fail"]},
                    "rationale": {"type": "string"},
                },
                "required": ["label", "inputs", "expected_outcome", "rationale"],
            },
        }
    },
    "required": ["scenarios"],
}


def _build_scenario_prompt(rule: BusinessRule, max_scenarios: int) -> str:
    return (
        "Generate API test scenarios for this rule.\n"
        f"rule_id: {rule.rule_id}\n"
        f"type: {rule.type}\n"
        f"description: {rule.description}\n"
        f"entities: {rule.entities}\n"
        f"conditions: {rule.conditions}\n"
        f"expected_effect: {rule.expected_effect}\n"
        f"invalid_scenarios: {rule.invalid_scenarios}\n"
        f"edge_cases: {rule.edge_cases}\n"
        f"constraints: return at most {max_scenarios} scenarios; include a mix of valid/boundary/invalid when relevant."
    )
