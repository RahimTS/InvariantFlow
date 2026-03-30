import pytest

from app.mock_api import store


@pytest.fixture(autouse=True)
def reset_mock_store() -> None:
    store.reset()
    yield
    store.reset()

