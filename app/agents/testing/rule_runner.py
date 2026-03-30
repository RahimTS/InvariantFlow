"""
End-to-end deterministic runner:
approved RuleStore rules -> scenarios -> flow plans -> execute -> oracle.
"""

from __future__ import annotations

import inspect

from app.agents.testing.executor import Executor
from app.agents.testing.flow_planner import FlowPlanner
from app.agents.testing.oracle import Oracle
from app.agents.testing.scenario_generator import ScenarioGenerator
from app.memory.exec_log import ExecutionLog
from app.memory.rule_store import RuleStore
from app.schemas.rules import BusinessRule
from app.schemas.validation import OracleVerdict


class RuleTestRunner:
    def __init__(
        self,
        rule_store: RuleStore,
        scenario_generator: ScenarioGenerator | None = None,
        flow_planner: FlowPlanner | None = None,
        executor: Executor | None = None,
        oracle: Oracle | None = None,
        execution_log: ExecutionLog | None = None,
    ) -> None:
        self._rule_store = rule_store
        self._scenario_generator = scenario_generator or ScenarioGenerator()
        self._flow_planner = flow_planner or FlowPlanner()
        self._executor = executor or Executor()
        self._oracle = oracle or Oracle()
        self._execution_log = execution_log or ExecutionLog()

    async def run_active_rules(self, entity: str | None = None, run_id: str | None = None) -> dict:
        rules = await self._rule_store.get_active_rules(entity=entity)
        all_results: list[dict] = []
        for rule in rules:
            results = await self.run_rule(rule, run_id=run_id)
            all_results.extend(results)

        failed = [r for r in all_results if r["verdict"].result == "fail"]
        inconclusive = [r for r in all_results if r["verdict"].result == "inconclusive"]
        passed = [r for r in all_results if r["verdict"].result == "pass"]

        return {
            "total_rules": len(rules),
            "total_scenarios": len(all_results),
            "passed": len(passed),
            "failed": len(failed),
            "inconclusive": len(inconclusive),
            "results": all_results,
        }

    async def run_rule(self, rule: BusinessRule, run_id: str | None = None) -> list[dict]:
        scenarios = await self._scenario_generator.generate_for_rule(rule)
        rule_results: list[dict] = []

        for scenario in scenarios:
            flow_plan = self._flow_planner.generate(rule, scenario)
            trace = await self._executor.execute(
                rule_id=rule.rule_id,
                scenario=scenario,
                flow_plan=flow_plan,
                run_id=run_id,
            )
            maybe = self._execution_log.append(trace)
            if inspect.isawaitable(maybe):
                await maybe
            verdict = self._oracle.evaluate(rule=rule, scenario=scenario, trace=trace)

            rule_results.append(
                {
                    "rule_id": rule.rule_id,
                    "scenario_id": scenario.scenario_id,
                    "flow_id": flow_plan.flow_id,
                    "trace_id": trace.trace_id,
                    "trace": trace,
                    "verdict": verdict,
                }
            )

        return rule_results


def summarize_verdicts(results: list[dict]) -> dict[str, int]:
    counts = {"pass": 0, "fail": 0, "inconclusive": 0}
    for item in results:
        verdict: OracleVerdict = item["verdict"]
        counts[verdict.result] += 1
    return counts
