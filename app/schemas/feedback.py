from pydantic import BaseModel
from typing import Literal


class CriticFinding(BaseModel):
    type: Literal[
        "missing_edge_case",
        "rule_confidence_update",
        "flow_gap",
        "false_positive",
        "false_negative",
        "rule_revision_suggestion",
    ]
    target: Literal[
        "scenario_generator",
        "flow_planner",
        "oracle",
        "business_memory",
    ]
    detail: str
    action: str
    payload: dict = {}


class CriticFeedback(BaseModel):
    test_run_id: str
    rule_id: str
    findings: list[CriticFinding]
    summary: str
    iterations_remaining: int
