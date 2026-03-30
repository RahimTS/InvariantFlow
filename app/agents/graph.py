"""
LangGraph wiring for Phase 2 testing loop:
Scenario Generator -> Flow Planner/Executor/Oracle -> Critic -> optional refine.
"""

from __future__ import annotations

from typing import TypedDict, Any
from uuid import uuid4

from langgraph.graph import END, START, StateGraph

from app.agents.testing.critic import Critic
from app.agents.testing.executor import Executor
from app.agents.testing.flow_planner import FlowPlanner
from app.agents.testing.oracle import Oracle
from app.agents.testing.scenario_generator import ScenarioGenerator
from app.memory.exec_log import ExecutionLog
from app.memory.rule_store import RuleStore
from app.schemas.feedback import CriticFeedback
from app.schemas.rules import BusinessRule
from app.schemas.scenarios import Scenario
from app.schemas.validation import OracleVerdict


class RuleLoopState(TypedDict):
    run_id: str
    rule: BusinessRule
    iteration: int
    max_iterations: int
    scenarios: list[Scenario]
    pending_scenarios: list[Scenario]
    processed_scenario_ids: list[str]
    results: list[dict[str, Any]]
    last_iteration_verdicts: list[OracleVerdict]
    feedback_history: list[CriticFeedback]
    last_feedback: CriticFeedback | None


class LangGraphRuleRunner:
    def __init__(
        self,
        rule_store: RuleStore,
        scenario_generator: ScenarioGenerator | None = None,
        flow_planner: FlowPlanner | None = None,
        executor: Executor | None = None,
        oracle: Oracle | None = None,
        critic: Critic | None = None,
        execution_log: ExecutionLog | None = None,
    ) -> None:
        self._rule_store = rule_store
        self._scenario_generator = scenario_generator or ScenarioGenerator()
        self._flow_planner = flow_planner or FlowPlanner()
        self._executor = executor or Executor()
        self._oracle = oracle or Oracle()
        self._critic = critic or Critic()
        self._execution_log = execution_log or ExecutionLog()
        self._graph = self._build_graph()

    async def run_active_rules(self, entity: str | None = None, max_iterations: int = 3) -> dict:
        rules = await self._rule_store.get_active_rules(entity=entity)
        combined_results: list[dict] = []
        combined_feedback: list[dict] = []

        for rule in rules:
            run_result = await self.run_rule(rule, max_iterations=max_iterations)
            combined_results.extend(run_result["results"])
            combined_feedback.extend(run_result["feedback"])

        passed = [r for r in combined_results if r["verdict"]["result"] == "pass"]
        failed = [r for r in combined_results if r["verdict"]["result"] == "fail"]
        inconclusive = [r for r in combined_results if r["verdict"]["result"] == "inconclusive"]

        return {
            "mode": "langgraph",
            "total_rules": len(rules),
            "total_scenarios": len(combined_results),
            "passed": len(passed),
            "failed": len(failed),
            "inconclusive": len(inconclusive),
            "results": combined_results,
            "feedback": combined_feedback,
        }

    async def run_rule(self, rule: BusinessRule, max_iterations: int = 3) -> dict:
        initial: RuleLoopState = {
            "run_id": f"lg_{uuid4().hex}",
            "rule": rule,
            "iteration": 0,
            "max_iterations": max_iterations,
            "scenarios": [],
            "pending_scenarios": [],
            "processed_scenario_ids": [],
            "results": [],
            "last_iteration_verdicts": [],
            "feedback_history": [],
            "last_feedback": None,
        }
        final = await self._graph.ainvoke(initial)
        serialized_results = [_serialize_result(item) for item in final["results"]]
        serialized_feedback = [fb.model_dump(mode="json") for fb in final["feedback_history"]]
        return {
            "rule_id": rule.rule_id,
            "iterations": final["iteration"],
            "results": serialized_results,
            "feedback": serialized_feedback,
        }

    def _build_graph(self):
        graph = StateGraph(RuleLoopState)
        graph.add_node("scenario_generator", self._node_scenario_generator)
        graph.add_node("execute_validate", self._node_execute_validate)
        graph.add_node("critic", self._node_critic)

        graph.add_edge(START, "scenario_generator")
        graph.add_edge("scenario_generator", "execute_validate")
        graph.add_edge("execute_validate", "critic")
        graph.add_conditional_edges("critic", self._route_after_critic, {"continue": "scenario_generator", "end": END})
        return graph.compile()

    async def _node_scenario_generator(self, state: RuleLoopState) -> dict:
        scenarios = list(state["scenarios"])
        if state["iteration"] == 0 and not scenarios:
            scenarios = await self._scenario_generator.generate_for_rule(state["rule"])
        else:
            maybe_edge = _edge_scenario_for_rule(state["rule"], scenarios)
            if maybe_edge is not None:
                scenarios.append(maybe_edge)

        processed = set(state["processed_scenario_ids"])
        pending = [s for s in scenarios if s.scenario_id not in processed]

        return {
            "scenarios": scenarios,
            "pending_scenarios": pending,
        }

    async def _node_execute_validate(self, state: RuleLoopState) -> dict:
        results = list(state["results"])
        processed = set(state["processed_scenario_ids"])
        verdicts: list[OracleVerdict] = []

        for scenario in state["pending_scenarios"]:
            flow_plan = self._flow_planner.generate(state["rule"], scenario)
            trace = await self._executor.execute(state["rule"].rule_id, scenario, flow_plan)
            self._execution_log.append(trace)
            verdict = self._oracle.evaluate(state["rule"], scenario, trace)
            verdicts.append(verdict)
            results.append(
                {
                    "rule_id": state["rule"].rule_id,
                    "scenario": scenario,
                    "flow_id": flow_plan.flow_id,
                    "trace": trace,
                    "verdict": verdict,
                }
            )
            processed.add(scenario.scenario_id)

        return {
            "results": results,
            "processed_scenario_ids": list(processed),
            "last_iteration_verdicts": verdicts,
            "pending_scenarios": [],
        }

    async def _node_critic(self, state: RuleLoopState) -> dict:
        iteration = state["iteration"] + 1
        feedback = await self._critic.analyze_for_rule(
            test_run_id=state["run_id"],
            rule=state["rule"],
            scenarios=state["scenarios"],
            verdicts=state["last_iteration_verdicts"],
            iteration=iteration,
            max_iterations=state["max_iterations"],
        )
        history = list(state["feedback_history"])
        history.append(feedback)
        return {
            "iteration": iteration,
            "last_feedback": feedback,
            "feedback_history": history,
        }

    def _route_after_critic(self, state: RuleLoopState) -> str:
        if state["iteration"] >= state["max_iterations"]:
            return "end"
        feedback = state["last_feedback"]
        if feedback is None or not feedback.findings:
            return "end"
        if _has_diminishing_returns(state["feedback_history"]):
            return "end"
        has_missing_edge = any(f.type == "missing_edge_case" for f in feedback.findings)
        has_edge_scenario = any(s.label == "edge" for s in state["scenarios"])
        if has_missing_edge and not has_edge_scenario:
            return "continue"
        return "end"


