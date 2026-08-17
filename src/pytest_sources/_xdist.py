import os

import pytest
from xdist.remote import Producer
from xdist.workermanage import WorkerController

from pytest_sources._core.discover import universe
from pytest_sources._core.schedule import SourceScheduling, start_replacement


@pytest.hookimpl
def pytest_xdist_make_scheduler(config: pytest.Config, log: Producer) -> SourceScheduling | None:
    if not universe(config):
        return None
    return SourceScheduling(config, log)


@pytest.hookimpl(tryfirst=True)
def pytest_xdist_auto_num_workers(config: pytest.Config) -> int | None:
    """
    One worker per source capped by machine's CPU count.
    """
    sources = universe(config)
    if not sources:
        return None
    return min(len(sources), os.cpu_count() or 1)


@pytest.hookimpl
def pytest_testnodedown(node: WorkerController, error: object | None) -> None:
    start_replacement(node, error)


@pytest.hookimpl
def pytest_configure_node(node: WorkerController) -> None:
    """
    Ship the source universe to the worker, which cannot scan for it itself.
    """
    sources = universe(node.config)
    if sources:
        node.workerinput["sources_universe"] = [[str(source.path), source.id] for source in sources]
