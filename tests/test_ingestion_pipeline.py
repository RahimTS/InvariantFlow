import pytest
from pathlib import Path
from uuid import uuid4

from app.agents.ingestion.pipeline import IngestionPipeline
from app.memory.rule_store import RuleStore


@pytest.mark.asyncio
async def test_ingestion_pipeline_stores_proposed_rules() -> None:
    run_root = Path("artifacts") / f"ingestion_{uuid4().hex}"
    run_root.mkdir(parents=True, exist_ok=True)
    db_path = run_root / "rules.db"

    store = RuleStore(db_path=str(db_path))
    await store.init()
    pipeline = IngestionPipeline(rule_store=store)

    result = await pipeline.ingest_text(
        source="jira-123",
        text=(
            "Shipment weight must not exceed vehicle capacity.\n"
            "Shipment must be assigned before dispatch."
        ),
    )

    assert result["total_rules"] >= 2
    pending = await store.get_rules_by_status("proposed")
    assert len(pending) >= 2
    assert any("weight" in r.description.lower() for r in pending)

