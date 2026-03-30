"""
Normalizer agent: RawExtraction -> proposed BusinessRule objects.
LLM-first with deterministic fallback.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from app.config import settings
from app.llm.client import StructuredLLMClient
from app.schemas.rules import BusinessRule, RawExtraction


@dataclass
class NormalizerResult:
    rules: list[BusinessRule]
    used_llm: bool = False


class Normalizer:
    def __init__(
        self,
        llm_client: StructuredLLMClient | None = None,
        model: str | None = None,
    ) -> None:
        self._llm_client = llm_client
        self._model = model or settings.normalizer_model

    async def normalize(self, extraction: RawExtraction) -> NormalizerResult:
        if self._llm_client is not None:
            try:
                rules = await self._normalize_with_llm(extraction)
                if rules:
                    return NormalizerResult(rules=rules, used_llm=True)
            except Exception:
                pass
        return NormalizerResult(rules=self._normalize_deterministic(extraction), used_llm=False)

    async def _normalize_with_llm(self, extraction: RawExtraction) -> list[BusinessRule]:
        payload = await self._llm_client.generate_structured(
            model=self._model,
            system_prompt=_NORMALIZER_SYSTEM_PROMPT,
            user_prompt=_build_prompt(extraction),
            schema_name="normalized_business_rules",
            schema=_NORMALIZER_SCHEMA,
            temperature=0.1,
        )
        rows = payload.get("rules")
        if not isinstance(rows, list):
            raise ValueError("normalizer output missing rules list")

        rules: list[BusinessRule] = []
        for idx, row in enumerate(rows):
            if not isinstance(row, dict):
                continue
            data = dict(row)
            data.setdefault("rule_id", _make_rule_id(extraction.source, idx + 1))
            data.setdefault("version", 1)
            data.setdefault("status", "proposed")
            data.setdefault("created_by", "normalizer_llm")
            rules.append(BusinessRule.model_validate(data))
        return rules

    def _normalize_deterministic(self, extraction: RawExtraction) -> list[BusinessRule]:
        rules: list[BusinessRule] = []
        for idx, text in enumerate(extraction.raw_rules, start=1):
            lower = text.lower()
            if "weight" in lower and "capacity" in lower:
                rules.append(
                    BusinessRule(
                        rule_id=f"NRM_{idx:03d}",
                        type="constraint",
                        description=text,
                        entities=["Shipment", "Vehicle"],
                        conditions=["scenario.shipment_weight <= entities.vehicle.capacity"],
                        expected_effect=["dispatch should be rejected if weight exceeds capacity"],
                        invalid_scenarios=["shipment_weight > vehicle_capacity should fail dispatch"],
                        edge_cases=["shipment_weight == vehicle_capacity"],
                        source=[extraction.source],
                        status="proposed",
                        created_by="normalizer_fallback",
                    )
                )
                continue

            if "before dispatch" in lower or ("assigned" in lower and "dispatch" in lower):
                rules.append(
                    BusinessRule(
                        rule_id=f"NRM_{idx:03d}",
                        type="precondition",
                        description=text,
                        entities=["Shipment"],
                        conditions=["entities.shipment.status == 'ASSIGNED'"],
                        expected_effect=["dispatch should fail if not ASSIGNED"],
                        invalid_scenarios=["dispatch a CREATED shipment without assigning"],
                        source=[extraction.source],
                        status="proposed",
                        created_by="normalizer_fallback",
                    )
                )
                continue

            rules.append(
                BusinessRule(
                    rule_id=f"NRM_{idx:03d}",
                    type="derived",
                    description=text,
                    entities=["Shipment"],
                    conditions=["entities.shipment.status != null"],
                    expected_effect=["shipment state should remain trackable"],
                    invalid_scenarios=["shipment status is missing"],
                    source=[extraction.source],
                    status="proposed",
                    created_by="normalizer_fallback",
                    requires_llm=True,
                )
            )

        if not rules and extraction.source:
            rules.append(
                BusinessRule(
                    rule_id="NRM_001",
                    type="derived",
                    description=f"No rule-like statement extracted from source={extraction.source}",
                    entities=["Shipment"],
                    conditions=["entities.shipment.status != null"],
                    expected_effect=["shipment state should remain trackable"],
                    invalid_scenarios=["shipment status is missing"],
                    source=[extraction.source],
                    status="proposed",
                    created_by="normalizer_fallback",
                    requires_llm=True,
                )
            )
        return rules


def _make_rule_id(source: str, index: int) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9]+", "_", source or "SRC").strip("_").upper()
    if not cleaned:
        cleaned = "SRC"
    return f"{cleaned}_{index:03d}"


_NORMALIZER_SYSTEM_PROMPT = (
    "Convert extracted rule-like statements into BusinessRule JSON records. "
    "Use deterministic dot-path conditions when possible."
)


_NORMALIZER_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "rules": {
            "type": "array",
            "minItems": 1,
            "items": {
                "type": "object",
                "additionalProperties": True,
                "properties": {
                    "rule_id": {"type": "string"},
                    "type": {
                        "type": "string",
                        "enum": ["constraint", "state_transition", "precondition", "postcondition", "derived"],
                    },
                    "description": {"type": "string"},
                    "entities": {"type": "array", "items": {"type": "string"}},
                    "conditions": {"type": "array", "items": {"type": "string"}},
                    "expected_effect": {"type": "array", "items": {"type": "string"}},
                    "invalid_scenarios": {"type": "array", "items": {"type": "string"}},
                    "edge_cases": {"type": "array", "items": {"type": "string"}},
                },
                "required": [
                    "type",
                    "description",
                    "entities",
                    "conditions",
                    "expected_effect",
                    "invalid_scenarios",
                ],
            },
        }
    },
    "required": ["rules"],
}


def _build_prompt(extraction: RawExtraction) -> str:
    return (
        f"Source: {extraction.source}\n"
        f"Extraction confidence: {extraction.extraction_confidence}\n"
        "Raw rules:\n"
        + "\n".join(f"- {r}" for r in extraction.raw_rules)
    )

