import os
from collections.abc import Generator

import pytest

from pytest_sources._discover import resolve


@pytest.hookimpl(wrapper=True)
def pytest_cmdline_main(config: pytest.Config) -> Generator[None, object, object]:
    """
    Give every source its own process unless the user asked for otherwise.
    """
    unset = getattr(config.option, "numprocesses", None) is None
    if unset and not _is_worker(config) and resolve(config):
        config.option.numprocesses = "auto"
    return (yield)


@pytest.hookimpl(tryfirst=True)
def pytest_xdist_auto_num_workers(config: pytest.Config) -> int | None:
    """
    One worker per source. tryfirst so this beats xdist's CPU-count default.
    """
    sources = resolve(config)
    return len(sources) if sources else None


def _is_worker(config: pytest.Config) -> bool:
    """
    Whether this process is running tests on behalf of a controller.

    Not xdist.is_xdist_worker, which takes a request or session and only looks at
    config.workerinput. PYTEST_XDIST_WORKER is exported before a worker builds its
    config and is inherited by anything it starts, so this holds at any depth.
    """
    return "PYTEST_XDIST_WORKER" in os.environ or hasattr(config, "workerinput")
