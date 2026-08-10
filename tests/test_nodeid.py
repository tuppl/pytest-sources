"""How the bracket of a fanned-out nodeid is built.

pytest joins parameter ids with "-", which is also legal in a directory name.
_nodeid replaces that separator with "+" while sources are in use, and _option
refuses sources containing it, so the source is always everything before the
first "+".

Covers how the bracket is written, and source_of reading it back.

    uv run pytest tests/test_nodeid.py -v
"""

import pytest

from pytest_sources._nodeid import DELIMITER, UNFANNED, source_of


def make_sources(pytester, *names):
    for name in names:
        directory = pytester.path / "submissions" / name
        directory.mkdir(parents=True)
        (directory / "solution.py").write_text("X = 1\n")


def collect(pytester, *args):
    result = pytester.runpytest("--collect-only", "-q", *args)
    return [line for line in result.outlines if "::" in line]


def collect_sources(pytester):
    return collect(pytester, "--sources", "submissions/*")


def brackets(nodeids):
    return {nodeid[nodeid.index("[") :] for nodeid in nodeids}


def test_source_id_is_the_whole_bracket_when_there_are_no_parameters(pytester):
    make_sources(pytester, "alice")
    pytester.makepyfile("def test_x(source): ...")

    (nodeid,) = collect_sources(pytester)
    assert nodeid.endswith("[submissions/alice]")


def test_a_parameter_is_appended_after_the_delimiter(pytester):
    make_sources(pytester, "alice")
    pytester.makepyfile(
        """
        import pytest

        @pytest.mark.parametrize("n", [1])
        def test_x(source, n): ...
        """
    )

    (nodeid,) = collect_sources(pytester)
    assert nodeid.endswith("[submissions/alice+1]")


def test_every_parametrize_call_adds_another_delimiter(pytester):
    make_sources(pytester, "alice")
    pytester.makepyfile(
        """
        import pytest

        @pytest.mark.parametrize("mode", ["fast"])
        @pytest.mark.parametrize("n", [1])
        def test_x(source, n, mode): ...
        """
    )

    (nodeid,) = collect_sources(pytester)
    assert nodeid.endswith("[submissions/alice+1+fast]")


def test_values_within_one_parametrize_call_are_still_joined_with_a_dash(pytester):
    """Only the join between parametrize calls is replaced."""
    make_sources(pytester, "alice")
    pytester.makepyfile(
        """
        import pytest

        @pytest.mark.parametrize("a,b", [(1, 2)])
        def test_x(source, a, b): ...
        """
    )

    (nodeid,) = collect_sources(pytester)
    assert nodeid.endswith("[submissions/alice+1-2]")


def test_an_appended_parameter_is_distinct_from_a_dashed_source(pytester):
    make_sources(pytester, "alice", "alice-1")
    pytester.makepyfile(
        """
        import pytest

        @pytest.mark.parametrize("n", [1])
        def test_x(source, n): ...
        """
    )

    # Joined with "-" both of these would render as [submissions/alice-1].
    assert brackets(collect_sources(pytester)) == {
        "[submissions/alice+1]",
        "[submissions/alice-1+1]",
    }


def test_explicitly_given_parameter_ids_are_joined_the_same_way(pytester):
    make_sources(pytester, "alice")
    pytester.makepyfile(
        """
        import pytest

        @pytest.mark.parametrize("n", [pytest.param(1, id="one")])
        def test_x(source, n): ...
        """
    )

    (nodeid,) = collect_sources(pytester)
    assert nodeid.endswith("[submissions/alice+one]")


def test_unfanned_tests_are_joined_with_the_delimiter_too(pytester):
    """The patch is process-wide, so no_sources tests are affected as well."""
    make_sources(pytester, "alice")
    pytester.makepyfile(
        """
        import pytest

        @pytest.mark.no_sources
        @pytest.mark.parametrize("mode", ["fast"])
        @pytest.mark.parametrize("n", [1])
        def test_x(n, mode): ...
        """
    )

    (nodeid,) = collect_sources(pytester)
    assert nodeid.endswith("[1+fast]")


def test_ids_are_untouched_without_sources(pytester):
    pytester.makepyfile(
        """
        import pytest

        @pytest.mark.parametrize("mode", ["fast"])
        @pytest.mark.parametrize("n", [1])
        def test_x(n, mode): ...
        """
    )

    (nodeid,) = collect(pytester)
    assert nodeid.endswith("[1-fast]")


def test_sources_from_the_ini_file_also_change_the_delimiter(pytester):
    make_sources(pytester, "alice")
    pytester.makeini("[pytest]\nsources = submissions/*\n")
    pytester.makepyfile(
        """
        import pytest

        @pytest.mark.parametrize("n", [1])
        def test_x(source, n): ...
        """
    )

    (nodeid,) = collect(pytester)
    assert nodeid.endswith("[submissions/alice+1]")


def test_a_source_containing_the_delimiter_is_rejected(pytester):
    (pytester.path / "submissions" / f"a{DELIMITER}b").mkdir(parents=True)

    with pytest.raises(pytest.UsageError, match="may not appear in a source path"):
        pytester.parseconfigure("--sources", "submissions/*")


def test_the_original_delimiter_is_restored_on_unconfigure(pytester):
    """Nested in-process runs must not leak the patch into the outer session."""
    from _pytest.python import CallSpec2

    before = CallSpec2.id

    make_sources(pytester, "alice")
    pytester.makepyfile("def test_x(source): ...")
    collect_sources(pytester)

    assert CallSpec2.id is before
    assert CallSpec2(params={}, indices={}, _arg2scope={}, _idlist=["a", "b"]).id == "a-b"


SOURCE_IDS = {
    "submissions/alice",
    "submissions/alice2",
    "submissions/alice-alt",
    "submissions/my-source",
}


def test_matches_a_lone_source():
    assert source_of("t.py::test_x[submissions/alice]", SOURCE_IDS) == "submissions/alice"


def test_matches_when_the_test_has_further_parameters():
    assert source_of("t.py::test_x[submissions/alice+1]", SOURCE_IDS) == "submissions/alice"


def test_matches_a_source_whose_name_contains_a_dash():
    assert source_of("t.py::test_x[submissions/my-source+1]", SOURCE_IDS) == "submissions/my-source"


def test_matches_a_dashed_parameter_value():
    assert source_of("t.py::test_x[submissions/alice+a-b]", SOURCE_IDS) == "submissions/alice"


def test_distinguishes_a_dashed_source_from_a_dashed_parameter():
    # Without the reserved delimiter both of these would read as
    # submissions/alice-alt.
    assert source_of("t.py::test_x[submissions/alice-alt+1]", SOURCE_IDS) == "submissions/alice-alt"
    assert source_of("t.py::test_x[submissions/alice+alt]", SOURCE_IDS) == "submissions/alice"


def test_unparametrised_test_belongs_to_no_source():
    assert source_of("t.py::test_x", SOURCE_IDS) == UNFANNED


def test_unknown_parameter_belongs_to_no_source():
    assert source_of("t.py::test_x[3]", SOURCE_IDS) == UNFANNED


def test_matches_a_bare_nodeid_without_a_module_separator():
    assert source_of("test_x[submissions/alice]", SOURCE_IDS) == "submissions/alice"


def test_ignores_brackets_in_the_file_path():
    assert source_of("dir[1]/t.py::test_x[submissions/alice]", SOURCE_IDS) == "submissions/alice"
