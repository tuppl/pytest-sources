import glob
from collections.abc import Sequence
from pathlib import Path

import pytest


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
                f"sources glob matched {len(matches)} path(s), "
                f"none of them directories: {pattern!r}"
            )
        sources |= directories

    return sorted(sources)
