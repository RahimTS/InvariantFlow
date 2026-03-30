"""
Lightweight cross-run memory store (Mem0-style groundwork).
"""

from __future__ import annotations

import json
from pathlib import Path


class Mem0Store:
    def __init__(self, path: str = "artifacts/mem0.json") -> None:
        self._path = Path(path)
        self._path.parent.mkdir(parents=True, exist_ok=True)
        if not self._path.exists():
            self._path.write_text("{}")

    def add(self, agent_id: str, run_id: str, memory: dict) -> None:
        data = self._read()
        agent_mem = data.setdefault(agent_id, {})
        run_mem = agent_mem.setdefault(run_id, [])
        run_mem.append(memory)
        self._write(data)

    def get(self, agent_id: str, run_id: str | None = None) -> list[dict]:
        data = self._read()
        agent_mem = data.get(agent_id, {})
        if run_id is None:
            out: list[dict] = []
            for items in agent_mem.values():
                if isinstance(items, list):
                    out.extend(items)
            return out
        items = agent_mem.get(run_id, [])
        return items if isinstance(items, list) else []

    def _read(self) -> dict:
        try:
            return json.loads(self._path.read_text())
        except json.JSONDecodeError:
            return {}

    def _write(self, data: dict) -> None:
        self._path.write_text(json.dumps(data, indent=2))

