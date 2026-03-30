"""
Ingestion chain:
Extractor -> Normalizer -> Rule Validator -> store proposed rules for human approval.
"""

from __future__ import annotations

from app.agents.ingestion.extractor import Extractor
from app.agents.ingestion.normalizer import Normalizer
from app.agents.ingestion.rule_validator import RuleValidator
from app.memory.rule_store import RuleStore
from app.schemas.rules import BusinessRule


class IngestionPipeline:
    def __init__(
        self,
        rule_store: RuleStore,
        extractor: Extractor | None = None,
        normalizer: Normalizer | None = None,
        validator: RuleValidator | None = None,
    ) -> None:
        self._rule_store = rule_store
        self._extractor = extractor or Extractor()
        self._normalizer = normalizer or Normalizer()
        self._validator = validator or RuleValidator()

    async def ingest_text(self, source: str, text: str) -> dict:
        extraction = self._extractor.extract(source=source, text=text)
        normalization = await self._normalizer.normalize(extraction)

        stored: list[dict] = []
        for rule in normalization.rules:
            rule = await self._assign_version(rule)
            validation_result = self._validator.validate(rule)

            # Keep all non-rejected rules in proposed status for human gate.
            if validation_result.verdict.verdict != "rejected":
                validation_result.rule.status = "proposed"  # type: ignore[assignment]
                await self._rule_store.insert_rule(validation_result.rule)

            stored.append(
                {
                    "rule_id": validation_result.rule.rule_id,
                    "version": validation_result.rule.version,
                    "status": validation_result.rule.status,
                    "requires_llm": validation_result.rule.requires_llm,
                    "validation": validation_result.verdict.model_dump(mode="json"),
                }
            )

        return {
            "source": source,
            "raw_extraction": extraction.model_dump(mode="json"),
            "normalizer_used_llm": normalization.used_llm,
            "rules": stored,
            "total_rules": len(stored),
        }

    async def _assign_version(self, rule: BusinessRule) -> BusinessRule:
        history = await self._rule_store.get_rule_history(rule.rule_id)
        if history:
            next_version = max(r.version for r in history) + 1
            return rule.model_copy(update={"version": next_version})
        return rule

