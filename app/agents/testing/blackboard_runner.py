"""
Task-driven deterministic runner built on Blackboard task posting/claiming.
"""

from __future__ import annotations

from uuid import uuid4

from app.agents.testing.executor import Executor
from app.agents.testing.flow_planner import FlowPlanner
from app.agents.testing.oracle import Oracle
from app.agents.testing.scenario_generator import ScenarioGenerator
from app.memory.blackboard import Blackboard
from app.memory.exec_log import ExecutionLog
from app.memory.rule_store import RuleStore
from app.schemas.execution import ExecutionTrace
from app.schemas.scenarios import FlowPlan, Scenario
from app.schemas.validation import OracleVerdict


class BlackboardRuleRunner:
    def __init__(
        self,
        rule_store: RuleStore,
        blackboard: Blackboard,
        scenario_generator: ScenarioGenerator | None = None,
        flow_planner: FlowPlanner | None = None,
        executor: Executor | None = None,
        oracle: Oracle | None = None,
        execution_log: ExecutionLog | None = None,
    ) -> None:
        self._rule_store = rule_store
        self._blackboard = blackboard
        self._scenario_generator = scenario_generator or ScenarioGenerator()
        self._flow_planner = flow_planner or FlowPlanner()
        self._executor = executor or Executor()
        self._oracle = oracle or Oracle()
        self._execution_log = execution_log or ExecutionLog()
        self._results: list[dict] = []

    async def run_active_rules(self, entity: str | None = None, max_cycles: int = 1000) -> dict:
        rules = await self._rule_store.get_active_rules(entity=entity)
        for rule in rules:
            await self._blackboard.post_task(
                task_id=_task_id("test_rule", rule.rule_id),
                task_type="test_rule",
                data={"rule_id": rule.rule_id},
            )

        await self.run_until_idle(max_cycles=max_cycles)
        dead_tasks = await self._blackboard.get_dead_tasks()
        return _summarize(self._results, len(rules), dead_tasks=dead_tasks)

    async def run_until_idle(self, max_cycles: int = 1000) -> None:
        for _ in range(max_cycles):
            progressed = False
            progressed |= await self._run_worker(
                task_type="test_rule",
                agent_id="scenario_generator",
                handler=self._handle_test_rule,
            )
            progressed |= await self._run_worker(
                task_type="generate_flow",
                agent_id="flow_planner",
                handler=self._handle_generate_flow,
            )
            progressed |= await self._run_worker(
                task_type="execute",
                agent_id="executor",
                handler=self._handle_execute,
            )
            progressed |= await self._run_worker(
                task_type="validate",
                agent_id="oracle",
                handler=self._handle_validate,
            )
            if not progressed:
                if not await self._blackboard.get_pending_tasks():
                    break

    async def _run_worker(self, task_type: str, agent_id: str, handler) -> bool:
        task = await self._blackboard.claim_task(task_type=task_type, agent_id=agent_id)
        if not task:
            return False

        task_id = task["task_id"]
        await self._blackboard.start_task(task_id)
        try:
            await handler(task)
            await self._blackboard.complete_task(task_id)
        except Exception as exc:
            await self._blackboard.fail_task(task_id, str(exc))
        return True

    async def _handle_test_rule(self, task: dict) -> None:
        rule_id = task["data"]["rule_id"]
        rule = await self._rule_store.get_rule(rule_id=rule_id)
        if rule is None:
            raise ValueError(f"rule not found: {rule_id}")

        scenarios = await self._scenario_generator.generate_for_rule(rule)
        for scenario in scenarios:
            await self._blackboard.post_task(
                task_id=_task_id("generate_flow", f"{rule_id}:{scenario.scenario_id}"),
                task_type="generate_flow",
                data={
                    "rule_id": rule_id,
                    "scenario": scenario.model_dump(mode="json"),
                },
            )

    async def _handle_generate_flow(self, task: dict) -> None:
        rule_id = task["data"]["rule_id"]
        scenario = Scenario.model_validate(task["data"]["scenario"])
        rule = await self._rule_store.get_rule(rule_id=rule_id)
        if rule is None:
            raise ValueError(f"rule not found: {rule_id}")

        flow = self._flow_planner.generate(rule=rule, scenario=scenario)
        await self._blackboard.post_task(
            task_id=_task_id("execute", f"{rule_id}:{scenario.scenario_id}"),
            task_type="execute",
            data={
                "rule_id": rule_id,
                "scenario": scenario.model_dump(mode="json"),
                "flow_plan": flow.model_dump(mode="json"),
            },
        )

    async def _handle_execute(self, task: dict) -> None:
        rule_id = task["data"]["rule_id"]
        scenario = Scenario.model_validate(task["data"]["scenario"])
        flow_plan = FlowPlan.model_validate(task["data"]["flow_plan"])
        trace = await self._executor.execute(
            rule_id=rule_id,
            scenario=scenario,
            flow_plan=flow_plan,
        )
        self._execution_log.append(trace)
        await self._blackboard.post_task(
            task_id=_task_id("validate", f"{rule_id}:{scenario.scenario_id}"),
            task_type="validate",
            data={
                "rule_id": rule_id,
                "scenario": scenario.model_dump(mode="json"),
                "trace": trace.model_dump(mode="json"),
            },
        )

    async def _handle_validate(self, task: dict) -> None:
        rule_id = task["data"]["rule_id"]
        scenario = Scenario.model_validate(task["data"]["scenario"])
        trace = ExecutionTrace.model_validate(task["data"]["trace"])
        rule = await self._rule_store.get_rule(rule_id=rule_id)
        if rule is None:
            raise ValueError(f"rule not found: {rule_id}")

        verdict = self._oracle.evaluate(rule=rule, scenario=scenario, trace=trace)
        self._results.append(
            _serialize_result(
                rule_id=rule_id,
                scenario_id=scenario.scenario_id,
                flow_id=trace.flow_id,
                trace=trace,
                verdict=verdict,
            )
        )


def _task_id(prefix: str, tail: str) -> str:
    return f"{prefix}:{tail}:{uuid4().hex[:8]}"


def _serialize_result(
    rule_id: str,
    scenario_id: str,
    flow_id: str,
    trace: ExecutionTrace,
    verdict: OracleVerdict,
) -> dict:
    return {
        "rule_id": rule_id,
        "scenario_id": scenario_id,
        "flow_id": flow_id,
        "trace_id": trace.trace_id,
        "trace": {
            "trace_id": trace.trace_id,
            "overall_status": trace.overall_status,
            "record_count": len(trace.records),
            "final_status_code": trace.records[-1].status_code if trace.records else None,
        },
        "verdict": verdict.model_dump(mode="json"),
    }


def _summarize(results: list[dict], total_rules: int, dead_tasks: list[dict]) -> dict:
    passed = [r for r in results if r["verdict"]["result"] == "pass"]
    failed = [r for r in results if r["verdict"]["result"] == "fail"]
    inconclusive = [r for r in results if r["verdict"]["result"] == "inconclusive"]
    return {
        "mode": "blackboard",
        "total_rules": total_rules,
        "total_scenarios": len(results),
        "passed": len(passed),
        "failed": len(failed),
        "inconclusive": len(inconclusive),
        "dead_tasks": len(dead_tasks),
        "dead_task_details": dead_tasks,
        "results": results,
    }
