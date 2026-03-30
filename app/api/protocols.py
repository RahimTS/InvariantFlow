from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel

from app.config import settings
from app.memory.mem0_store import Mem0Store
from app.runtime import agent_registry

router = APIRouter(tags=["protocols"])


_AGENT_CARDS = [
    {"agent_id": "extractor", "name": "Extractor", "capabilities": ["extract_raw_rules"], "model": settings.extractor_model},
    {"agent_id": "normalizer", "name": "Normalizer", "capabilities": ["normalize_business_rules"], "model": settings.normalizer_model},
    {"agent_id": "rule_validator", "name": "RuleValidator", "capabilities": ["validate_business_rules"], "model": settings.normalizer_model},
    {"agent_id": "scenario_generator", "name": "ScenarioGenerator", "capabilities": ["generate_scenarios"], "model": settings.scenario_generator_model},
    {"agent_id": "flow_planner", "name": "FlowPlanner", "capabilities": ["generate_flow_plans"], "model": settings.flow_planner_model},
    {"agent_id": "executor", "name": "Executor", "capabilities": ["execute_flow_plans"], "model": None},
    {"agent_id": "oracle", "name": "Oracle", "capabilities": ["evaluate_conditions"], "model": settings.oracle_fallback_model},
    {"agent_id": "critic", "name": "Critic", "capabilities": ["critique_verdicts"], "model": settings.critic_model},
]


@router.get("/.well-known/agent-card.json")
async def main_agent_card() -> dict:
    return {
        "name": "InvariantFlow Orchestrator",
        "version": "0.1.0",
        "description": "Business logic API validator swarm orchestrator",
        "agents": _AGENT_CARDS,
        "protocols": ["a2a", "mcp", "sse", "ag-ui"],
    }


@router.get("/api/v1/agents/cards")
async def list_agent_cards() -> dict:
    return {"count": len(_AGENT_CARDS), "agents": _AGENT_CARDS}


@router.get("/api/v1/mcp/tools")
async def list_mcp_tools() -> dict:
    tools = [
        {"name": "run_testing", "description": "Trigger testing run", "path": "/api/v1/testing/run"},
        {"name": "ingest_rules", "description": "Ingest raw business rules", "path": "/api/v1/ingestion/ingest"},
        {"name": "list_pending_rules", "description": "List rules pending approval", "path": "/api/v1/rules/pending"},
    ]
    return {"count": len(tools), "tools": tools}


class MCPCallRequest(BaseModel):
    tool: str
    args: dict = {}


@router.post("/api/v1/mcp/call")
async def mcp_call(body: MCPCallRequest) -> dict:
    # V1 lightweight MCP-style shim for local integration tests.
    return {
        "tool": body.tool,
        "args": body.args,
        "status": "accepted",
        "note": "MCP shim endpoint; integrate fastapi-mcp in production Phase 4.",
    }


@router.get("/api/v1/agents/status")
async def list_agent_status() -> dict:
    agents = [
        {
            "agent_id": a.agent_id,
            "role": a.role,
            "state": a.state.value,
            "last_heartbeat": a.last_heartbeat,
            "missed_heartbeats": a.missed_heartbeats,
        }
        for a in agent_registry.all()
    ]
    return {"count": len(agents), "agents": agents}


@router.post("/api/v1/agents/{agent_id}/heartbeat")
async def heartbeat(agent_id: str) -> dict:
    runtime = agent_registry.get(agent_id)
    if runtime is None:
        runtime = agent_registry.register(agent_id, "dynamic")
    runtime = agent_registry.heartbeat(agent_id)
    return {
        "agent_id": runtime.agent_id,
        "state": runtime.state.value,
        "last_heartbeat": runtime.last_heartbeat,
        "missed_heartbeats": runtime.missed_heartbeats,
    }


class Mem0WriteRequest(BaseModel):
    run_id: str
    memory: dict
    path: str | None = None


@router.post("/api/v1/mem0/{agent_id}")
async def mem0_add(agent_id: str, body: Mem0WriteRequest) -> dict:
    store = Mem0Store(path=body.path or "artifacts/mem0.json")
    store.add(agent_id=agent_id, run_id=body.run_id, memory=body.memory)
    return {"status": "ok"}


@router.get("/api/v1/mem0/{agent_id}")
async def mem0_get(agent_id: str, run_id: str | None = None, path: str | None = None) -> dict:
    store = Mem0Store(path=path or "artifacts/mem0.json")
    return {"agent_id": agent_id, "run_id": run_id, "items": store.get(agent_id=agent_id, run_id=run_id)}
