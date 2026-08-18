import os
import tempfile
from collections import Counter
from pathlib import Path

import pytest

from pytest_sources._core.discover import universe
from pytest_sources._core.nodeid import source_of

LOG = "sources_maxfail_log"

SHARED_LOG = pytest.StashKey[Path]()


def shared_log(config: pytest.Config) -> Path:
    """
    The run's failure log, created on the controller the first time a worker asks.

    Kept in the system temp directory and deleted at the end of the run. pytest's
    basetemp would outlive the run for no gain and follows --basetemp wherever the
    user points it, including into their project.
    """
    if SHARED_LOG not in config.stash:
        handle, path = tempfile.mkstemp(prefix="pytest-sources-maxfail-", suffix=".log")
        os.close(handle)
        config.stash[SHARED_LOG] = Path(path)
    return config.stash[SHARED_LOG]


def discard_log(config: pytest.Config) -> None:
    """Remove the run's failure log, if one was ever created."""
    log = config.stash.get(SHARED_LOG, None)
    if log is not None:
        del config.stash[SHARED_LOG]
        log.unlink(missing_ok=True)


class SourceMaxfail:
    """Skip a source's remaining tests once enough of them have failed.

    Counts per source rather than per process, so it reads the same whether
    every source has its own worker or they all share one under -n 0.

    Workers append their failures to one log for the whole run and count the lines
    back, so a source spread over several processes spends a single budget between
    them. A worker holds the budget in memory when it has no log to share, which is
    every process of an undistributed run.
    """

    def __init__(self, config: pytest.Config) -> None:
        self._limit = config.getoption("sources_maxfail")
        self._source_ids = {source.id for source in universe(config)}
        self._failures: Counter[str] = Counter()
        self._log = _worker_log(config)
        self._cursor = 0

    @pytest.hookimpl(tryfirst=True)
    def pytest_runtest_setup(self, item: pytest.Item) -> None:
        source = source_of(item.nodeid, self._source_ids)
        if not source:
            return

        self._catch_up()
        if self._failures[source] >= self._limit:
            pytest.skip(f"{source} stopped after {self._limit} failures")

    @pytest.hookimpl
    def pytest_runtest_logreport(self, report: pytest.TestReport) -> None:
        # A teardown failure is not counted: the test itself already reported,
        # and counting both would spend two of the budget on one test.
        if not report.failed or report.when not in ("call", "setup"):
            return

        source = source_of(report.nodeid, self._source_ids)
        if not source:
            return

        if self._log is None:
            self._failures[source] += 1
        else:
            _append(self._log, source)

    def _catch_up(self) -> None:
        """
        Fold everything appended since the last look into the count.

        Reading from a cursor keeps this to the handful of bytes another process
        may have written between two tests, rather than the whole log each time.
        """
        if self._log is None:
            return

        with self._log.open("rb") as handle:
            handle.seek(self._cursor)
            appended = handle.read()

        # A line without its newline is a write still in flight.
        complete = appended.rfind(b"\n") + 1
        self._cursor += complete
        self._failures.update(line.decode() for line in appended[:complete].splitlines())


def _worker_log(config: pytest.Config) -> Path | None:
    """The log this worker shares with the rest of the run, or None if it runs alone."""
    path = getattr(config, "workerinput", {}).get(LOG)
    return Path(path) if path else None


def _append(log: Path, source: str) -> None:
    """
    Record one failure.

    An O_APPEND write of a small buffer lands whole, so concurrent workers never
    interleave and no process has to lock or rewrite what the others put there.
    """
    handle = os.open(log, os.O_WRONLY | os.O_APPEND | getattr(os, "O_BINARY", 0))
    try:
        os.write(handle, f"{source}\n".encode())
    finally:
        os.close(handle)
