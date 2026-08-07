import pytest

from pytest_sources._discover import discover
from pytest_sources._stash import SOURCES
from pytest_sources.source import make_sources


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


@pytest.hookimpl
def pytest_configure(config: pytest.Config) -> None:
    globs = config.getoption("sources") or config.getini("sources")
    if not globs:
        return
    config.stash[SOURCES] = make_sources(discover(globs, config.rootpath), config.rootpath)
