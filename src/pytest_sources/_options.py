import pytest

from pytest_sources._core.nodeid import DEFAULT
from pytest_sources._core.summary import Summary


@pytest.hookimpl
def pytest_addoption(parser: pytest.Parser) -> None:
    group = parser.getgroup("sources")
    group.addoption(
        "--sources",
        dest="sources",
        metavar="GLOB",
        action="append",
        default=[],
        help="Glob matching source directories to run each test against (repeatable)",
    )
    parser.addini("sources", type="args", default=[], help="Default --sources globs")

    group.addoption(
        "--sources-delimiter",
        dest="sources_delimiter",
        metavar="CHAR",
        default=None,
        help=(
            f"Character separating parameters in a test id, {DEFAULT!r} by default. No source path may contain the delimiter."
        ),
    )
    parser.addini("sources_delimiter", default=DEFAULT, help="Default --sources-delimiter")

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

    group.addoption(
        "--sources-summary",
        dest="sources_summary",
        choices=list(Summary),
        default=Summary.COUNTS,
        help=(
            "Summary printed after the run. counts: a row per source with outcome "
            "totals. sources: a row per source, a column per test. tests: a row per "
            "test, a column per source. none: no summary."
        ),
    )
