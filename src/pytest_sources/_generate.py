import pytest

from pytest_sources._core.discover import (
    marker_sources_wanted,
    parametrizes_source,
    record_marker_globs,
    scanning,
    sources_for,
)


@pytest.hookimpl(tryfirst=True)
def pytest_generate_tests(metafunc: pytest.Metafunc) -> None:
    if scanning():
        marker = metafunc.definition.get_closest_marker("sources")
        if marker is not None and marker.args:
            record_marker_globs(tuple(marker.args))
        return

    if metafunc.definition.get_closest_marker("no_sources"):
        return

    marker = metafunc.definition.get_closest_marker("sources")
    if marker is not None and marker.args and not marker_sources_wanted(metafunc.config):
        if "source" not in metafunc.fixturenames:
            metafunc.fixturenames.append("source")
        skip = pytest.mark.skip(reason="marker sources are disabled by --skip-marker-sources")
        metafunc.parametrize("source", [pytest.param(None, marks=skip, id="disabled")], indirect=True)
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
