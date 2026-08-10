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


def section(result):
    """The lines between the sources separator and whatever follows it."""
    lines = result.outlines
    start = next(i for i, line in enumerate(lines) if line.startswith("=") and " sources " in line)
    body = []
    for line in lines[start + 1 :]:
        if line.startswith("="):
            break
        body.append(line)
    return body


def rows(result):
    """The counts body, keyed by source: passed, failed, error, skipped."""
    return {
        line.split()[0]: line.split()[1:5]
        for line in section(result)[1:]  # drop the header
    }


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


def grid(result):
    """The grid body, keyed by row label, header and legend removed."""
    body = section(result)[1:-1]
    return {line.split()[0]: line.split()[1:] for line in body}


def test_sources_grid_puts_a_source_on_each_row(mixed):
    result = mixed.runpytest("--sources", "submissions/*", "-n", "0", "--sources-summary=sources")

    assert grid(result) == {
        "submissions/alice": [".", "s", "."],
        "submissions/bob": [".", "s", "F"],
    }


def test_tests_grid_is_the_transpose(mixed):
    result = mixed.runpytest("--sources", "submissions/*", "-n", "0", "--sources-summary=tests")

    rows = grid(result)
    assert [cells[0] for cells in rows.values()] == [".", "s", "."]
    assert [cells[1] for cells in rows.values()] == [".", "s", "F"]


def test_a_grid_explains_its_characters(mixed):
    result = mixed.runpytest("--sources", "submissions/*", "-n", "0", "--sources-summary=sources")

    result.stdout.fnmatch_lines(["*. passed*F failed*E error*s skipped*- not run*"])


def test_none_prints_no_summary(mixed):
    result = mixed.runpytest("--sources", "submissions/*", "-n", "0", "--sources-summary=none")

    assert not any("= sources =" in line for line in result.outlines)


def test_an_unknown_summary_style_is_rejected(pytester):
    result = pytester.runpytest("--sources-summary=matrix")

    assert result.ret != 0
    result.stderr.fnmatch_lines(["*invalid choice*"])


def test_a_test_missing_from_a_source_reads_as_not_run(pytester):
    """A source whose worker died mid-item leaves gaps rather than false passes."""
    for name in ("alice", "bob"):
        (pytester.path / "submissions" / name).mkdir(parents=True)
    pytester.makepyfile(
        """
        import pytest

        @pytest.mark.sources("submissions/alice")
        def test_only_alice(source): ...

        def test_both(source): ...
        """
    )

    result = pytester.runpytest("--sources", "submissions/*", "-n", "0", "--sources-summary=sources")

    assert grid(result)["submissions/bob"] == [".", "-"]
