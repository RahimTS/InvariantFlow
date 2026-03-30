"""
Execution log — append-only store of ExecutionRecord objects.

V1: in-memory list with JSON dump to ./artifacts/{run_id}/.
V2: Postgres.
"""

from __future__ import annotations
from pathlib import Path

from app.schemas.execution import ExecutionTrace


class ExecutionLog:
    def __init__(self, artifacts_dir: str = "artifacts") -> None:
        self._log: list[ExecutionTrace] = []
        self._artifacts_dir = Path(artifacts_dir)

    def append(self, trace: ExecutionTrace) -> None:
        self._log.append(trace)
        self._persist(trace)

    def get_by_rule(self, rule_id: str) -> list[ExecutionTrace]:
        return [t for t in self._log if t.rule_id == rule_id]

    def get_by_scenario(self, scenario_id: str) -> list[ExecutionTrace]:
        return [t for t in self._log if t.scenario_id == scenario_id]

    def get_by_trace(self, trace_id: str) -> ExecutionTrace | None:
        for t in self._log:
            if t.trace_id == trace_id:
                return t
        return None

    def all(self) -> list[ExecutionTrace]:
        return list(self._log)

    def _persist(self, trace: ExecutionTrace) -> None:
        run_dir = self._artifacts_dir / trace.trace_id
        run_dir.mkdir(parents=True, exist_ok=True)
        path = run_dir / "trace.json"
        path.write_text(trace.model_dump_json(indent=2))
