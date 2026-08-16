import pytest

from pytest_sources._core import nodeid
from pytest_sources._core.discover import resolve
from pytest_sources._core.maxfail import SourceMaxfail
from pytest_sources._core.summary import SourceSummary, Summary


# tryfirst: the delimiter must be settled and CallSpec2 patched before anything,
# ours or another plugin's, resolves sources or parametrizes.
@pytest.hookimpl(tryfirst=True)
def pytest_configure(config: pytest.Config) -> None:
    # Again, in case pytest_cmdline_main was skipped (pytester.parseconfigure).
    nodeid.update_delimiter(config)

    # Gate on the raw globs, not resolve(), which can raise UsageError and must
    # find the patch decision already made.
    if config.getoption("sources") or config.getini("sources"):
        nodeid._patch()

    config.addinivalue_line("markers", "sources(*globs): run against matching sources")
    config.addinivalue_line("markers", "no_sources: exempt from --sources fanout")
    config.addinivalue_line("markers", "no_chdir: keep the working directory pytest was started in")

    # Discover once and cache on the config. Load-bearing even when nothing below
    # registers: pytest_generate_tests reads SOURCES from the stash rather than
    # resolving, so an unpopulated stash means no fanout.
    sources = resolve(config)

    # Registered in workers too, since that is where the tests run.
    if config.getoption("sources_maxfail") > 0 and sources:
        config.pluginmanager.register(SourceMaxfail(config), "pytest_sources_maxfail")

    # Controller only: workers report to the controller, which is where the
    # totals are wanted. Nothing runs under --collect-only, so a table of
    # zeroes would only be misleading.
    if (
        sources
        and not hasattr(config, "workerinput")
        and not config.getoption("collectonly", False)
        and Summary(config.getoption("sources_summary")) is not Summary.NONE
    ):
        config.pluginmanager.register(SourceSummary(config), "pytest_sources_summary")


@pytest.hookimpl
def pytest_unconfigure(config: pytest.Config) -> None:
    nodeid.reset()
