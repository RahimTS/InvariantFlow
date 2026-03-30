from pydantic import BaseModel
from typing import Literal


class OracleVerdict(BaseModel):
    trace_id: str
    rule_id: str
    scenario_id: str
    result: Literal["pass", "fail", "inconclusive"]
    violated_conditions: list[str]
    evaluation_method: Literal["deterministic", "llm_assisted"]
    reproducible: bool  # False when evaluation_method is llm_assisted
    evidence: dict
    confidence: float
