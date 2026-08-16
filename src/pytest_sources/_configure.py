import pytest

from pytest_sources._core import nodeid
from pytest_sources._core.discover import resolve
from pytest_sources._core.maxfail import SourceMaxfail
from pytest_sources._core.summary import SourceSummary, Summary


@pytest.hookimpl(tryfirst=True)
def pytest_configure(config: pytest.Config) -> None:
    nodeid.update_delimiter(config)

    if config.getoption("sources") or config.getini("sources"):
        nodeid._patch()

    config.addinivalue_line("markers", "sources(*globs): run against matching sources")
    config.addinivalue_line("markers", "no_sources: exempt from --sources fanout")
    config.addinivalue_line("markers", "no_chdir: keep the working directory pytest was started in")

    sources = resolve(config)

    if config.getoption("sources_maxfail") > 0 and sources:
        config.pluginmanager.register(SourceMaxfail(config), "pytest_sources_maxfail")

    if (
        sources
        and not hasattr(config, "workerinput")
        and not config.getoption("collectonly", False)
        and Summary(config.getoption("sources_summary")) is not Summary.NONE
    ):
        config.pluginmanager.register(SourceSummary(config), "pytest_sources_summary")


@pytest.hookimpl
def pytest_unconfigure(config: pytest.Config) -> None:
    nodeid.reset()
