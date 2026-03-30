"""
Rule Validator agent for ingestion chain.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from app.eval.condition_parser import can_evaluate
from app.schemas.rules import BusinessRule, ValidationVerdict


KNOWN_ENTITIES = {"Shipment", "Vehicle"}


@dataclass
class RuleValidationResult:
    rule: BusinessRule
    verdict: ValidationVerdict
    machine_evaluable_ratio: float = 0.0
    flags: dict = field(default_factory=dict)


class RuleValidator:
    def validate(self, rule: BusinessRule) -> RuleValidationResult:
        issues: list[dict] = []
        checks_passed: list[str] = []
        checks_failed: list[str] = []

        if rule.description.strip():
            checks_passed.append("description_present")
        else:
            checks_failed.append("description_present")
            issues.append({"field": "description", "issue": "empty"})

        if rule.conditions:
            checks_passed.append("conditions_present")
        else:
            checks_failed.append("conditions_present")
            issues.append({"field": "conditions", "issue": "empty"})

        unknown_entities = [e for e in rule.entities if e not in KNOWN_ENTITIES]
        if unknown_entities:
            checks_failed.append("known_entities")
            issues.append({"field": "entities", "issue": "unknown_entities", "value": unknown_entities})
        else:
            checks_passed.append("known_entities")

        if rule.expected_effect:
            checks_passed.append("expected_effect_present")
        else:
            checks_failed.append("expected_effect_present")
            issues.append({"field": "expected_effect", "issue": "empty"})

        if rule.invalid_scenarios:
            checks_passed.append("invalid_scenarios_present")
        else:
            checks_failed.append("invalid_scenarios_present")
            issues.append({"field": "invalid_scenarios", "issue": "empty"})

        evaluable = [can_evaluate(c) for c in rule.conditions]
        if evaluable:
            ratio = sum(1 for x in evaluable if x) / len(evaluable)
        else:
            ratio = 0.0
        requires_llm = any(not x for x in evaluable) if evaluable else True
        rule.requires_llm = requires_llm
        if requires_llm:
            issues.append(
                {
                    "field": "conditions",
                    "issue": "some_conditions_require_llm",
                    "evaluable_ratio": round(ratio, 3),
                }
            )

        if checks_failed:
            verdict_type = "needs_revision"
        else:
            verdict_type = "approved"

        verdict = ValidationVerdict(
            rule_id=rule.rule_id,
            verdict=verdict_type,  # type: ignore[arg-type]
            issues=issues,
            checks_passed=checks_passed,
            checks_failed=checks_failed,
        )

        return RuleValidationResult(
            rule=rule,
            verdict=verdict,
            machine_evaluable_ratio=ratio,
            flags={"requires_llm": requires_llm},
        )

