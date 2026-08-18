import pytest

from pytest_sources._core.discover import universe
from pytest_sources._core.dist import REQUESTED_DIST, WITHIN


@pytest.hookimpl
def pytest_report_header(config: pytest.Config) -> str | None:
    sources = universe(config)
    if not sources:
        return None

    workers = getattr(config.option, "numprocesses", None)
    if not workers:
        # Report when sources are single-process.
        return f"sources: {len(sources)} in one shared process; pass -n auto for a process per source"

    return f"sources: {len(sources)}, workers: {workers}, work items: {_work_items(config, len(sources), workers)}"


def _work_items(config: pytest.Config, sources: int, workers: int) -> str:
    """The work items this run will schedule, as far as is known before collection."""
    mode = config.stash.get(REQUESTED_DIST, None)
    if mode is not None and mode in WITHIN:
        return f"decided by --dist {mode}"

    if config.getoption("sources_maxfail") or workers <= sources:
        return str(sources)
    return f"up to {workers}"
