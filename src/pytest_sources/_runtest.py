from collections.abc import Generator

import pytest

from pytest_sources._core.attribution import carry, source_map
from pytest_sources._core.source import active, source_for


# tryfirst: the source must be on sys.path before any fixture runs.
@pytest.hookimpl(tryfirst=True)
def pytest_runtest_setup(item: pytest.Item) -> None:
    source = source_for(item)
    if source is not None:
        source.activate()
        return

    # An unfanned test belongs to no source, so it must not see the one before it.
    current = active()
    if current is not None:
        current.deactivate()


@pytest.hookimpl(wrapper=True)
def pytest_runtest_makereport(item: pytest.Item) -> Generator[None, pytest.TestReport, pytest.TestReport]:
    report = yield
    carry(report, source_map(item.config))
    return report
