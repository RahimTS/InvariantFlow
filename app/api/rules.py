from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from app.memory.factory import get_rule_store
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
async def get_pending_rules(request: Request, db_path: str | None = None) -> dict:
    store = await get_rule_store(request.app, db_path)
    rules = await store.get_rules_by_status("proposed")
    return {"count": len(rules), "rules": [r.model_dump(mode="json") for r in rules]}


@router.post("/{rule_id}/approve")
async def approve_rule(rule_id: str, body: ApproveRuleRequest, request: Request) -> dict:
    store = await get_rule_store(request.app, body.db_path)
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
async def reject_rule(rule_id: str, body: RejectRuleRequest, request: Request) -> dict:
    store = await get_rule_store(request.app, body.db_path)
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
async def get_rule_history(rule_id: str, request: Request, db_path: str | None = None) -> dict:
    store = await get_rule_store(request.app, db_path)
    history = await store.get_rule_history(rule_id)
    return {"rule_id": rule_id, "versions": [r.model_dump(mode="json") for r in history]}


@router.get("/{rule_id}")
async def get_rule(rule_id: str, request: Request, version: int | None = None, db_path: str | None = None) -> dict:
    store = await get_rule_store(request.app, db_path)
    rule: BusinessRule | None = await store.get_rule(rule_id=rule_id, version=version)
    if rule is None:
        raise HTTPException(status_code=404, detail=f"Rule not found: {rule_id}")
    return {"rule": rule.model_dump(mode="json")}
