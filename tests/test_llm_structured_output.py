import pytest
from pydantic import BaseModel

from app.llm.structured_output import extract_json_object, validate_output


class _Payload(BaseModel):
    value: int


def test_extract_json_object_from_plain_json() -> None:
    data = extract_json_object('{"value": 7}')
    assert data["value"] == 7


def test_extract_json_object_from_wrapped_text() -> None:
    data = extract_json_object("Here is output:\n```json\n{\"value\": 9}\n```")
    assert data["value"] == 9


def test_extract_json_object_raises_when_missing() -> None:
    with pytest.raises(ValueError, match="no JSON object"):
        extract_json_object("not json")


def test_validate_output_uses_pydantic_validation() -> None:
    model = validate_output(_Payload, {"value": 11})
    assert model.value == 11

