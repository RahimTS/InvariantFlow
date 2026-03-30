from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum

from app.config import settings


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
    def __init__(self) -> None:
        self._agents: dict[str, AgentRuntime] = {}
        self._missed_limit = settings.heartbeat_missed_limit

    def register(self, agent_id: str, role: str) -> AgentRuntime:
        runtime = AgentRuntime(agent_id=agent_id, role=role, state=AgentState.IDLE)
        self._agents[agent_id] = runtime
        return runtime

    def transition(self, agent_id: str, state: AgentState) -> AgentRuntime:
        runtime = self._agents[agent_id]
        runtime.state = state
        return runtime

    def heartbeat(self, agent_id: str) -> AgentRuntime:
        runtime = self._agents[agent_id]
        runtime.last_heartbeat = _now()
        runtime.missed_heartbeats = 0
        if runtime.state == AgentState.DRAINING:
            runtime.state = AgentState.IDLE
        return runtime

    def mark_missed(self, agent_id: str) -> AgentRuntime:
        runtime = self._agents[agent_id]
        runtime.missed_heartbeats += 1
        if runtime.missed_heartbeats >= self._missed_limit:
            runtime.state = AgentState.DRAINING
        return runtime

    def terminate(self, agent_id: str) -> AgentRuntime:
        runtime = self._agents[agent_id]
        runtime.state = AgentState.TERMINATED
        return runtime

    def get(self, agent_id: str) -> AgentRuntime | None:
        return self._agents.get(agent_id)

    def all(self) -> list[AgentRuntime]:
        return list(self._agents.values())


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()

