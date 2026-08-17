from pathlib import Path

import pytest

from pytest_sources._core import nodeid
from pytest_sources._core.discover import UNIVERSE, resolve, scanning, universe
from pytest_sources._core.maxfail import SourceMaxfail
from pytest_sources._core.source import Source
from pytest_sources._core.summary import SourceSummary, Summary


@pytest.hookimpl(tryfirst=True)
def pytest_configure(config: pytest.Config) -> None:
    # The scanning pass only reads markers; patching or registering anything
    # would leak into the run that started it.
    if scanning():
        _register_markers(config)
        return

    nodeid.update_delimiter(config)

    _register_markers(config)

    resolve(config)

    # A worker cannot scan for marker sources itself; the controller already did
    # and ships the result along.
    workerinput = getattr(config, "workerinput", None)
    if workerinput is not None and "sources_universe" in workerinput:
        config.stash[UNIVERSE] = [Source(path=Path(path), id=id) for path, id in workerinput["sources_universe"]]

    sources = universe(config)

    # Patch only for runs that fan out, so unrelated projects keep pytest's ids.
    if sources:
        nodeid._patch()

    # Registered in workers too, since that is where the tests run.
    if config.getoption("sources_maxfail") > 0 and sources:
        config.pluginmanager.register(SourceMaxfail(config), "pytest_sources_maxfail")

    if (
        sources
        and workerinput is None
        and not config.getoption("collectonly", False)
        and Summary(config.getoption("sources_summary")) is not Summary.NONE
    ):
        config.pluginmanager.register(SourceSummary(config), "pytest_sources_summary")


def _register_markers(config: pytest.Config) -> None:
    config.addinivalue_line("markers", "sources(*globs): run against matching sources")
    config.addinivalue_line("markers", "no_sources: exempt from --sources fanout")
    config.addinivalue_line("markers", "no_chdir: keep the working directory pytest was started in")


@pytest.hookimpl
def pytest_unconfigure(config: pytest.Config) -> None:
    if scanning():
        return
    nodeid.reset()
