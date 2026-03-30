"""
Dot-path value resolution and evaluation context construction.

All Oracle condition paths resolve against a fixed context shape:
  {"entities": {...}, "scenario": {...}, "response": {...}}
"""

from __future__ import annotations
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from app.schemas.scenarios import Scenario


def resolve(path: str, context: dict) -> Any:
    """Dot-path lookup into a nested dict.

    'entities.shipment.status' → context['entities']['shipment']['status']
    Returns None if any part of the path is missing.
    """
    parts = path.split(".")
    current = context
    for part in parts:
        if isinstance(current, dict) and part in current:
            current = current[part]
        else:
            return None
    return current


def build_eval_context(
    state_snapshot: dict,
    scenario: "Scenario",
    last_response: dict,
) -> dict:
    """Build the standardized evaluation context for Oracle condition evaluation.

    Always produces three top-level keys:
      - entities.*  → entity states keyed by lowercase type name
      - scenario.*  → original test inputs from the Scenario
      - response.*  → latest API response body

    state_snapshot maps entity_id → entity_dict. Entities must have a 'type' field.
    If multiple entities share the same type, the last one wins (V1 simplification).
    """
    entities: dict[str, dict] = {}
    for entity_id, entity_data in state_snapshot.items():
        if not isinstance(entity_data, dict):
            continue
        type_key = entity_data.get("type", "unknown").lower()
        entities[type_key] = entity_data

    return {
        "entities": entities,
        "scenario": scenario.inputs,
        "response": last_response,
    }
