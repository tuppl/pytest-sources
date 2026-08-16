import pytest

from pytest_sources._core.discover import resolve
from pytest_sources._core.dist import REQUESTED_DIST, WITHIN


@pytest.hookimpl
def pytest_report_header(config: pytest.Config) -> str | None:
    sources = resolve(config)
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

    # Splitting a source would split its failure budget, so maxfail keeps one
    # work item per source. Same for runs with no spare workers.
    chunks = max(1, workers // sources) if not config.getoption("sources_maxfail") else 1
    if chunks == 1:
        return str(sources)
    # Chunking caps at each source's test count, which is unknown until collection.
    return f"up to {sources * chunks}"
