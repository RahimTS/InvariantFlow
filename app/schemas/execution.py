from pydantic import BaseModel
from typing import Literal
from datetime import datetime


class ExecutionRecord(BaseModel):
    step_number: int
    endpoint: str
    request_payload: dict
    response_body: dict
    status_code: int
    latency_ms: float
    timestamp: datetime


class ExecutionTrace(BaseModel):
    trace_id: str
    rule_id: str
    scenario_id: str
    flow_id: str
    records: list[ExecutionRecord]
    final_state: dict
    overall_status: Literal["completed", "error", "timeout"]
