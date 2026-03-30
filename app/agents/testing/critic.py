"""
Critic with LLM-first analysis and deterministic fallback.
"""

from __future__ import annotations

from app.config import settings
from app.llm.client import StructuredLLMClient
from app.schemas.feedback import CriticFeedback, CriticFinding
from app.schemas.rules import BusinessRule
from app.schemas.scenarios import Scenario
from app.schemas.validation import OracleVerdict


class Critic:
    def __init__(
        self,
        llm_client: StructuredLLMClient | None = None,
        model: str | None = None,
    ) -> None:
        self._llm_client = llm_client
        self._model = model or settings.critic_model

    async def analyze_for_rule(
        self,
        test_run_id: str,
        rule: BusinessRule,
        scenarios: list[Scenario],
        verdicts: list[OracleVerdict],
        iteration: int,
        max_iterations: int,
    ) -> CriticFeedback:
        if self._llm_client is not None:
            try:
                return await self._analyze_with_llm(
                    test_run_id=test_run_id,
                    rule=rule,
                    scenarios=scenarios,
                    verdicts=verdicts,
                    iteration=iteration,
                    max_iterations=max_iterations,
                )
            except Exception:
                pass
        return self.analyze(
            test_run_id=test_run_id,
            rule=rule,
            scenarios=scenarios,
            verdicts=verdicts,
            iteration=iteration,
            max_iterations=max_iterations,
        )

    def analyze(
        self,
        test_run_id: str,
        rule: BusinessRule,
        scenarios: list[Scenario],
        verdicts: list[OracleVerdict],
        iteration: int,
        max_iterations: int,
    ) -> CriticFeedback:
        findings: list[CriticFinding] = []
        scenario_by_id = {s.scenario_id: s for s in scenarios}

        expected_fail_caught = 0
        false_positive_count = 0
        inconclusive_count = 0
        for verdict in verdicts:
            scenario = scenario_by_id.get(verdict.scenario_id)
            if scenario is None:
                continue

            if verdict.result == "inconclusive":
                inconclusive_count += 1
            elif verdict.result == "fail" and scenario.expected_outcome == "fail":
                expected_fail_caught += 1
            elif verdict.result == "fail" and scenario.expected_outcome == "pass":
                false_positive_count += 1

        if expected_fail_caught:
            findings.append(
                CriticFinding(
                    type="rule_confidence_update",
                    target="business_memory",
                    detail="Rule correctly caught at least one invalid scenario.",
                    action="increase_confidence",
                    payload={"delta": 0.05, "rule_id": rule.rule_id},
                )
            )

        if false_positive_count:
            findings.append(
                CriticFinding(
                    type="false_positive",
                    target="business_memory",
                    detail="Rule failed one or more scenarios expected to pass.",
                    action="review_rule",
                    payload={"count": false_positive_count, "rule_id": rule.rule_id},
                )
            )

        if inconclusive_count:
            findings.append(
                CriticFinding(
                    type="flow_gap",
                    target="oracle",
                    detail="Some scenarios were inconclusive and need clearer evaluable conditions.",
                    action="tighten_condition_language",
                    payload={"count": inconclusive_count, "rule_id": rule.rule_id},
                )
            )

        has_edge = any(s.label == "edge" for s in scenarios)
        if not has_edge:
            findings.append(
                CriticFinding(
                    type="missing_edge_case",
                    target="scenario_generator",
                    detail="No edge scenario present for this rule.",
                    action="add_edge_case",
                    payload={"rule_id": rule.rule_id},
                )
            )

        summary = (
            f"Iteration {iteration}: "
            f"{expected_fail_caught} expected-fail catches, "
            f"{false_positive_count} false positives, "
            f"{inconclusive_count} inconclusive."
        )
        return CriticFeedback(
            test_run_id=test_run_id,
            rule_id=rule.rule_id,
            findings=findings,
            summary=summary,
            iterations_remaining=max(0, max_iterations - iteration),
        )

    async def _analyze_with_llm(
        self,
        test_run_id: str,
        rule: BusinessRule,
        scenarios: list[Scenario],
        verdicts: list[OracleVerdict],
        iteration: int,
        max_iterations: int,
    ) -> CriticFeedback:
        payload = await self._llm_client.generate_structured(
            model=self._model,
            system_prompt=_CRITIC_SYSTEM_PROMPT,
            user_prompt=_build_critic_prompt(rule, scenarios, verdicts, iteration, max_iterations),
            schema_name="critic_feedback",
            schema=_CRITIC_SCHEMA,
            temperature=0.1,
        )
        raw_findings = payload.get("findings")
        if not isinstance(raw_findings, list):
            raise ValueError("critic output missing findings list")

        findings: list[CriticFinding] = []
        for row in raw_findings:
            if not isinstance(row, dict):
                continue
            findings.append(CriticFinding.model_validate(row))

        summary = str(payload.get("summary", ""))
        if not summary:
            summary = f"Iteration {iteration}: critic generated structured findings."

        return CriticFeedback(
            test_run_id=test_run_id,
            rule_id=rule.rule_id,
            findings=findings,
            summary=summary,
            iterations_remaining=max(0, max_iterations - iteration),
        )


_CRITIC_SYSTEM_PROMPT = """You are a QA critic for API rule validation.
Return STRICT JSON only and keep findings actionable."""


_CRITIC_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "summary": {"type": "string"},
        "findings": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": True,
                "properties": {
                    "type": {
                        "type": "string",
                        "enum": [
                            "missing_edge_case",
                            "rule_confidence_update",
                            "flow_gap",
                            "false_positive",
                            "false_negative",
                            "rule_revision_suggestion",
                        ],
                    },
                    "target": {
                        "type": "string",
                        "enum": [
                            "scenario_generator",
                            "flow_planner",
                            "oracle",
                            "business_memory",
                        ],
                    },
                    "detail": {"type": "string"},
                    "action": {"type": "string"},
                    "payload": {"type": "object"},
                },
                "required": ["type", "target", "detail", "action"],
            },
        },
    },
    "required": ["summary", "findings"],
}


def _build_critic_prompt(
    rule: BusinessRule,
    scenarios: list[Scenario],
    verdicts: list[OracleVerdict],
    iteration: int,
    max_iterations: int,
) -> str:
    scenario_lines = [
        f"- {s.scenario_id}: label={s.label}, expected={s.expected_outcome}, inputs={s.inputs}"
        for s in scenarios
    ]
    verdict_lines = [
        (
            f"- {v.scenario_id}: result={v.result}, "
            f"violated={v.violated_conditions}, method={v.evaluation_method}"
        )
        for v in verdicts
    ]
    return (
        "Analyze API rule validation quality and propose actionable findings.\n"
        f"rule_id: {rule.rule_id}\n"
        f"rule_type: {rule.type}\n"
        f"description: {rule.description}\n"
        f"conditions: {rule.conditions}\n"
        f"iteration: {iteration}/{max_iterations}\n"
        "scenarios:\n"
        + "\n".join(scenario_lines)
        + "\nverdicts:\n"
        + "\n".join(verdict_lines)
        + "\nConstraints: keep findings specific and machine-actionable."
    )
