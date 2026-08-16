import pytest
from xdist.remote import Producer
from xdist.workermanage import WorkerController

from pytest_sources._core.discover import resolve
from pytest_sources._core.schedule import SourceScheduling, start_replacement


@pytest.hookimpl
def pytest_xdist_make_scheduler(config: pytest.Config, log: Producer) -> SourceScheduling | None:
    if not resolve(config):
        return None
    return SourceScheduling(config, log)


@pytest.hookimpl(tryfirst=True)
def pytest_xdist_auto_num_workers(config: pytest.Config) -> int | None:
    """
    One worker per source. tryfirst so this beats xdist's CPU-count default.
    """
    sources = resolve(config)
    return len(sources) if sources else None


@pytest.hookimpl
def pytest_testnodedown(node: WorkerController, error: object | None) -> None:
    start_replacement(node, error)
