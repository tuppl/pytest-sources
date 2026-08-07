import pytest

from pytest_sources.source import Source

SOURCES = pytest.StashKey[list[Source]]()
MARKER_SOURCES = pytest.StashKey[dict[tuple[str, ...], list[Source]]]()
