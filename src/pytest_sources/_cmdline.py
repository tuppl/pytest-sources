from collections.abc import Generator

import pytest

from pytest_sources._core import dist, nodeid


@pytest.hookimpl(wrapper=True, tryfirst=True)
def pytest_cmdline_main(config: pytest.Config) -> Generator[None, object, object]:
    nodeid.update_delimiter(config)
    dist.settle(config)
    return (yield)
