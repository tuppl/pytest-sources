import sys

import pytest

from pytest_sources import source as source_module


@pytest.fixture(autouse=True)
def isolate_imports():
    original_path = list(sys.path)
    original_modules = set(sys.modules)
    yield
    source_module._active = None
    sys.path[:] = original_path
    for name in set(sys.modules) - original_modules:
        del sys.modules[name]


@pytest.fixture
def submissions(pytester):
    for name, value in (("alice", 1), ("bob", 2)):
        directory = pytester.path / "submissions" / name
        directory.mkdir(parents=True)
        (directory / "solution.py").write_text(f"VALUE = {value}\n")
    return pytester


def collected_ids(result):
    return [line for line in result.outlines if "::test_" in line]


def test_fans_a_test_out_over_every_source(submissions):
    submissions.makepyfile("def test_x(source): pass")
    result = submissions.runpytest("--sources", "submissions/*", "-n", "0")
    result.assert_outcomes(passed=2)


def test_ids_are_root_relative(submissions):
    submissions.makepyfile("def test_x(source): pass")
    result = submissions.runpytest("--sources", "submissions/*", "-n", "0", "--collect-only", "-q")
    assert "test_x[submissions/alice]" in result.stdout.str()
    assert "test_x[submissions/bob]" in result.stdout.str()


def test_fans_out_a_test_that_never_requests_source(submissions):
    submissions.makepyfile("def test_x(): pass")
    result = submissions.runpytest("--sources", "submissions/*", "-n", "0")
    result.assert_outcomes(passed=2)


def test_no_sources_marker_runs_the_test_once(submissions):
    submissions.makepyfile(
        """
        import pytest

        @pytest.mark.no_sources
        def test_x(): pass
        """
    )
    result = submissions.runpytest("--sources", "submissions/*", "-n", "0")
    result.assert_outcomes(passed=1)


def test_sources_marker_replaces_the_command_line_set(submissions):
    submissions.makepyfile(
        """
        import pytest

        @pytest.mark.sources("submissions/alice")
        def test_x(source): pass
        """
    )
    result = submissions.runpytest("--sources", "submissions/*", "-n", "0", "--collect-only", "-q")
    assert "test_x[submissions/alice]" in result.stdout.str()
    assert "submissions/bob" not in result.stdout.str()


def test_sources_marker_works_without_the_command_line_option(submissions):
    submissions.makepyfile(
        """
        import pytest

        @pytest.mark.sources("submissions/*")
        def test_x(source): pass
        """
    )
    result = submissions.runpytest()
    result.assert_outcomes(passed=2)


def test_requesting_source_without_any_sources_skips(submissions):
    submissions.makepyfile("def test_x(source): pass")
    result = submissions.runpytest("-rs")
    result.assert_outcomes(skipped=1)
    result.stdout.fnmatch_lines(["*no sources configured*"])


def test_session_scope_groups_tests_by_source(submissions):
    submissions.makepyfile(
        test_a="def test_one(source): pass",
        test_b="def test_two(source): pass",
    )
    # -n 0: reported order is only meaningful in a single process.
    result = submissions.runpytest("--sources", "submissions/*", "-n", "0", "-v")
    ids = [line.split("[")[1].split("]")[0] for line in collected_ids(result)]
    assert ids == [
        "submissions/alice",
        "submissions/alice",
        "submissions/bob",
        "submissions/bob",
    ]


def test_keyword_selection_by_source_name(submissions):
    submissions.makepyfile("def test_x(source): pass")
    # -n 0: workers deselect locally, so the controller reports no deselections.
    result = submissions.runpytest("--sources", "submissions/*", "-n", "0", "-k", "alice")
    result.assert_outcomes(passed=1, deselected=1)


def test_each_source_imports_its_own_module(submissions):
    submissions.makepyfile(
        """
        def test_value(source):
            expected = {"alice": 1, "bob": 2}[source.name]
            assert source.import_module("solution").VALUE == expected
        """
    )
    result = submissions.runpytest("--sources", "submissions/*", "-n", "0")
    result.assert_outcomes(passed=2)


def test_plain_import_of_a_source_module_works_inside_a_test(submissions):
    submissions.makepyfile(
        """
        def test_value(source):
            import solution
            assert solution.VALUE == {"alice": 1, "bob": 2}[source.name]
        """
    )
    result = submissions.runpytest("--sources", "submissions/*", "-n", "0")
    result.assert_outcomes(passed=2)


def test_no_sources_applies_to_a_whole_module(submissions):
    submissions.makepyfile(
        """
        import pytest

        pytestmark = pytest.mark.no_sources

        def test_one(): pass
        def test_two(): pass
        """
    )
    result = submissions.runpytest("--sources", "submissions/*", "-n", "0")
    result.assert_outcomes(passed=2)


def test_the_sources_marker_takes_several_globs(pytester):
    for parent in ("submissions", "other"):
        (pytester.path / parent / "alice").mkdir(parents=True)
    pytester.makepyfile(
        """
        import pytest

        @pytest.mark.sources("submissions/*", "other/*")
        def test_x(source): pass
        """
    )
    result = pytester.runpytest("-n", "0", "--collect-only", "-q")
    assert "test_x[submissions/alice]" in result.stdout.str()
    assert "test_x[other/alice]" in result.stdout.str()
