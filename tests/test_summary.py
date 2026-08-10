import pytest


@pytest.fixture
def mixed(pytester):
    """Two sources whose results differ, so the columns cannot be confused."""
    for name in ("alice", "bob"):
        (pytester.path / "submissions" / name).mkdir(parents=True)
    (pytester.path / "submissions" / "alice" / "solution.py").write_text("VALUE = 1\n")
    (pytester.path / "submissions" / "bob" / "solution.py").write_text("VALUE = 2\n")
    pytester.makepyfile(
        """
        import pytest

        def test_value(source):
            assert source.import_module("solution").VALUE == 1

        def test_always(source): ...

        @pytest.mark.skip(reason="not ready")
        def test_skipped(source): ...
        """
    )
    return pytester


def rows(result):
    """The table body, keyed by source: passed, failed, error, skipped."""
    found = {}
    for line in result.outlines:
        if line.startswith("submissions/"):
            name, *values = line.split()
            found[name] = values[:4]
    return found


def test_reports_a_row_for_each_source(mixed):
    result = mixed.runpytest("--sources", "submissions/*", "-n", "0")

    assert rows(result) == {
        "submissions/alice": ["2", "0", "0", "1"],
        "submissions/bob": ["1", "1", "0", "1"],
    }


def test_each_row_ends_with_a_duration(mixed):
    result = mixed.runpytest("--sources", "submissions/*", "-n", "0")

    durations = [line.split()[-1] for line in result.outlines if line.startswith("submissions/")]
    assert durations and all(value.endswith("s") for value in durations)


def test_counts_setup_failures_as_errors(pytester):
    (pytester.path / "submissions" / "alice").mkdir(parents=True)
    pytester.makepyfile(
        """
        import pytest

        @pytest.fixture
        def broken():
            raise RuntimeError("boom")

        def test_x(source, broken): ...
        """
    )

    result = pytester.runpytest("--sources", "submissions/*", "-n", "0")

    assert rows(result)["submissions/alice"] == ["0", "0", "1", "0"]


def test_the_table_is_absent_without_sources(pytester):
    pytester.makepyfile("def test_x(): ...")

    result = pytester.runpytest()

    assert "sources" not in "".join(line for line in result.outlines if line.startswith("="))


def test_a_source_with_no_tests_still_gets_a_row(mixed):
    """A source whose tests were all deselected, or whose worker died, reads zero."""
    result = mixed.runpytest("--sources", "submissions/*", "-n", "0", "-k", "alice")

    assert rows(result)["submissions/bob"] == ["0", "0", "0", "0"]


def test_the_totals_are_the_same_under_xdist(mixed):
    """Reports reach the controller either way, so distribution cannot change them."""
    serial = rows(mixed.runpytest("--sources", "submissions/*", "-n", "0"))
    distributed = rows(mixed.runpytest("--sources", "submissions/*", "-n", "2"))

    assert serial == distributed
