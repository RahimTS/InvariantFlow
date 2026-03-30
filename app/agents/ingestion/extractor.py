"""
Deterministic extractor for Phase 3 groundwork.
"""

from __future__ import annotations

import re

from app.schemas.rules import RawExtraction


class Extractor:
    _KEYWORDS = ("must", "should", "cannot", "can't", "before", "after", "if")

    def extract(self, source: str, text: str) -> RawExtraction:
        chunks = _split_text(text)
        raw_rules = [chunk for chunk in chunks if _looks_like_rule(chunk)]
        if not raw_rules and text.strip():
            raw_rules = [text.strip()]

        confidence = 0.9 if raw_rules else 0.2
        return RawExtraction(
            source=source,
            raw_rules=raw_rules,
            extraction_confidence=confidence,
        )


def _split_text(text: str) -> list[str]:
    cleaned = text.replace("\r", "\n")
    parts = re.split(r"[\n;]+", cleaned)
    return [p.strip(" -\t") for p in parts if p.strip()]


def _looks_like_rule(text: str) -> bool:
    lower = text.lower()
    return any(k in lower for k in Extractor._KEYWORDS)

