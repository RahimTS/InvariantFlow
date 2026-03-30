from __future__ import annotations

import json
import re
from typing import TypeVar

from pydantic import BaseModel

T = TypeVar("T", bound=BaseModel)


def extract_json_object(text: str) -> dict:
    """Extract a JSON object from model text output."""
    text = text.strip()
    if not text:
        raise ValueError("empty model output")

    try:
        obj = json.loads(text)
        if isinstance(obj, dict):
            return obj
    except json.JSONDecodeError:
        pass

    match = re.search(r"\{[\s\S]*\}", text)
    if not match:
        raise ValueError("no JSON object found in model output")

    obj = json.loads(match.group(0))
    if not isinstance(obj, dict):
        raise ValueError("model output did not contain a JSON object")
    return obj


def validate_output(model_type: type[T], payload: dict) -> T:
    return model_type.model_validate(payload)

