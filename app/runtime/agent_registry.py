from __future__ import annotations

from app.agents.lifecycle import AgentLifecycleManager


agent_registry = AgentLifecycleManager()

for agent_id, role in [
    ("extractor", "ingestion"),
    ("normalizer", "ingestion"),
    ("rule_validator", "ingestion"),
    ("scenario_generator", "testing"),
    ("flow_planner", "testing"),
    ("executor", "testing"),
    ("oracle", "testing"),
    ("critic", "testing"),
]:
    if agent_registry.get(agent_id) is None:
        agent_registry.register(agent_id, role)

