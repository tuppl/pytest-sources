import pytest


@pytest.hookimpl
def pytest_configure(config: pytest.Config) -> None:
    config.addinivalue_line("markers", "sources(*globs): run against matching sources")
    config.addinivalue_line("markers", "no_sources: exempt from --sources fanout")
