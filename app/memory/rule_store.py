"""
Rule store — persists BusinessRule objects with versioning and conflict detection.

V1: SQLite via aiosqlite.
V2: Postgres (swap by reimplementing this module).
"""

from __future__ import annotations
from datetime import datetime, timezone

import aiosqlite

from app.schemas.rules import BusinessRule


_CREATE_TABLE = """
CREATE TABLE IF NOT EXISTS business_rules (
    pk       TEXT PRIMARY KEY,          -- '{rule_id}_v{version}'
    rule_id  TEXT NOT NULL,
    version  INTEGER NOT NULL,
    status   TEXT NOT NULL,
    data     TEXT NOT NULL,             -- JSON-serialized BusinessRule
    created_at TEXT NOT NULL,
    UNIQUE(rule_id, version)
);
"""


class RuleStore:
    def __init__(self, db_path: str = "invariantflow.db") -> None:
        self._db_path = db_path

    async def init(self) -> None:
        async with aiosqlite.connect(self._db_path) as db:
            await db.execute(_CREATE_TABLE)
            await db.commit()

    # ------------------------------------------------------------------
    # Write operations
    # ------------------------------------------------------------------

    async def insert_rule(self, rule: BusinessRule) -> None:
        pk = f"{rule.rule_id}_v{rule.version}"
        async with aiosqlite.connect(self._db_path) as db:
            await db.execute(
                "INSERT OR REPLACE INTO business_rules (pk, rule_id, version, status, data, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (
                    pk,
                    rule.rule_id,
                    rule.version,
                    rule.status,
                    rule.model_dump_json(),
                    datetime.now(timezone.utc).isoformat(),
                ),
            )
            await db.commit()

        await self._detect_conflicts(rule)

    async def upsert_rule(self, rule: BusinessRule) -> None:
        await self.insert_rule(rule)

    async def next_version(self, rule_id: str) -> int:
        async with aiosqlite.connect(self._db_path) as db:
            cursor = await db.execute(
                "SELECT COALESCE(MAX(version), 0) FROM business_rules WHERE rule_id = ?",
                (rule_id,),
            )
            row = await cursor.fetchone()
        current = int(row[0]) if row else 0
        return current + 1

    async def update_status(
        self,
        rule_id: str,
        version: int,
        status: str,
        approved_by: str | None = None,
    ) -> None:
        async with aiosqlite.connect(self._db_path) as db:
            await db.execute(
                "UPDATE business_rules SET status = ? WHERE rule_id = ? AND version = ?",
                (status, rule_id, version),
            )
            await db.commit()

        # Patch JSON blob so status/approval metadata stays consistent.
        rule = await self.get_rule(rule_id, version)
        if rule:
            rule.status = status  # type: ignore[assignment]
            if approved_by:
                rule.approved_by = approved_by
                rule.approved_at = datetime.now(timezone.utc)
            async with aiosqlite.connect(self._db_path) as db:
                await db.execute(
                    "UPDATE business_rules SET data = ? WHERE rule_id = ? AND version = ?",
                    (rule.model_dump_json(), rule_id, version),
                )
                await db.commit()

    async def save_rule(self, rule: BusinessRule) -> None:
        async with aiosqlite.connect(self._db_path) as db:
            await db.execute(
                "UPDATE business_rules SET status = ?, data = ? WHERE rule_id = ? AND version = ?",
                (rule.status, rule.model_dump_json(), rule.rule_id, rule.version),
            )
            await db.commit()

    async def approve_rule(
        self,
        rule_id: str,
        version: int | None = None,
        approved_by: str = "human",
        edits: dict | None = None,
    ) -> BusinessRule:
        target = await self.get_rule(rule_id, version)
        if target is None:
            raise ValueError(f"Rule not found: {rule_id}")

        if edits:
            target = target.model_copy(update=edits)

        # Deprecate older approved versions for this rule_id.
        history = await self.get_rule_history(rule_id)
        for rule in history:
            if rule.version != target.version and rule.status == "approved":
                rule.status = "deprecated"  # type: ignore[assignment]
                await self.save_rule(rule)

        target.status = "approved"  # type: ignore[assignment]
        target.approved_by = approved_by
        target.approved_at = datetime.now(timezone.utc)
        await self.save_rule(target)
        await self._detect_conflicts(target)
        return target

    async def reject_rule(
        self,
        rule_id: str,
        version: int | None = None,
        reason: str | None = None,
    ) -> BusinessRule:
        target = await self.get_rule(rule_id, version)
        if target is None:
            raise ValueError(f"Rule not found: {rule_id}")
        target.status = "deprecated"  # type: ignore[assignment]
        if reason:
            target.change_reason = reason
        await self.save_rule(target)
        return target

    # ------------------------------------------------------------------
    # Read operations
    # ------------------------------------------------------------------

    async def get_rule(self, rule_id: str, version: int | None = None) -> BusinessRule | None:
        async with aiosqlite.connect(self._db_path) as db:
            if version is None:
                cursor = await db.execute(
                    "SELECT data FROM business_rules WHERE rule_id = ? ORDER BY version DESC LIMIT 1",
                    (rule_id,),
                )
            else:
                cursor = await db.execute(
                    "SELECT data FROM business_rules WHERE rule_id = ? AND version = ?",
                    (rule_id, version),
                )
            row = await cursor.fetchone()
        if row:
            return BusinessRule.model_validate_json(row[0])
        return None

    async def get_active_rules(self, entity: str | None = None) -> list[BusinessRule]:
        async with aiosqlite.connect(self._db_path) as db:
            cursor = await db.execute(
                "SELECT data FROM business_rules WHERE status = 'approved'"
            )
            rows = await cursor.fetchall()

        rules = [BusinessRule.model_validate_json(r[0]) for r in rows]
        if entity:
            rules = [r for r in rules if entity in r.entities]
        return rules

    async def get_rules_by_status(self, status: str) -> list[BusinessRule]:
        async with aiosqlite.connect(self._db_path) as db:
            cursor = await db.execute(
                "SELECT data FROM business_rules WHERE status = ?", (status,)
            )
            rows = await cursor.fetchall()
        return [BusinessRule.model_validate_json(r[0]) for r in rows]

    async def get_latest_proposed(self, rule_id: str) -> BusinessRule | None:
        async with aiosqlite.connect(self._db_path) as db:
            cursor = await db.execute(
                "SELECT data FROM business_rules WHERE rule_id = ? AND status = 'proposed' "
                "ORDER BY version DESC LIMIT 1",
                (rule_id,),
            )
            row = await cursor.fetchone()
        if not row:
            return None
        return BusinessRule.model_validate_json(row[0])

    async def get_rule_history(self, rule_id: str) -> list[BusinessRule]:
        async with aiosqlite.connect(self._db_path) as db:
            cursor = await db.execute(
                "SELECT data FROM business_rules WHERE rule_id = ? ORDER BY version ASC",
                (rule_id,),
            )
            rows = await cursor.fetchall()
        return [BusinessRule.model_validate_json(r[0]) for r in rows]

    async def get_conflicts(self, rule_id: str) -> list[str]:
        rule = await self.get_rule(rule_id)
        if rule:
            return rule.conflicts_with
        return []

    # ------------------------------------------------------------------
    # Conflict detection
    # ------------------------------------------------------------------

    async def _detect_conflicts(self, new_rule: BusinessRule) -> None:
        """Passive conflict detection at insertion time (V1).

        Marks both rules' conflicts_with lists when entity overlap AND
        condition polarity contradiction is detected.
        """
        existing = await self.get_active_rules()
        for existing_rule in existing:
            if existing_rule.rule_id == new_rule.rule_id:
                continue
            shared_entities = set(new_rule.entities) & set(existing_rule.entities)
            if not shared_entities:
                continue
            # Simple heuristic: same entity + opposing conditions
            if _conditions_may_conflict(new_rule.conditions, existing_rule.conditions):
                if existing_rule.rule_id not in new_rule.conflicts_with:
                    new_rule.conflicts_with.append(existing_rule.rule_id)
                    await self._patch_conflicts(new_rule)
                if new_rule.rule_id not in existing_rule.conflicts_with:
                    existing_rule.conflicts_with.append(new_rule.rule_id)
                    await self._patch_conflicts(existing_rule)

    async def _patch_conflicts(self, rule: BusinessRule) -> None:
        async with aiosqlite.connect(self._db_path) as db:
            await db.execute(
                "UPDATE business_rules SET data = ? WHERE rule_id = ? AND version = ?",
                (rule.model_dump_json(), rule.rule_id, rule.version),
            )
            await db.commit()


def _conditions_may_conflict(conds_a: list[str], conds_b: list[str]) -> bool:
    """Heuristic: look for same field with opposing operators (< vs >, == vs !=)."""
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
