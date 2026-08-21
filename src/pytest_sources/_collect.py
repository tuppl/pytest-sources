import pytest

from pytest_sources._core.attribution import record
from pytest_sources._core.discover import scanning


@pytest.hookimpl(trylast=True)
def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    if scanning():
        return
    record(items, config)
