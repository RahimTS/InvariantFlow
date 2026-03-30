import pytest
from pathlib import Path
from uuid import uuid4

from app.agents.testing.blackboard_runner import BlackboardRuleRunner
from app.agents.testing.executor import Executor
from app.main import app
from app.memory.blackboard import Blackboard
from app.memory.exec_log import ExecutionLog
from app.memory.rule_store import RuleStore
from app.memory.seeds import seed_starter_rules


@pytest.mark.asyncio
async def test_blackboard_runner_processes_tasks_and_catches_bug() -> None:
    run_root = Path("artifacts") / f"bb_runner_{uuid4().hex}"
    run_root.mkdir(parents=True, exist_ok=True)

    rule_store = RuleStore(db_path=str(run_root / "rules.db"))
    await rule_store.init()
    await seed_starter_rules(rule_store)

    runner = BlackboardRuleRunner(
        rule_store=rule_store,
        blackboard=Blackboard(timeout_seconds=30, max_retries=3),
        executor=Executor(app=app),
        execution_log=ExecutionLog(artifacts_dir=str(run_root / "exec")),
    )

    summary = await runner.run_active_rules(entity="Shipment")

    assert summary["mode"] == "blackboard"
    assert summary["total_rules"] == 3
    assert summary["total_scenarios"] >= 6
    assert summary["failed"] >= 1
    assert summary["dead_tasks"] == 0
    assert any(item["rule_id"] == "SHIP_001" and item["verdict"]["result"] == "fail" for item in summary["results"])

