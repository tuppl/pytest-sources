import pytest

from pytest_sources._discover import resolve

pytest_plugins = [
    "pytest_sources._nodeid",
    "pytest_sources._option",
    "pytest_sources._fanout",
    "pytest_sources._scheduling",
]


@pytest.hookimpl
def pytest_configure(config: pytest.Config) -> None:
    resolve(config)
