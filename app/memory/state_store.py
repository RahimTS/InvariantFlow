"""
State store — scoped per test run.

V1: in-memory Python dict.
V2: Redis hashes (swap by implementing the StateStore protocol).
"""

from __future__ import annotations
from typing import Protocol, runtime_checkable


@runtime_checkable
class StateStore(Protocol):
    async def get_entity(self, run_id: str, entity_id: str) -> dict | None: ...
    async def update_entity(self, run_id: str, entity_id: str, fields: dict) -> None: ...
    async def get_status_history(self, run_id: str, entity_id: str) -> list[str]: ...
    async def get_entities_by_type(self, run_id: str, entity_type: str) -> list[dict]: ...
    async def get_related_entities(self, run_id: str, entity_id: str) -> list[dict]: ...
    async def snapshot(self, run_id: str) -> dict: ...
    async def clear(self, run_id: str) -> None: ...


class InMemoryStateStore:
    """Thread-safe in-memory state store for V1."""

    def __init__(self) -> None:
        self._store: dict[str, dict[str, dict]] = {}

    def _run(self, run_id: str) -> dict[str, dict]:
        if run_id not in self._store:
            self._store[run_id] = {}
        return self._store[run_id]

    async def get_entity(self, run_id: str, entity_id: str) -> dict | None:
        return self._run(run_id).get(entity_id)

    async def update_entity(self, run_id: str, entity_id: str, fields: dict) -> None:
        run = self._run(run_id)
        if entity_id not in run:
            run[entity_id] = {}
        run[entity_id].update(fields)

    async def get_status_history(self, run_id: str, entity_id: str) -> list[str]:
        entity = self._run(run_id).get(entity_id, {})
        return entity.get("status_history", [])

    async def get_entities_by_type(self, run_id: str, entity_type: str) -> list[dict]:
        return [
            e for e in self._run(run_id).values()
            if e.get("type", "").lower() == entity_type.lower()
        ]

    async def get_related_entities(self, run_id: str, entity_id: str) -> list[dict]:
        """V1: simple scan — return entities that reference entity_id in any field."""
        result = []
        for eid, entity_data in self._run(run_id).items():
            if eid == entity_id:
                continue
            for val in entity_data.values():
                if val == entity_id:
                    result.append(entity_data)
                    break
        return result

    async def snapshot(self, run_id: str) -> dict:
        """Return a shallow copy of all entities for this run."""
        return dict(self._run(run_id))

    async def clear(self, run_id: str) -> None:
        self._store.pop(run_id, None)
