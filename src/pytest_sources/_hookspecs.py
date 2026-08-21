import pytest


@pytest.hookspec(firstresult=True)
def pytest_sources_source_of(nodeid: str) -> str | None:
    """
    The source an item belongs to, when pytest-sources did not fan it out.

    Implement this for items another collector creates, one per source, whose
    nodeid names no source. The answer is used to attribute results, spend the
    failure budget and place the item with its source's worker. An id outside
    the run's sources is ignored, as is None.

    The implementation must live in a rootdir conftest or an installed plugin,
    because a subdirectory conftest never loads on the xdist controller, and a
    plugin shipping it needs pytest.hookimpl(optionalhook=True) to keep working
    where pytest-sources is absent.
    """
