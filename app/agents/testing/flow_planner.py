"""
Deterministic flow planner with output validation.

For V1:
- Constraint and postcondition rules use create -> assign -> dispatch.
- Precondition invalid scenarios can skip assign intentionally.
- Flow plan output is validated against known routes and state dependencies.
"""

from __future__ import annotations

from collections.abc import Iterable

from app.schemas.rules import BusinessRule
from app.schemas.scenarios import FlowPlan, FlowStep, Scenario


KNOWN_ROUTES = {
    "/api/v1/shipments",
    "/api/v1/shipments/{shipment_id}/assign",
    "/api/v1/shipments/{shipment_id}/dispatch",
}


class FlowPlanner:
    def __init__(self, known_routes: Iterable[str] | None = None) -> None:
        self._known_routes = set(known_routes) if known_routes is not None else set(KNOWN_ROUTES)

    def generate(self, rule: BusinessRule, scenario: Scenario) -> FlowPlan:
        steps = _build_steps(rule, scenario)
        plan = FlowPlan(
            flow_id=f"{rule.rule_id}_{scenario.scenario_id}_FLOW",
            rule_id=rule.rule_id,
            name=f"{rule.rule_id} deterministic flow",
            steps=steps,
            description="Deterministic V1 planner output",
        )
        issues = self.validate_flow_plan(plan, self._known_routes)
        if issues:
            raise ValueError("; ".join(issues))
        return plan

    @staticmethod
    def validate_flow_plan(plan: FlowPlan, known_routes: Iterable[str]) -> list[str]:
        issues: list[str] = []
        route_set = set(known_routes)

        extracted_state: set[str] = set()
        for step in sorted(plan.steps, key=lambda s: s.step_number):
            if step.endpoint not in route_set:
                issues.append(f"unknown endpoint in step {step.step_number}: {step.endpoint}")

            for source in _iter_state_references(step.path_params) | _iter_state_references(step.payload_map):
                if source not in extracted_state:
                    issues.append(
                        f"missing state dependency '{source}' in step {step.step_number}"
                    )

            for target, pointer in step.extract.items():
                if isinstance(pointer, str) and pointer.startswith("$.response."):
                    extracted_state.add(target)
                elif pointer == "$.response":
                    extracted_state.add(target)

            if not step.expected_status:
                issues.append(f"empty expected_status in step {step.step_number}")

        return issues


def _build_steps(rule: BusinessRule, scenario: Scenario) -> list[FlowStep]:
    should_assign = _should_assign(rule, scenario)
    dispatch_expected = [200] if scenario.expected_outcome == "pass" else [400]

    steps: list[FlowStep] = [
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
        )
    ]

    if should_assign:
        steps.append(
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
            )
        )
        dispatch_step_number = 3
    else:
        dispatch_step_number = 2

    steps.append(
        FlowStep(
            step_number=dispatch_step_number,
            endpoint="/api/v1/shipments/{shipment_id}/dispatch",
            method="POST",
            path_params={"shipment_id": "$state.shipment_id"},
            payload_map={},
            extract={
                "status": "$.response.status",
                "dispatched_at": "$.response.dispatched_at",
            },
            expected_status=dispatch_expected,
        )
    )

    return steps


def _should_assign(rule: BusinessRule, scenario: Scenario) -> bool:
    if rule.type != "precondition":
        return True
    return bool(scenario.inputs.get("assign_before_dispatch", True))


def _iter_state_references(template: dict) -> set[str]:
    refs: set[str] = set()
    for value in template.values():
        if isinstance(value, str) and value.startswith("$state."):
            refs.add(value.removeprefix("$state.").split(".")[0])
    return refs

