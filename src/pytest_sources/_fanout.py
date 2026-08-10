from collections.abc import Iterator

import pytest
from _pytest.python import FunctionDefinition

from pytest_sources._discover import discover
from pytest_sources._stash import MARKER_SOURCES, SOURCES
from pytest_sources.source import Source, make_sources


@pytest.hookimpl
def pytest_configure(config: pytest.Config) -> None:
    config.addinivalue_line("markers", "sources(*globs): run against matching sources")
    config.addinivalue_line("markers", "no_sources: exempt from --sources fanout")


@pytest.hookimpl(tryfirst=True)
def pytest_generate_tests(metafunc: pytest.Metafunc) -> None:
    if metafunc.definition.get_closest_marker("no_sources"):
        return

    sources = _sources_for(metafunc.definition, metafunc.config)
    if not sources:
        return

    if "source" not in metafunc.fixturenames:
        metafunc.fixturenames.append("source")

    metafunc.parametrize(
        "source",
        sources,
        ids=[source.id for source in sources],
        indirect=True,
        scope="session",
    )


@pytest.fixture(scope="session")
def source(request: pytest.FixtureRequest) -> Iterator[Source]:
    active = getattr(request, "param", None)
    if active is None:
        pytest.skip("no sources configured; pass --sources GLOB")

    active.activate()
    yield active
    active.deactivate()


def _sources_for(definition: FunctionDefinition, config: pytest.Config) -> list[Source]:
    marker = definition.get_closest_marker("sources")
    if marker is not None and marker.args:
        return _marker_sources(tuple(marker.args), config)
    return config.stash.get(SOURCES, [])


def _marker_sources(globs: tuple[str, ...], config: pytest.Config) -> list[Source]:
    cache = config.stash.setdefault(MARKER_SOURCES, {})
    if globs not in cache:
        cache[globs] = make_sources(discover(globs, config.rootpath), config.rootpath)
    return cache[globs]
