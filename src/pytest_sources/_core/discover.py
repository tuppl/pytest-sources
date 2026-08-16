import glob
from collections.abc import Sequence
from pathlib import Path

import pytest
from _pytest.python import FunctionDefinition

from pytest_sources._core.source import Source, make_sources

SOURCES = pytest.StashKey[list[Source]]()
MARKER_SOURCES = pytest.StashKey[dict[tuple[str, ...], list[Source]]]()


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
        cache[globs] = _narrow(globs, config)
    return cache[globs]


def _narrow(globs: tuple[str, ...], config: pytest.Config) -> list[Source]:
    """
    Select the run's sources that the marker's globs match.
    """
    matched = make_sources(discover(globs, config.rootpath), config.rootpath)
    declared = resolve(config)
    # Nothing declared, so the markers are the whole run and there is no set to
    # narrow. Every source shares a process, as under -n 0.
    if not declared:
        return matched

    paths = {source.path for source in declared}
    undeclared = sorted(source.id for source in matched if source.path not in paths)
    if undeclared:
        raise pytest.UsageError(
            f"sources marker matched sources that --sources did not: {', '.join(undeclared)}. "
            f"Add them to --sources, or narrow the marker."
        )

    matched_paths = {source.path for source in matched}
    return [source for source in declared if source.path in matched_paths]
