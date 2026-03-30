"""
Deterministic Oracle for Phase 1.

Evaluation rule:
1) Evaluate every condition using the four-pattern parser.
2) If any condition is unknown, return inconclusive (LLM path not implemented yet).
3) If conditions are violated and API accepted the request (2xx), return fail.
4) If conditions are violated and API rejected (non-2xx), return pass.
5) If all conditions hold and API accepted, return pass.
6) If all conditions hold and API rejected, return fail.
"""

from __future__ import annotations

import asyncio
import inspect
import logging
from typing import Any

from app.eval.condition_parser import evaluate
from app.eval.resolver import build_eval_context
from app.runtime.events import make_event
from app.schemas.execution import ExecutionTrace
from app.schemas.rules import BusinessRule
from app.schemas.scenarios import Scenario
from app.schemas.validation import OracleVerdict

logger = logging.getLogger(__name__)


class Oracle:
    def __init__(self, event_emitter: Any | None = None) -> None:
        self._event_emitter = event_emitter

    def evaluate(self, rule: BusinessRule, scenario: Scenario, trace: ExecutionTrace) -> OracleVerdict:
        if not trace.records:
            verdict = OracleVerdict(
                trace_id=trace.trace_id,
                rule_id=rule.rule_id,
                scenario_id=scenario.scenario_id,
                result="inconclusive",
                violated_conditions=[],
                evaluation_method="deterministic",
                reproducible=True,
                evidence={"reason": "no execution records"},
                confidence=0.0,
            )
            self._emit_verdict(verdict)
            return verdict

        last_record = trace.records[-1]
        last_response = last_record.response_body if isinstance(last_record.response_body, dict) else {}
        context = build_eval_context(trace.final_state, scenario, last_response)

        violated: list[str] = []
        unresolved: list[str] = []
        condition_results: dict[str, bool | None] = {}
        for condition in rule.conditions:
            result = evaluate(condition, context)
            condition_results[condition] = result
            if result is None:
                unresolved.append(condition)
            elif result is False:
                violated.append(condition)

        if unresolved:
            verdict = OracleVerdict(
                trace_id=trace.trace_id,
                rule_id=rule.rule_id,
                scenario_id=scenario.scenario_id,
                result="inconclusive",
                violated_conditions=violated,
                evaluation_method="llm_assisted",
                reproducible=False,
                evidence={
                    "reason": "condition requires llm fallback",
                    "unresolved_conditions": unresolved,
                    "condition_results": condition_results,
                    "final_status_code": last_record.status_code,
                },
                confidence=0.0,
            )
            self._emit_verdict(verdict)
            return verdict

        api_accepted = 200 <= last_record.status_code < 300
        if violated and api_accepted:
            verdict_result = "fail"
        elif violated and not api_accepted:
            verdict_result = "pass"
        elif not violated and api_accepted:
            verdict_result = "pass"
        else:
            verdict_result = "fail"

        verdict = OracleVerdict(
            trace_id=trace.trace_id,
            rule_id=rule.rule_id,
            scenario_id=scenario.scenario_id,
            result=verdict_result,  # type: ignore[arg-type]
            violated_conditions=violated,
            evaluation_method="deterministic",
            reproducible=True,
            evidence={
                "condition_results": condition_results,
                "final_status_code": last_record.status_code,
                "api_accepted": api_accepted,
                "overall_status": trace.overall_status,
            },
            confidence=1.0,
        )
        self._emit_verdict(verdict)
        return verdict

    def _emit_verdict(self, verdict: OracleVerdict) -> None:
        self._emit(
            make_event(
                "VERDICT",
                {
                    "trace_id": verdict.trace_id,
                    "rule_id": verdict.rule_id,
                    "scenario_id": verdict.scenario_id,
                    "result": verdict.result,
                    "violated_conditions": verdict.violated_conditions,
                },
            )
        )

    def _emit(self, event: dict[str, Any]) -> None:
        if self._event_emitter is None:
            return
        try:
            result = self._event_emitter(event)
            if inspect.isawaitable(result):
                try:
                    asyncio.get_running_loop().create_task(result)
                except RuntimeError:
                    pass
        except Exception:
            logger.exception("oracle event emission failed")
