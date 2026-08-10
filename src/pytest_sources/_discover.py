import glob
from collections.abc import Sequence
from pathlib import Path

import pytest

from pytest_sources._stash import SOURCES
from pytest_sources.source import Source, make_sources


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
