import pytest

from pytest_sources._core.source import active


@pytest.hookimpl
def pytest_sessionfinish(session: pytest.Session) -> None:
    current = active()
    if current is not None:
        current.deactivate()
