import pytest

from pytest_sources._core.discover import parametrizes_source, sources_for


@pytest.hookimpl(tryfirst=True)
def pytest_generate_tests(metafunc: pytest.Metafunc) -> None:
    if metafunc.definition.get_closest_marker("no_sources"):
        return

    sources = sources_for(metafunc.definition, metafunc.config)
    if not sources:
        return

    if parametrizes_source(metafunc.definition):
        raise pytest.UsageError(
            f"the parameter name 'source' is taken by pytest-sources while --sources "
            f"is active: {metafunc.definition.nodeid}. Rename the parameter, or mark "
            f"the test no_sources to keep it."
        )

    if "source" not in metafunc.fixturenames:
        metafunc.fixturenames.append("source")

    metafunc.parametrize(
        "source",
        sources,
        ids=[source.id for source in sources],
        indirect=True,
        scope="session",
    )
