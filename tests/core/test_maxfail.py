import re
from types import SimpleNamespace

import pytest

from pytest_sources._core.discover import UNIVERSE
from pytest_sources._core.maxfail import LOG, SourceMaxfail, discard_log, shared_log
from pytest_sources._core.source import Source


@pytest.fixture
def failing(pytester):
    """Two sources against three tests. alice passes them all, bob fails them all."""
    for name in ("alice", "bob"):
        (pytester.path / "submissions" / name).mkdir(parents=True)
    pytester.makepyfile(
        """
        def test_one(source): assert source.name == "alice"
        def test_two(source): assert source.name == "alice"
        def test_three(source): assert source.name == "alice"
        """
    )
    return pytester


@pytest.fixture
def spread(pytester):
    """The same two sources against six tests, spread over three files."""
    for name in ("alice", "bob"):
        (pytester.path / "submissions" / name).mkdir(parents=True)
    body = """
        def test_one(source): assert source.name == "alice"
        def test_two(source): assert source.name == "alice"
        """
    pytester.makepyfile(test_first=body, test_second=body, test_third=body)
    return pytester


def workers_of(result, source):
    """The xdist workers that reported a test of the given source."""
    workers = set()
    for line in result.outlines:
        found = re.match(r"\[(gw\d+)\]", line)
        if found and f"[{source}]" in line:
            workers.add(found[1])
    return workers


class TestFailureBudget:
    """Spending a source's allowance of failures."""

    def test_a_failing_source_stops_at_the_limit(self, failing):
        result = failing.runpytest("--sources", "submissions/*", "-n", "0", "--sources-maxfail=1")

        result.assert_outcomes(passed=3, failed=1, skipped=2)

    def test_a_higher_limit_lets_more_through(self, failing):
        result = failing.runpytest("--sources", "submissions/*", "-n", "0", "--sources-maxfail=2")

        result.assert_outcomes(passed=3, failed=2, skipped=1)

    def test_zero_disables_it(self, failing):
        result = failing.runpytest("--sources", "submissions/*", "-n", "0")

        result.assert_outcomes(passed=3, failed=3)

    @pytest.mark.parametrize("workers", ["0", "2", "4"])
    def test_the_budget_is_per_source_not_per_process(self, failing, workers):
        """At -n 4 the two sources would otherwise be split, giving each half a budget."""
        result = failing.runpytest("--sources", "submissions/*", "-n", workers, "--sources-maxfail=1")

        result.assert_outcomes(passed=3, failed=1, skipped=2)


class TestWhatTheBudgetTouches:
    """Which results count, and which sources are affected."""

    def test_the_other_sources_are_unaffected(self, failing):
        """The point of the option: one bad submission does not end the run."""
        result = failing.runpytest("--sources", "submissions/*", "-n", "0", "--sources-maxfail=1", "-v")

        passed = [line for line in result.outlines if "PASSED" in line]
        assert len(passed) == 3
        assert all("submissions/alice" in line for line in passed)

    def test_setup_errors_count_towards_the_limit(self, pytester):
        (pytester.path / "submissions" / "alice").mkdir(parents=True)
        pytester.makepyfile(
            """
            import pytest

            @pytest.fixture
            def broken():
                raise RuntimeError("boom")

            def test_one(source, broken): ...
            def test_two(source, broken): ...
            """
        )

        result = pytester.runpytest("--sources", "submissions/*", "-n", "0", "--sources-maxfail=1")

        result.assert_outcomes(errors=1, skipped=1)

    def test_the_skip_reason_names_the_source_and_the_limit(self, failing):
        result = failing.runpytest("--sources", "submissions/*", "-n", "0", "--sources-maxfail=2", "-rs")

        result.stdout.fnmatch_lines(["*submissions/bob stopped after 2 failures*"])


