from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

try:
    import asyncpg
except ImportError:  # pragma: no cover - optional dependency
    asyncpg = None  # type: ignore[assignment]

from app.schemas.rules import BusinessRule


CREATE_RULES_SQL = """
CREATE TABLE IF NOT EXISTS business_rules (
    pk          TEXT PRIMARY KEY,
    rule_id     TEXT NOT NULL,
    version     INTEGER NOT NULL,
    status      TEXT NOT NULL,
    data        JSONB NOT NULL,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE(rule_id, version)
);
CREATE INDEX IF NOT EXISTS idx_rules_status ON business_rules(status);
CREATE INDEX IF NOT EXISTS idx_rules_rule_id ON business_rules(rule_id);
"""


class PostgresRuleStore:
    def __init__(self, dsn: str) -> None:
        self._dsn = dsn
        self._pool: Any = None

    async def init(self) -> None:
        self._ensure_driver()
        self._pool = await asyncpg.create_pool(self._dsn)
        async with self._pool.acquire() as conn:
            await conn.execute(CREATE_RULES_SQL)

    async def close(self) -> None:
        if self._pool is not None:
            await self._pool.close()

    async def insert_rule(self, rule: BusinessRule) -> None:
        await self._write_rule(rule)
        await self._detect_conflicts(rule)

    async def _write_rule(self, rule: BusinessRule) -> None:
        await self._ensure_pool()
        pk = f"{rule.rule_id}_v{rule.version}"
        async with self._pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO business_rules (pk, rule_id, version, status, data, created_at)
                VALUES ($1, $2, $3, $4, $5::jsonb, $6)
                ON CONFLICT (pk) DO UPDATE
                SET status = EXCLUDED.status, data = EXCLUDED.data, created_at = EXCLUDED.created_at
                """,
                pk,
                rule.rule_id,
                rule.version,
                rule.status,
                rule.model_dump_json(),
                datetime.now(timezone.utc),
            )

    async def upsert_rule(self, rule: BusinessRule) -> None:
        await self.insert_rule(rule)

    async def save_rule(self, rule: BusinessRule) -> None:
        await self._write_rule(rule)

    async def next_version(self, rule_id: str) -> int:
        await self._ensure_pool()
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT COALESCE(MAX(version), 0) AS max_version FROM business_rules WHERE rule_id = $1",
                rule_id,
            )
        return int(row["max_version"]) + 1

    async def get_rule(self, rule_id: str, version: int | None = None) -> BusinessRule | None:
        await self._ensure_pool()
        async with self._pool.acquire() as conn:
            if version is None:
                row = await conn.fetchrow(
                    "SELECT data::text AS data FROM business_rules WHERE rule_id = $1 "
                    "ORDER BY version DESC LIMIT 1",
                    rule_id,
                )
            else:
                row = await conn.fetchrow(
                    "SELECT data::text AS data FROM business_rules WHERE rule_id = $1 AND version = $2",
                    rule_id,
                    version,
                )
        if not row:
            return None
        return BusinessRule.model_validate_json(row["data"])

    async def get_rules_by_status(self, status: str) -> list[BusinessRule]:
        await self._ensure_pool()
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT data::text AS data FROM business_rules WHERE status = $1 ORDER BY created_at DESC",
                status,
            )
        return [BusinessRule.model_validate_json(r["data"]) for r in rows]

    async def get_active_rules(self, entity: str | None = None) -> list[BusinessRule]:
        rules = await self.get_rules_by_status("approved")
        if entity is None:
            return rules
        return [r for r in rules if entity in r.entities]

    async def get_rule_history(self, rule_id: str) -> list[BusinessRule]:
        await self._ensure_pool()
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT data::text AS data FROM business_rules WHERE rule_id = $1 ORDER BY version ASC",
                rule_id,
            )
        return [BusinessRule.model_validate_json(r["data"]) for r in rows]

    async def get_conflicts(self, rule_id: str) -> list[str]:
        rule = await self.get_rule(rule_id)
        return rule.conflicts_with if rule else []

    async def get_latest_proposed(self, rule_id: str) -> BusinessRule | None:
        await self._ensure_pool()
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT data::text AS data FROM business_rules WHERE rule_id = $1 AND status = 'proposed' "
                "ORDER BY version DESC LIMIT 1",
                rule_id,
            )
        if not row:
            return None
        return BusinessRule.model_validate_json(row["data"])

    async def approve_rule(
        self,
        rule_id: str,
        version: int | None = None,
        approved_by: str = "human",
        edits: dict | None = None,
    ) -> BusinessRule:
        rule = await self.get_rule(rule_id, version)
        if rule is None:
            raise ValueError(f"Rule not found: {rule_id}")
        if edits:
            rule = rule.model_copy(update=edits)

        history = await self.get_rule_history(rule_id)
        for item in history:
            if item.version != rule.version and item.status == "approved":
                item.status = "deprecated"  # type: ignore[assignment]
                await self.save_rule(item)

        rule.status = "approved"  # type: ignore[assignment]
        rule.approved_by = approved_by
        rule.approved_at = datetime.now(timezone.utc)
        await self.save_rule(rule)
        await self._detect_conflicts(rule)
        return rule

    async def reject_rule(
        self,
        rule_id: str,
        version: int | None = None,
        reason: str | None = None,
    ) -> BusinessRule:
        rule = await self.get_rule(rule_id, version)
        if rule is None:
            raise ValueError(f"Rule not found: {rule_id}")
        rule.status = "deprecated"  # type: ignore[assignment]
        rule.change_reason = reason
        await self.save_rule(rule)
        return rule

    async def _detect_conflicts(self, new_rule: BusinessRule) -> None:
        if new_rule.status != "approved":
            return

        existing = await self.get_active_rules()
        for existing_rule in existing:
            if existing_rule.rule_id == new_rule.rule_id:
                continue
            shared_entities = set(new_rule.entities) & set(existing_rule.entities)
            if not shared_entities:
                continue
            if _conditions_may_conflict(new_rule.conditions, existing_rule.conditions):
                if existing_rule.rule_id not in new_rule.conflicts_with:
                    new_rule.conflicts_with.append(existing_rule.rule_id)
                if new_rule.rule_id not in existing_rule.conflicts_with:
                    existing_rule.conflicts_with.append(new_rule.rule_id)
                    await self._write_rule(existing_rule)

        await self._write_rule(new_rule)

    def _ensure_driver(self) -> None:
        if asyncpg is None:  # pragma: no cover - optional dependency
            raise RuntimeError("asyncpg is required for PostgresRuleStore. Install asyncpg.")

    async def _ensure_pool(self) -> None:
        if self._pool is None:
            await self.init()


def _conditions_may_conflict(conds_a: list[str], conds_b: list[str]) -> bool:
    opposing = [("<=", ">="), ("<", ">"), ("==", "!=")]
    for ca in conds_a:
        for cb in conds_b:
            for op_a, op_b in opposing:
                if op_a in ca and op_b in cb:
                    field_a = ca.split(op_a)[0].strip()
                    field_b = cb.split(op_b)[0].strip()
                    if field_a == field_b:
                        return True
    return False
