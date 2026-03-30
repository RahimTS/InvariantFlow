import pytest
from pathlib import Path
from uuid import uuid4

from app.agents.testing.executor import Executor
from app.agents.testing.flow_planner import FlowPlanner
from app.agents.testing.oracle import Oracle
from app.agents.testing.rule_runner import RuleTestRunner, summarize_verdicts
from app.agents.testing.scenario_generator import ScenarioGenerator
from app.main import app
from app.memory.exec_log import ExecutionLog
from app.memory.rule_store import RuleStore
from app.memory.seeds import seed_starter_rules


@pytest.mark.asyncio
async def test_rule_runner_runs_approved_rules_and_catches_weight_bug() -> None:
    run_root = Path("artifacts") / f"test_run_{uuid4().hex}"
    run_root.mkdir(parents=True, exist_ok=True)
    db_path = run_root / "rules.db"
    artifacts_dir = run_root / "exec_artifacts"

    rule_store = RuleStore(db_path=str(db_path))
    await rule_store.init()
    await seed_starter_rules(rule_store)

    runner = RuleTestRunner(
        rule_store=rule_store,
        scenario_generator=ScenarioGenerator(),
        flow_planner=FlowPlanner(),
        executor=Executor(app=app),
        oracle=Oracle(),
        execution_log=ExecutionLog(artifacts_dir=str(artifacts_dir)),
    )
    summary = await runner.run_active_rules(entity="Shipment")

    assert summary["total_rules"] == 3
    assert summary["total_scenarios"] >= 6
    assert summary["failed"] >= 1

    counts = summarize_verdicts(summary["results"])
    assert counts["fail"] >= 1

    ship_001 = [
        item for item in summary["results"]
        if item["rule_id"] == "SHIP_001"
    ]
    assert ship_001
    assert any(item["verdict"].result == "fail" for item in ship_001)
