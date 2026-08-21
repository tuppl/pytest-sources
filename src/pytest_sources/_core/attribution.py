from collections.abc import Container, Mapping, Sequence

import pytest

from pytest_sources._core.discover import universe
from pytest_sources._core.nodeid import UNFANNED, drop_group
from pytest_sources._core.source import Source

SOURCE_MAP = pytest.StashKey[dict[str, str]]()

ATTRIBUTE = "sources_source"


def source_map(config: pytest.Config) -> dict[str, str]:
    """The run's nodeid-to-source map, one dict shared by its builder and readers."""
    return config.stash.setdefault(SOURCE_MAP, {})


def record(items: Sequence[pytest.Item], config: pytest.Config) -> None:
    """
    Map each collected nodeid to the source its callspec carries.

    The callspec holds the real parameter value, so a source whose id cannot be
    read back out of the nodeid is still attributed in every process that
    collected.
    """
    ids = {source.id for source in universe(config)}
    mapping = source_map(config)
    for item in items:
        callspec = getattr(item, "callspec", None)
        value = callspec.params.get("source") if callspec is not None else None
        if isinstance(value, Source):
            mapping[item.nodeid] = value.id
        elif isinstance(value, str) and value in ids:
            mapping[item.nodeid] = value


def attributed(nodeid: str, mapping: Mapping[str, str], source_ids: Container[str]) -> str:
    """The map's source for a nodeid, or UNFANNED when it has none in the universe."""
    source = mapping.get(drop_group(nodeid), UNFANNED)
    return source if source and source in source_ids else UNFANNED


def carry(report: pytest.TestReport, mapping: Mapping[str, str]) -> None:
    """
    Put the attribution on the report itself, for readers that never collected.

    Only the process that collected holds the map, and the controller running the
    summary is not one of them. A report carries its own attributes across, so
    what the worker knew reaches the run that reports it.
    """
    source = mapping.get(drop_group(report.nodeid))
    if source:
        setattr(report, ATTRIBUTE, source)


def carried(report: pytest.TestReport, source_ids: Container[str]) -> str:
    """The attribution a report brought with it, or UNFANNED."""
    source = getattr(report, ATTRIBUTE, UNFANNED)
    return source if source and source in source_ids else UNFANNED
