from collections import Counter
from enum import StrEnum

import pytest

from pytest_sources._core.discover import resolve
from pytest_sources._core.nodeid import delimiter, drop_group, source_of


class Summary(StrEnum):
    """Which view of the results to print after the run."""

    COUNTS = "counts"
    SOURCES = "sources"
    TESTS = "tests"
    NONE = "none"


class Outcome(StrEnum):
    """What a test did, folded from its three phase reports."""

    PASSED = "passed"
    FAILED = "failed"
    ERROR = "error"
    SKIPPED = "skipped"
    XFAILED = "xfailed"
    XPASSED = "xpassed"


CHARACTERS = {
    Outcome.PASSED: ".",
    Outcome.FAILED: "F",
    Outcome.ERROR: "E",
    Outcome.SKIPPED: "s",
    Outcome.XFAILED: "x",
    Outcome.XPASSED: "X",
}
MISSING = "-"


class SourceSummary:
    """Record every outcome per source and print one of three views of it."""

    def __init__(self, config: pytest.Config) -> None:
        self._sources = [source.id for source in resolve(config)]
        self._source_ids = set(self._sources)
        self._style = Summary(config.getoption("sources_summary"))
        self._results: dict[str, dict[str, Outcome]] = {source: {} for source in self._sources}
        self._duration: dict[str, float] = dict.fromkeys(self._sources, 0.0)

    @pytest.hookimpl
    def pytest_runtest_logreport(self, report: pytest.TestReport) -> None:
        source = source_of(report.nodeid, self._source_ids)
        if not source:
            return

        self._duration[source] += report.duration
        outcome = _outcome(report)
        if outcome is not None:
            self._results[source][_test_of(report.nodeid, source)] = outcome

    @pytest.hookimpl
    def pytest_terminal_summary(self, terminalreporter) -> None:
        if not self._results:
            return

        terminalreporter.write_sep("=", "sources")
        if self._style is Summary.COUNTS:
            self._write_counts(terminalreporter)
        else:
            self._write_grid(terminalreporter)

    def _write_counts(self, terminalreporter) -> None:
        width = max(len("source"), *(len(source) for source in self._sources))
        terminalreporter.write_line(_counts_row("source", list(Outcome), "time", width))

        for source in self._sources:
            tally = Counter(self._results[source].values())
            values = [str(tally[outcome]) for outcome in Outcome]
            failed = bool(tally[Outcome.FAILED] or tally[Outcome.ERROR])
            terminalreporter.write_line(
                _counts_row(source, values, f"{self._duration[source]:.2f}s", width),
                red=failed,
                green=not failed,
            )

    def _write_grid(self, terminalreporter) -> None:
        tests = sorted({test for results in self._results.values() for test in results})

        if self._style is Summary.SOURCES:
            corner, rows, columns = "source", self._sources, tests
        else:
            corner, rows, columns = "test", tests, self._sources

        def cell(row: str, column: str) -> str:
            source, test = (row, column) if self._style is Summary.SOURCES else (column, row)
            outcome = self._results[source].get(test)
            return CHARACTERS[outcome] if outcome else MISSING

        # Only the headings are shortened. A row has the width to spare, and a
        # source id abbreviated in the left column is the one a grader records.
        headings = [_shorten(columns)[column] for column in columns]
        width = max(len(corner), *(len(row) for row in rows))
        widths = [max(len(heading), 1) for heading in headings]

        terminalreporter.write_line(_grid_row(corner, headings, width, widths))
        for row in rows:
            cells = [cell(row, column) for column in columns]
            terminalreporter.write_line(_grid_row(row, cells, width, widths))

        legend = "  ".join(f"{character} {outcome}" for outcome, character in CHARACTERS.items())
        terminalreporter.write_line(f"{legend}  {MISSING} not run")


def _counts_row(source: str, values, duration: str, width: int) -> str:
    counts = "  ".join(f"{value:>{len(outcome)}}" for value, outcome in zip(values, Outcome, strict=True))
    return f"{source:<{width}}  {counts}  {duration:>7}"


def _grid_row(label: str, cells, width: int, widths) -> str:
    body = "  ".join(f"{cell:>{size}}" for cell, size in zip(cells, widths, strict=True))
    return f"{label:<{width}}  {body}"


def _shorten(labels) -> dict[str, str]:
    """Drop the leading path from each label, unless that would merge two of them."""
    short = {label: label.rsplit("/", 1)[-1].rsplit("::", 1)[-1] for label in labels}
    if len(set(short.values())) < len(short):
        return {label: label for label in labels}
    return short


def _test_of(nodeid: str, source: str) -> str:
    """The nodeid with its source taken out, so one test lines up across sources."""
    head, bracket, params = drop_group(nodeid).partition("[")
    if not bracket:
        return head
    rest = params.removesuffix("]").removeprefix(source).removeprefix(delimiter())
    return f"{head}[{rest}]" if rest else head


def _outcome(report: pytest.TestReport) -> Outcome | None:
    """
    Fold a phase report into one outcome, or nothing.
    """
    if hasattr(report, "wasxfail"):
        return Outcome.XPASSED if report.passed else Outcome.XFAILED

    if report.when == "call":
        return Outcome(report.outcome) if report.outcome in Outcome else None
    if report.failed:
        return Outcome.ERROR
    if report.when == "setup" and report.skipped:
        return Outcome.SKIPPED
    return None
