import pytest


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


class TestMarkerOnlyBudget:
    """--sources-scan gives marker-only sources a failure budget, in workers too."""

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
