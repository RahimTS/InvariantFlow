from pydantic import BaseModel, Field
from typing import Literal, Optional
from datetime import datetime


class RuleTrigger(BaseModel):
    action: Optional[str] = None
    endpoint: Optional[str] = None


class BusinessRule(BaseModel):
    rule_id: str
    version: int = 1
    type: Literal[
        "constraint",
        "state_transition",
        "precondition",
        "postcondition",
        "derived",
    ]
    description: str
    entities: list[str]
    conditions: list[str]
    trigger: Optional[RuleTrigger] = None
    expected_effect: list[str]
    invalid_scenarios: list[str]
    edge_cases: list[str] = []
    confidence: float = Field(default=0.7, ge=0.0, le=1.0)
    source: list[str] = []

    # Lifecycle
    status: Literal["proposed", "approved", "deprecated"] = "proposed"
    previous_version: Optional[int] = None
    created_by: str = ""
    approved_by: Optional[str] = None
    approved_at: Optional[datetime] = None
    conflicts_with: list[str] = []
    change_reason: Optional[str] = None

    # Set by Rule Validator during validation
    requires_llm: bool = False


# Ingestion layer models

class RawExtraction(BaseModel):
    source: str
    raw_rules: list[str]
    extraction_confidence: float


class ValidationVerdict(BaseModel):
    rule_id: str
    verdict: Literal["approved", "rejected", "needs_revision"]
    issues: list[dict]
    checks_passed: list[str]
    checks_failed: list[str]
