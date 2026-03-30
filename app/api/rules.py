from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.memory.rule_store import RuleStore
from app.schemas.rules import BusinessRule

router = APIRouter(prefix="/api/v1/rules", tags=["rules"])


class PendingRulesQuery(BaseModel):
    db_path: str | None = None


class ApproveRuleRequest(BaseModel):
    db_path: str | None = None
    version: int | None = None
    approved_by: str = "human"
    edits: dict[str, Any] | None = None


class RejectRuleRequest(BaseModel):
    db_path: str | None = None
    version: int | None = None
    reason: str


@router.get("/pending")
async def get_pending_rules(db_path: str | None = None) -> dict:
    store = RuleStore(db_path=db_path or "invariantflow.db")
    await store.init()
    rules = await store.get_rules_by_status("proposed")
    return {"count": len(rules), "rules": [r.model_dump(mode="json") for r in rules]}


@router.post("/{rule_id}/approve")
async def approve_rule(rule_id: str, body: ApproveRuleRequest) -> dict:
    store = RuleStore(db_path=body.db_path or "invariantflow.db")
    await store.init()
    try:
        approved = await store.approve_rule(
            rule_id=rule_id,
            version=body.version,
            approved_by=body.approved_by,
            edits=body.edits,
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {"rule": approved.model_dump(mode="json")}


@router.post("/{rule_id}/reject")
async def reject_rule(rule_id: str, body: RejectRuleRequest) -> dict:
    store = RuleStore(db_path=body.db_path or "invariantflow.db")
    await store.init()
    try:
        rejected = await store.reject_rule(
            rule_id=rule_id,
            version=body.version,
            reason=body.reason,
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {"rule": rejected.model_dump(mode="json")}


@router.get("/{rule_id}/history")
async def get_rule_history(rule_id: str, db_path: str | None = None) -> dict:
    store = RuleStore(db_path=db_path or "invariantflow.db")
    await store.init()
    history = await store.get_rule_history(rule_id)
    return {"rule_id": rule_id, "versions": [r.model_dump(mode="json") for r in history]}


@router.get("/{rule_id}")
async def get_rule(rule_id: str, version: int | None = None, db_path: str | None = None) -> dict:
    store = RuleStore(db_path=db_path or "invariantflow.db")
    await store.init()
    rule: BusinessRule | None = await store.get_rule(rule_id=rule_id, version=version)
    if rule is None:
        raise HTTPException(status_code=404, detail=f"Rule not found: {rule_id}")
    return {"rule": rule.model_dump(mode="json")}

