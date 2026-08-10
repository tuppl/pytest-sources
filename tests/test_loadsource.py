from collections import Counter

import pytest

from pytest_sources.loadsource import UNFANNED, source_of

SOURCE_IDS = {
    "submissions/alice",
    "submissions/alice2",
    "submissions/alice-alt",
    "submissions/my-source",
}


def worker_assignments(result):
    """Map each worker id to the set of sources it ran tests for."""
    assignments = {}
    for line in result.outlines:
        if "[gw" not in line or "PASSED" not in line:
            continue
        worker = line[line.index("[gw") + 1 : line.index("]")]
        source = line[line.rindex("[") + 1 : line.rindex("]")].split("+")[0]
        assignments.setdefault(worker, set()).add(source)
    return assignments


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


def test_one_worker_per_source(submissions):
    result = submissions.runpytest("--sources", "submissions/*", "-n", "3", "-v")
    result.assert_outcomes(passed=6)
    assignments = worker_assignments(result)
    assert len(assignments) == 3
    assert all(len(sources) == 1 for sources in assignments.values())


def test_spare_workers_are_split_within_a_source(submissions):
    """Three sources over six workers: two workers each, none of them shared.

    Splitting a source is safe because every worker holding it activates that
    source and no other, so sys.path and sys.modules stay clean.
    """
    result = submissions.runpytest("--sources", "submissions/*", "-n", "6", "-v")
    result.assert_outcomes(passed=6)

    assignments = worker_assignments(result)
    assert len(assignments) == 6
    assert all(len(sources) == 1 for sources in assignments.values())
    assert Counter(next(iter(sources)) for sources in assignments.values()) == {
        "submissions/alice": 2,
        "submissions/bob": 2,
        "submissions/carol": 2,
    }


def test_a_worker_is_replaced_rather_than_reused(submissions):
    """Two slots, three sources, so a slot has to take a second source.

    It does not reuse the process. The finished worker exits and a replacement
    starts, giving three worker ids from two concurrent slots.
    """
    result = submissions.runpytest("--sources", "submissions/*", "-n", "2", "-v")
    result.assert_outcomes(passed=6)

    assignments = worker_assignments(result)
    assert len(assignments) == 3
    assert all(len(sources) == 1 for sources in assignments.values())

    seen = [source for sources in assignments.values() for source in sources]
    assert sorted(seen) == [
        "submissions/alice",
        "submissions/bob",
        "submissions/carol",
    ]


def test_single_worker_runs_every_source(submissions):
    result = submissions.runpytest("--sources", "submissions/*", "-n", "1")
    result.assert_outcomes(passed=6)


@pytest.mark.parametrize("workers", ["1", "2", "3"])
def test_each_source_gets_its_own_process(pytester, tmp_path, monkeypatch, workers):
    """The guarantee itself: one interpreter per source, at any worker count.

    Worker stdout is not forwarded, so each test records its pid to a file.
    """
    monkeypatch.setenv("PIDDIR", str(tmp_path))
    for name in ("alice", "bob", "carol"):
        (pytester.path / "submissions" / name).mkdir(parents=True)
    pytester.makepyfile(
        """
        import os, pathlib

        def test_pid(source):
            pathlib.Path(os.environ["PIDDIR"], source.name).write_text(str(os.getpid()))
        """
    )

    result = pytester.runpytest("--sources", "submissions/*", "-n", workers)
    result.assert_outcomes(passed=3)

    pids = {path.read_text() for path in tmp_path.iterdir()}
    assert len(pids) == 3


def test_unfanned_tests_still_run_under_xdist(submissions):
    submissions.makepyfile(
        test_helper="""
        import pytest

        @pytest.mark.no_sources
        def test_helper(): pass
        """
    )
    result = submissions.runpytest("--sources", "submissions/*", "-n", "3")
    result.assert_outcomes(passed=7)