class TestBudgetAcrossProcesses:
    """One budget between the processes a grouping mode splits a source over.

    The processes trade failures through a shared file, so what holds is that the
    source stops, not that it failed an exact number of times. Two workers can both
    fail before either sees the other's write, and a test already running when the
    limit is reached cannot be recalled.
    """

    def test_a_source_split_over_files_stops(self, spread):
        """--dist loadfile gives each of bob's three files a process of its own."""
        result = spread.runpytest(
            "--sources", "submissions/*", "--dist", "loadfile", "-n", "4", "--sources-maxfail=1", "-v"
        )

        assert len(workers_of(result, "submissions/bob")) > 1, "the source was never split"
        outcomes = result.parseoutcomes()
        assert outcomes.get("skipped", 0) >= 1
        assert outcomes.get("failed", 0) + outcomes.get("skipped", 0) == 6

    def test_the_other_sources_are_still_unaffected(self, spread):
        result = spread.runpytest(
            "--sources", "submissions/*", "--dist", "loadfile", "-n", "4", "--sources-maxfail=1", "-v"
        )

        passed = [line for line in result.outlines if "PASSED" in line]
        assert len(passed) == 6
        assert all("submissions/alice" in line for line in passed)

    def test_a_source_kept_in_one_process_spends_its_budget_exactly(self, spread):
        """The default mode never splits a source, so the boundary cannot be reached."""
        result = spread.runpytest("--sources", "submissions/*", "-n", "4", "--sources-maxfail=1")

        result.assert_outcomes(passed=6, failed=1, skipped=5)


def failure_of(source):
    """A report of a test of that source failing."""
    return SimpleNamespace(failed=True, when="call", nodeid=f"test_first.py::test_one[{source}]")


def item_of(source):
    """An item about to run, from a different file to the one that failed."""
    return SimpleNamespace(nodeid=f"test_second.py::test_one[{source}]")


class TestTheSharedLog:
    """Where the log the workers append to lives, and what reading it back settles."""

    @pytest.fixture
    def config(self, spread):
        """One run's config, carrying a single source, taking its log with it."""
        config = spread.parseconfig("--sources", "submissions/*", "--sources-maxfail=1")
        config.stash[UNIVERSE] = [Source(path=spread.path / "submissions" / "bob", id="submissions/bob")]
        yield config
        discard_log(config)

    def test_it_sits_outside_the_project_and_is_deleted_after_the_run(self, spread, config):
        log = shared_log(config)

        assert log.exists()
        assert spread.path not in log.parents
        assert shared_log(config) == log, "one log per run, not one per worker"

        discard_log(config)

        assert not log.exists()

    def test_a_worker_is_stopped_by_a_failure_another_worker_recorded(self, config):
        """The sharing itself, without the timing a distributed run brings.

        Two workers of one run, and only the first ever sees a test fail. The
        second skips on the strength of the first's line alone.
        """
        config.workerinput = {LOG: str(shared_log(config))}
        first, second = SourceMaxfail(config), SourceMaxfail(config)

        first.pytest_runtest_logreport(failure_of("submissions/bob"))

        with pytest.raises(pytest.skip.Exception, match="submissions/bob stopped after 1 failures"):
            second.pytest_runtest_setup(item_of("submissions/bob"))

    def test_a_worker_running_alone_keeps_its_own_count(self, config):
        """No log to share means the in-memory count, which is every -n 0 run."""
        alone = SourceMaxfail(config)

        alone.pytest_runtest_logreport(failure_of("submissions/bob"))

        with pytest.raises(pytest.skip.Exception):
            alone.pytest_runtest_setup(item_of("submissions/bob"))


class TestMarkerOnlyBudget:
    """The marker scan gives marker-only sources a failure budget, in workers too."""

    def test_the_budget_reaches_a_marker_source_under_workers(self, pytester):
        for name in ("alice", "bob"):
            (pytester.path / "submissions" / name).mkdir(parents=True)
        pytester.makepyfile(
            """
            import pytest

            pytestmark = pytest.mark.sources("submissions/*")

            def test_one(source): assert source.name == "alice"
            def test_two(source): assert source.name == "alice"
            def test_three(source): assert source.name == "alice"
            """
        )

        result = pytester.runpytest("--sources-maxfail=1", "-n", "2")

        result.assert_outcomes(passed=3, failed=1, skipped=2)
