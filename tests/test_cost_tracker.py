import pytest

from app.llm.cost import CostLimitExceeded, CostTracker
from app.llm.models import LLMUsage


def test_cost_tracker_accumulates_usage() -> None:
    tracker = CostTracker(max_per_rule_usd=1.0, max_per_run_usd=2.0)
    cost = tracker.add_usage(
        rule_id="SHIP_001",
        model="google/gemini-2.5-flash",
        usage=LLMUsage(prompt_tokens=1000, completion_tokens=500, total_tokens=1500),
    )
    assert cost > 0
    snap = tracker.snapshot()
    assert snap["run_total_usd"] > 0
    assert snap["rule_totals_usd"]["SHIP_001"] > 0


def test_cost_tracker_enforces_rule_limit() -> None:
    tracker = CostTracker(max_per_rule_usd=0.0001, max_per_run_usd=1.0)
    with pytest.raises(CostLimitExceeded):
        tracker.add_usage(
            rule_id="SHIP_001",
            model="google/gemini-2.5-flash",
            usage=LLMUsage(prompt_tokens=1000, completion_tokens=1000, total_tokens=2000),
        )

