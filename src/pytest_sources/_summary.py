from collections import Counter

import pytest

from pytest_sources._discover import resolve
from pytest_sources._nodeid import source_of

COLUMNS = ("passed", "failed", "error", "skipped")


@pytest.hookimpl
def pytest_configure(config: pytest.Config) -> None:
    # Workers report to the controller, which is where the totals are wanted.
    if hasattr(config, "workerinput"):
        return
    # Nothing ran, so a table of zeroes would only be misleading.
    if config.getoption("collectonly", False):
        return
    if resolve(config):
        config.pluginmanager.register(SourceSummary(config), "pytest_sources_summary")


class SourceSummary:
    """Tally results per source and print them as a table after the run."""

    def __init__(self, config: pytest.Config) -> None:
        sources = [source.id for source in resolve(config)]
        self._source_ids = set(sources)
        self._tally: dict[str, Counter[str]] = {source: Counter() for source in sources}
        self._duration: dict[str, float] = dict.fromkeys(sources, 0.0)

    @pytest.hookimpl
    def pytest_runtest_logreport(self, report: pytest.TestReport) -> None:
        source = source_of(report.nodeid, self._source_ids)
        if not source:
            return

        self._duration[source] += report.duration
        outcome = _outcome(report)
        if outcome is not None:
            self._tally[source][outcome] += 1

    @pytest.hookimpl
    def pytest_terminal_summary(self, terminalreporter) -> None:
        if not self._tally:
            return

        width = max(len("source"), *(len(source) for source in self._tally))
        terminalreporter.write_sep("=", "sources")
        terminalreporter.write_line(_row("source", COLUMNS, "time", width))

        for source, counts in self._tally.items():
            values = [str(counts[column]) for column in COLUMNS]
            duration = f"{self._duration[source]:.2f}s"
            failed = bool(counts["failed"] or counts["error"])
            terminalreporter.write_line(
                _row(source, values, duration, width), red=failed, green=not failed
            )


def _row(source: str, values, duration: str, width: int) -> str:
    counts = "  ".join(
        f"{value:>{len(column)}}" for value, column in zip(values, COLUMNS, strict=True)
    )
    return f"{source:<{width}}  {counts}  {duration:>7}"


def _outcome(report: pytest.TestReport) -> str | None:
    """Fold a phase report into one of the columns, or nothing.

    A test reports three times. Only the call decides pass or fail; a setup or
    teardown that blows up is an error, and a skip is usually raised in setup.
    """
    if report.when == "call":
        return report.outcome
    if report.failed:
        return "error"
    if report.when == "setup" and report.skipped:
        return "skipped"
    return None
