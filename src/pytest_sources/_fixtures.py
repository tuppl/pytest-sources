from collections.abc import Iterator

import pytest

from pytest_sources._core.source import Source, source_for


@pytest.fixture(scope="session")
def source(request: pytest.FixtureRequest) -> Source:
    source = getattr(request, "param", None)
    if source is None:
        pytest.skip("no sources configured; pass --sources GLOB")
    return source


@pytest.fixture(autouse=True)
def _source_cwd(request: pytest.FixtureRequest) -> Iterator[None]:
    # Requesting the source fixture instead would skip every unfanned test.
    source = source_for(request.node)

    if source is None or request.node.get_closest_marker("no_chdir"):
        yield
        return

    with source.chdir():
        yield
