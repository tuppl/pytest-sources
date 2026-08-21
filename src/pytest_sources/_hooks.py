import pytest

from pytest_sources import _hookspecs


@pytest.hookimpl
def pytest_addhooks(pluginmanager: pytest.PytestPluginManager) -> None:
    pluginmanager.add_hookspecs(_hookspecs)
