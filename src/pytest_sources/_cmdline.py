from collections.abc import Generator

import pytest

from pytest_sources._core import dist, nodeid


# wrapper + tryfirst: the pre-yield half must run before xdist's own
# pytest_cmdline_main, which rewrites --dist no to load as soon as a worker
# count exists and answers -n auto with the CPU count.
@pytest.hookimpl(wrapper=True, tryfirst=True)
def pytest_cmdline_main(config: pytest.Config) -> Generator[None, object, object]:
    # Settle the delimiter first: everything downstream may call resolve(),
    # which validates source ids against it.
    nodeid.update_delimiter(config)
    # Record what the user asked --dist for, and reject conflicts. Must precede
    # the implied worker count: an explicit --dist no claims numprocesses (=0)
    # only while it is still unset.
    dist.settle(config)
    dist.imply_worker_count(config)
    return (yield)
