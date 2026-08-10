from collections import Counter

import pytest

from pytest_sources._discover import resolve
from pytest_sources._nodeid import source_of


@pytest.hookimpl
def pytest_addoption(parser: pytest.Parser) -> None:
    group = parser.getgroup("sources")
    group.addoption(
        "--sources-maxfail",
        dest="sources_maxfail",
        type=int,
        default=0,
        metavar="N",
        help=(
            "Stop running a source once N of its tests have failed. Other sources "
            "carry on, unlike --maxfail which ends the run. 0 disables."
        ),
    )


@pytest.hookimpl
def pytest_configure(config: pytest.Config) -> None:
    # Registered in workers too, since that is where the tests run.
    if config.getoption("sources_maxfail") > 0 and resolve(config):
        config.pluginmanager.register(SourceMaxfail(config), "pytest_sources_maxfail")


class SourceMaxfail:
    """Skip a source's remaining tests once enough of them have failed.

    Counts per source rather than per process, so it reads the same whether
    every source has its own worker or they all share one under -n 0.
    """

    def __init__(self, config: pytest.Config) -> None:
        self._limit = config.getoption("sources_maxfail")
        self._source_ids = {source.id for source in resolve(config)}
        self._failures: Counter[str] = Counter()

    @pytest.hookimpl(tryfirst=True)
    def pytest_runtest_setup(self, item: pytest.Item) -> None:
        source = source_of(item.nodeid, self._source_ids)
        if source and self._failures[source] >= self._limit:
            pytest.skip(f"{source} stopped after {self._limit} failures")

    @pytest.hookimpl
    def pytest_runtest_logreport(self, report: pytest.TestReport) -> None:
        # A teardown failure is not counted: the test itself already reported,
        # and counting both would spend two of the budget on one test.
        if not report.failed or report.when not in ("call", "setup"):
            return

        source = source_of(report.nodeid, self._source_ids)
        if source:
            self._failures[source] += 1