def _edge_scenario_for_rule(rule: BusinessRule, scenarios: list[Scenario]) -> Scenario | None:
    if any(s.label == "edge" for s in scenarios):
        return None
    if not scenarios:
        return None
    base = scenarios[0]
    edge_inputs = dict(base.inputs)
    if rule.rule_id == "SHIP_001":
        edge_inputs["shipment_weight"] = 1
    return Scenario(
        scenario_id=f"{rule.rule_id}_SCN_EDGE_001",
        rule_id=rule.rule_id,
        label="edge",
        inputs=edge_inputs,
        expected_outcome="pass",
        rationale="critic requested an explicit edge-case scenario",
    )


def _serialize_result(item: dict[str, Any]) -> dict:
    scenario: Scenario = item["scenario"]
    trace = item["trace"]
    verdict = item["verdict"]
    return {
        "rule_id": item["rule_id"],
        "scenario_id": scenario.scenario_id,
        "flow_id": item["flow_id"],
        "trace_id": trace.trace_id,
        "trace": {
            "trace_id": trace.trace_id,
            "overall_status": trace.overall_status,
            "record_count": len(trace.records),
            "final_status_code": trace.records[-1].status_code if trace.records else None,
        },
        "verdict": verdict.model_dump(mode="json"),
    }


def _has_diminishing_returns(history: list[CriticFeedback]) -> bool:
    if len(history) < 2:
        return False
    prev = history[-2]
    curr = history[-1]
    prev_sig = sorted((f.type, f.target, f.action) for f in prev.findings)
    curr_sig = sorted((f.type, f.target, f.action) for f in curr.findings)
    return prev_sig == curr_sig
