import contextlib
import glob
import io
import os
from collections.abc import Sequence
from pathlib import Path

import pytest
from _pytest.python import FunctionDefinition

from pytest_sources._core.source import Source, make_sources

SOURCES = pytest.StashKey[list[Source]]()
MARKER_SOURCES = pytest.StashKey[dict[tuple[str, ...], list[Source]]]()
UNIVERSE = pytest.StashKey[list[Source]]()

SCAN_ENV = "PYTEST_SOURCES_SCAN"

_harvest: list[tuple[str, ...]] | None = None


def resolve(config: pytest.Config) -> list[Source]:
    """
    Discover the configured sources, once per run.

    Called from pytest_configure and, earlier, while xdist works out how many
    workers to start, so the result is cached on the config.
    """
    if SOURCES in config.stash:
        return config.stash[SOURCES]

    globs = config.getoption("sources") or config.getini("sources")
    if not globs:
        return []

    sources = make_sources(discover(globs, config.rootpath), config.rootpath)
    config.stash[SOURCES] = sources
    return sources


def discover(patterns: Sequence[str], root: Path) -> list[Path]:
    """Expand source globs into a sorted, deduplicated list of directories."""
    sources: set[Path] = set()
    for pattern in patterns:
        matches = glob.glob(pattern, root_dir=root, recursive=True)
        if not matches:
            raise pytest.UsageError(f"sources glob matched nothing: {pattern!r}")

        directories = {(root / m).resolve() for m in matches if (root / m).is_dir()}
        if not directories:
            raise pytest.UsageError(
                f"sources glob matched {len(matches)} path(s), none of them directories: {pattern!r}"
            )
        sources |= directories

    return sorted(sources)


def sources_for(definition: FunctionDefinition, config: pytest.Config) -> list[Source]:
    """The sources a test fans out over: the marker's if it carries one, else the run's."""
    marker = definition.get_closest_marker("sources")
    if marker is not None and marker.args:
        return _marker_sources(tuple(marker.args), config)
    return config.stash.get(SOURCES, [])


def parametrizes_source(definition: FunctionDefinition) -> bool:
    """Whether the test carries a parametrize mark of its own named "source"."""
    for mark in definition.iter_markers("parametrize"):
        argnames = mark.args[0] if mark.args else ()
        names = [name.strip() for name in argnames.split(",")] if isinstance(argnames, str) else argnames
        if "source" in names:
            return True
    return False


def _marker_sources(globs: tuple[str, ...], config: pytest.Config) -> list[Source]:
    cache = config.stash.setdefault(MARKER_SOURCES, {})
    if globs not in cache:
        cache[globs] = make_sources(discover(globs, config.rootpath), config.rootpath)
    return cache[globs]


def universe(config: pytest.Config) -> list[Source]:
    """
    Every source the run may touch: the declared set, plus marker sources when
    --sources-scan is on.

    The scheduler, summary, failure budget and report all key off this, so it is
    computed once and cached on the config.
    """
    if UNIVERSE in config.stash:
        return config.stash[UNIVERSE]

    declared = resolve(config)

    if not marker_sources_wanted(config) or scanning() or is_worker(config):
        return declared

    combined = {source.path: source for source in declared}
    for globs in _scan(config):
        for source in make_sources(discover(globs, config.rootpath), config.rootpath):
            combined.setdefault(source.path, source)

    sources = list(combined.values())
    config.stash[UNIVERSE] = sources
    return sources


def marker_sources_wanted(config: pytest.Config) -> bool:
    return not (config.getoption("skip_marker_sources") or config.getini("skip_marker_sources"))


def scanning() -> bool:
    """Whether this process is the marker-scanning collection pass."""
    return SCAN_ENV in os.environ


def record_marker_globs(globs: tuple[str, ...]) -> None:
    if _harvest is not None and globs not in _harvest:
        _harvest.append(globs)


def _scan(config: pytest.Config) -> list[tuple[str, ...]]:
    """
    Collect once, silently, to find the globs that sources markers carry.

    Markers only become readable when collection imports the test modules, which
    is too late for the machinery that needs the full source list up front.
    """
    global _harvest
    arguments = [str(argument) for argument in config.invocation_params.args]
    arguments += ["--collect-only", "-q"]
    if "no:xdist" not in arguments:
        arguments += ["-n", "0"]

    _harvest = []
    os.environ[SCAN_ENV] = "1"
    sink = io.StringIO()
    try:
        with contextlib.redirect_stdout(sink), contextlib.redirect_stderr(sink):
            pytest.main(arguments)
    finally:
        del os.environ[SCAN_ENV]
        harvested, _harvest = _harvest, None
    return harvested


def is_worker(config: pytest.Config) -> bool:
    """
    Whether this process is running tests on behalf of a controller.
    """
    return "PYTEST_XDIST_WORKER" in os.environ or hasattr(config, "workerinput")
