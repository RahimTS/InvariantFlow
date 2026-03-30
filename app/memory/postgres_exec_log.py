from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

try:
    import asyncpg
except ImportError:  # pragma: no cover - optional dependency
    asyncpg = None  # type: ignore[assignment]

from app.schemas.execution import ExecutionTrace


CREATE_TRACES_SQL = """
CREATE TABLE IF NOT EXISTS execution_traces (
    trace_id    TEXT PRIMARY KEY,
    rule_id     TEXT NOT NULL,
    scenario_id TEXT NOT NULL,
    flow_id     TEXT NOT NULL,
    run_id      TEXT,
    data        JSONB NOT NULL,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_traces_rule_id ON execution_traces(rule_id);
CREATE INDEX IF NOT EXISTS idx_traces_run_id ON execution_traces(run_id);
"""


class PostgresExecutionLog:
    def __init__(self, dsn: str) -> None:
        self._dsn = dsn
        self._pool: Any = None

    async def init(self) -> None:
        self._ensure_driver()
        self._pool = await asyncpg.create_pool(self._dsn)
        async with self._pool.acquire() as conn:
            await conn.execute(CREATE_TRACES_SQL)

    async def close(self) -> None:
        if self._pool is not None:
            await self._pool.close()

    async def append(self, trace: ExecutionTrace, run_id: str | None = None) -> None:
        await self._ensure_pool()
        async with self._pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO execution_traces (trace_id, rule_id, scenario_id, flow_id, run_id, data, created_at)
                VALUES ($1, $2, $3, $4, $5, $6::jsonb, $7)
                ON CONFLICT (trace_id) DO UPDATE SET data = EXCLUDED.data
                """,
                trace.trace_id,
                trace.rule_id,
                trace.scenario_id,
                trace.flow_id,
                run_id,
                trace.model_dump_json(),
                datetime.now(timezone.utc),
            )

    async def get_by_trace(self, trace_id: str) -> ExecutionTrace | None:
        await self._ensure_pool()
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT data::text AS data FROM execution_traces WHERE trace_id = $1",
                trace_id,
            )
        if not row:
            return None
        return ExecutionTrace.model_validate_json(row["data"])

    async def get_by_rule(self, rule_id: str) -> list[ExecutionTrace]:
        await self._ensure_pool()
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT data::text AS data FROM execution_traces WHERE rule_id = $1 ORDER BY created_at DESC",
                rule_id,
            )
        return [ExecutionTrace.model_validate_json(r["data"]) for r in rows]

    async def get_by_scenario(self, scenario_id: str) -> list[ExecutionTrace]:
        await self._ensure_pool()
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT data::text AS data FROM execution_traces WHERE scenario_id = $1 ORDER BY created_at DESC",
                scenario_id,
            )
        return [ExecutionTrace.model_validate_json(r["data"]) for r in rows]

    async def _ensure_pool(self) -> None:
        if self._pool is None:
            await self.init()

    def _ensure_driver(self) -> None:
        if asyncpg is None:  # pragma: no cover
            raise RuntimeError("asyncpg is required for PostgresExecutionLog. Install asyncpg.")
