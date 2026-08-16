import pytest

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
