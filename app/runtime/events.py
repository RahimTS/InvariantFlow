from __future__ import annotations

from datetime import datetime, timezone
from typing import Any


AGUI_EVENT_MAP: dict[str, str] = {
    "RUN_START": "lifecycle",
    "RUN_COMPLETE": "lifecycle",
    "RUN_FAILED": "lifecycle",
    "TASK_POSTED": "tool_call",
    "TASK_CLAIMED": "tool_call",
    "TASK_COMPLETED": "tool_result",
    "TASK_DEAD": "tool_result",
    "EXECUTION_STEP": "tool_result",
    "VERDICT": "tool_result",
    "CRITIC_FINDING": "text_delta",
    "COST_UPDATE": "state_delta",
    "AGENT_STATE": "state_delta",
}


def make_event(
    event_type: str,
    data: dict[str, Any] | None = None,
    *,
    run_id: str | None = None,
) -> dict[str, Any]:
    event_name = AGUI_EVENT_MAP.get(event_type, "message")
    payload: dict[str, Any] = {
        "event": event_name,
        "event_type": event_type,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "data": data or {},
    }
    if run_id:
        payload["run_id"] = run_id
    return payload

