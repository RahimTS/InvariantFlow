from pydantic import BaseModel
from typing import Literal


class Scenario(BaseModel):
    scenario_id: str
    rule_id: str
    label: Literal["valid", "boundary", "invalid", "edge"]
    inputs: dict
    expected_outcome: Literal["pass", "fail"]
    rationale: str


class FlowStep(BaseModel):
    step_number: int
    endpoint: str
    method: str
    path_params: dict = {}   # {"shipment_id": "$state.shipment_id"}
    payload_map: dict = {}   # {"weight": "$scenario.shipment_weight"}
    extract: dict = {}       # {"shipment_id": "$.response.shipment_id"}
    expected_status: list[int] = [200, 201]


class FlowPlan(BaseModel):
    flow_id: str
    rule_id: str
    name: str
    steps: list[FlowStep]
    description: str
