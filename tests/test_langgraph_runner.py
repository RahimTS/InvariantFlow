import pytest
from pathlib import Path
from uuid import uuid4

from app.agents.graph import LangGraphRuleRunner
from app.agents.testing.executor import Executor
from app.main import app
from app.memory.exec_log import ExecutionLog
from app.memory.rule_store import RuleStore
from app.memory.seeds import seed_starter_rules


@pytest.mark.asyncio
async def test_langgraph_runner_runs_loop_and_produces_feedback() -> None:
    run_root = Path("artifacts") / f"langgraph_{uuid4().hex}"
    run_root.mkdir(parents=True, exist_ok=True)

    rule_store = RuleStore(db_path=str(run_root / "rules.db"))
    await rule_store.init()
    await seed_starter_rules(rule_store)

    runner = LangGraphRuleRunner(
        rule_store=rule_store,
        executor=Executor(app=app),
        execution_log=ExecutionLog(artifacts_dir=str(run_root / "exec")),
    )

    summary = await runner.run_active_rules(entity="Shipment", max_iterations=3)

    assert summary["mode"] == "langgraph"
    assert summary["total_rules"] == 3
    assert summary["total_scenarios"] >= 6
    assert summary["failed"] >= 1
    assert summary["feedback"]
    assert any(fb["findings"] for fb in summary["feedback"])

