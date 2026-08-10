from collections.abc import Iterator

import pytest


@pytest.hookimpl
def pytest_configure(config: pytest.Config) -> None:
    config.addinivalue_line("markers", "no_chdir: keep the working directory pytest was started in")


@pytest.fixture(autouse=True)
def _source_cwd(request: pytest.FixtureRequest) -> Iterator[None]:
    # Requesting the source fixture instead would skip every unfanned test.
    callspec = getattr(request.node, "callspec", None)
    source = callspec.params.get("source") if callspec else None

    if source is None or request.node.get_closest_marker("no_chdir"):
        yield
        return

    with source.chdir():
        yield
