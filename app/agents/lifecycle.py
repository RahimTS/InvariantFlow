from __future__ import annotations

import asyncio
import inspect
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any

from app.config import settings
from app.runtime.events import make_event

logger = logging.getLogger(__name__)


class AgentState(str, Enum):
    REGISTERED = "REGISTERED"
    IDLE = "IDLE"
    ACTIVE = "ACTIVE"
    DRAINING = "DRAINING"
    TERMINATED = "TERMINATED"


@dataclass
class AgentRuntime:
    agent_id: str
    role: str
    state: AgentState = AgentState.REGISTERED
    last_heartbeat: str = field(default_factory=lambda: _now())
    missed_heartbeats: int = 0


class AgentLifecycleManager:
    def __init__(self, event_emitter: Any | None = None) -> None:
        self._agents: dict[str, AgentRuntime] = {}
        self._missed_limit = settings.heartbeat_missed_limit
        self._event_emitter = event_emitter

    def register(self, agent_id: str, role: str) -> AgentRuntime:
        runtime = AgentRuntime(agent_id=agent_id, role=role, state=AgentState.IDLE)
        self._agents[agent_id] = runtime
        self._emit_state(agent_id=agent_id, old_state=None, new_state=runtime.state)
        return runtime

    def transition(self, agent_id: str, state: AgentState) -> AgentRuntime:
        runtime = self._agents[agent_id]
        old_state = runtime.state
        runtime.state = state
        self._emit_state(agent_id=agent_id, old_state=old_state, new_state=runtime.state)
        return runtime

    def heartbeat(self, agent_id: str) -> AgentRuntime:
        runtime = self._agents[agent_id]
        old_state = runtime.state
        runtime.last_heartbeat = _now()
        runtime.missed_heartbeats = 0
        if runtime.state == AgentState.DRAINING:
            runtime.state = AgentState.IDLE
        if old_state != runtime.state:
            self._emit_state(agent_id=agent_id, old_state=old_state, new_state=runtime.state)
        return runtime

    def mark_missed(self, agent_id: str) -> AgentRuntime:
        runtime = self._agents[agent_id]
        old_state = runtime.state
        runtime.missed_heartbeats += 1
        if runtime.missed_heartbeats >= self._missed_limit:
            runtime.state = AgentState.DRAINING
        if old_state != runtime.state:
            self._emit_state(agent_id=agent_id, old_state=old_state, new_state=runtime.state)
        return runtime

    def terminate(self, agent_id: str) -> AgentRuntime:
        runtime = self._agents[agent_id]
        old_state = runtime.state
        runtime.state = AgentState.TERMINATED
        self._emit_state(agent_id=agent_id, old_state=old_state, new_state=runtime.state)
        return runtime

    def get(self, agent_id: str) -> AgentRuntime | None:
        return self._agents.get(agent_id)

    def all(self) -> list[AgentRuntime]:
        return list(self._agents.values())

    def set_event_emitter(self, event_emitter: Any | None) -> None:
        self._event_emitter = event_emitter

    def _emit_state(self, agent_id: str, old_state: AgentState | None, new_state: AgentState) -> None:
        if self._event_emitter is None:
            return
        event = make_event(
            "AGENT_STATE",
            {
                "agent_id": agent_id,
                "old_state": old_state.value if old_state else None,
                "new_state": new_state.value,
            },
        )
        try:
            result = self._event_emitter(event)
            if inspect.isawaitable(result):
                try:
                    asyncio.get_running_loop().create_task(result)
                except RuntimeError:
                    pass
        except Exception:
            logger.exception("agent lifecycle event emission failed")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()
