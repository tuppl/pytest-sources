import pytest

from pytest_sources._discover import resolve


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
    resolve(config)
