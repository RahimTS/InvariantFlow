from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Request
from pydantic import BaseModel

from app.agents.graph import LangGraphRuleRunner
from app.agents.testing.blackboard_runner import BlackboardRuleRunner
from app.agents.testing.critic import Critic
from app.agents.testing.executor import Executor
from app.agents.testing.rule_runner import RuleTestRunner
from app.agents.testing.scenario_generator import ScenarioGenerator
from app.config import settings
from app.llm.client import create_openrouter_client
from app.memory.blackboard import Blackboard
from app.memory.exec_log import ExecutionLog
from app.memory.rule_store import RuleStore
from app.memory.seeds import seed_starter_rules
from app.runtime import run_registry

router = APIRouter(prefix="/api/v1/testing", tags=["testing"])


class RunRulesRequest(BaseModel):
    entity: str | None = None
    mode: Literal["direct", "blackboard", "langgraph"] = "blackboard"
    seed_starter: bool = False
    db_path: str | None = None
    artifacts_dir: str | None = None
    model_overrides: dict[str, str] | None = None


@router.post("/run")
async def run_rules(body: RunRulesRequest, request: Request) -> dict:
    run_id = await run_registry.create_run(
        metadata={"mode": body.mode, "entity": body.entity, "seed_starter": body.seed_starter}
    )
    db_path = body.db_path or settings.sqlite_db_path
    artifacts_dir = body.artifacts_dir or "artifacts"

    rule_store = RuleStore(db_path=db_path)
    await rule_store.init()
    if body.seed_starter:
        await seed_starter_rules(rule_store)

    execution_log = ExecutionLog(artifacts_dir=artifacts_dir)
    executor = Executor(app=request.app)
    llm_client = create_openrouter_client()
    overrides = body.model_overrides or {}
    scenario_generator = ScenarioGenerator(
        llm_client=llm_client,
        model=overrides.get("scenario_generator"),
    )
    critic = Critic(
        llm_client=llm_client,
        model=overrides.get("critic"),
    )

    try:
        if body.mode == "direct":
            runner = RuleTestRunner(
                rule_store=rule_store,
                scenario_generator=scenario_generator,
                executor=executor,
                execution_log=execution_log,
            )
            summary = await runner.run_active_rules(entity=body.entity)
            payload = _serialize_direct_summary(summary)
            payload["run_id"] = run_id
            await run_registry.complete_run(run_id, payload)
            return payload

        if body.mode == "langgraph":
            runner = LangGraphRuleRunner(
                rule_store=rule_store,
                scenario_generator=scenario_generator,
                executor=executor,
                critic=critic,
                execution_log=execution_log,
            )
            payload = await runner.run_active_rules(
                entity=body.entity,
                max_iterations=settings.max_feedback_iterations,
            )
            payload["run_id"] = run_id
            await run_registry.complete_run(run_id, payload)
            return payload

        blackboard = Blackboard(
            timeout_seconds=settings.blackboard_task_timeout_seconds,
            max_retries=settings.blackboard_max_retries,
        )
        runner = BlackboardRuleRunner(
            rule_store=rule_store,
            blackboard=blackboard,
            scenario_generator=scenario_generator,
            executor=executor,
            execution_log=execution_log,
        )
        payload = await runner.run_active_rules(entity=body.entity)
        payload["run_id"] = run_id
        await run_registry.complete_run(run_id, payload)
        return payload
    except Exception as exc:
        await run_registry.fail_run(run_id, str(exc))
        raise


@router.get("/runs")
async def list_runs(limit: int = 50) -> dict:
    runs = await run_registry.list_runs(limit=limit)
    return {"count": len(runs), "runs": runs}


@router.get("/runs/{run_id}")
async def get_run(run_id: str) -> dict:
    run = await run_registry.get_run(run_id)
    if run is None:
        return {"run_id": run_id, "status": "not_found"}
    return run


@router.get("/tasks/dead")
async def get_dead_tasks() -> dict:
    tasks = await run_registry.latest_dead_tasks()
    return {"count": len(tasks), "tasks": tasks}


def _serialize_direct_summary(summary: dict) -> dict:
    results = []
    for item in summary["results"]:
        verdict = item["verdict"]
        trace = item["trace"]
        results.append(
            {
                "rule_id": item["rule_id"],
                "scenario_id": item["scenario_id"],
                "flow_id": item["flow_id"],
                "trace_id": item["trace_id"],
                "trace": {
                    "trace_id": trace.trace_id,
                    "overall_status": trace.overall_status,
                    "record_count": len(trace.records),
                    "final_status_code": trace.records[-1].status_code if trace.records else None,
                },
                "verdict": verdict.model_dump(mode="json"),
            }
        )

    return {
        "mode": "direct",
        "total_rules": summary["total_rules"],
        "total_scenarios": summary["total_scenarios"],
        "passed": summary["passed"],
        "failed": summary["failed"],
        "inconclusive": summary["inconclusive"],
        "results": results,
    }
