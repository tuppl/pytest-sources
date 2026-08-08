import contextlib
import types

import pytest

from pytest_sources import _scheduling
from pytest_sources._scheduling import UNFANNED, source_of

SOURCE_IDS = {
    "submissions/alice",
    "submissions/alice2",
    "submissions/alice-alt",
    "submissions/my-source",
}


@pytest.fixture
def submissions(pytester):
    for name in ("alice", "bob", "carol"):
        directory = pytester.path / "submissions" / name
        directory.mkdir(parents=True)
        (directory / "solution.py").write_text(f"VALUE = {name!r}\n")
    pytester.makepyfile(
        """
        def test_one(source):
            assert source.import_module("solution").VALUE == source.name

        def test_two(source):
            assert (source / "solution.py").exists()
        """
    )
    return pytester


def worker_assignments(result):
    """Map each worker id to the set of sources it ran tests for."""
    assignments = {}
    for line in result.outlines:
        if "[gw" not in line or "PASSED" not in line:
            continue
        worker = line[line.index("[gw") + 1 : line.index("]")]
        source = line[line.rindex("[") + 1 : line.rindex("]")]
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


def drive_cmdline_main(config):
    """Run the hook wrapper's pre-yield half without starting a session."""
    generator = _scheduling.pytest_cmdline_main(config)
    next(generator)
    with contextlib.suppress(StopIteration):
        generator.send(0)


def fake_config(**attributes):
    config = types.SimpleNamespace(option=types.SimpleNamespace(numprocesses=None))
    config.__dict__.update(attributes)
    return config


@pytest.fixture
def three_sources(monkeypatch):
    monkeypatch.delenv("PYTEST_XDIST_WORKER", raising=False)
    monkeypatch.setattr(_scheduling, "resolve", lambda config: ["a", "b", "c"])


def test_sources_imply_one_worker_each(three_sources):
    config = fake_config()
    drive_cmdline_main(config)
    assert config.option.numprocesses == "auto"


def test_a_worker_never_starts_workers_of_its_own(three_sources):
    """An xdist worker re-enters this hook with numprocesses reset to None.

    Treating that as "unset" made every worker spawn a full set of its own,
    which multiplies until the machine runs out of memory.
    """
    config = fake_config(workerinput={"workerid": "gw0"})
    drive_cmdline_main(config)
    assert config.option.numprocesses is None


def test_a_descendant_of_a_worker_never_starts_workers_either(three_sources, monkeypatch):
    """PYTEST_XDIST_WORKER is inherited, so the guard holds at any depth.

    config.workerinput marks only the worker itself; a process it starts would
    not carry it.
    """
    monkeypatch.setenv("PYTEST_XDIST_WORKER", "gw0")
    config = fake_config()
    drive_cmdline_main(config)
    assert config.option.numprocesses is None


def test_a_missing_numprocesses_option_is_not_an_error(three_sources):
    """The option does not exist when xdist is disabled with -p no:xdist.

    Reading it must not raise; what the hook then writes is inert, because
    without xdist nothing reads it back.
    """
    config = fake_config()
    del config.option.numprocesses

    drive_cmdline_main(config)


@pytest.mark.parametrize("requested", [0, 2])
def test_an_explicit_worker_count_is_left_alone(three_sources, requested):
    config = fake_config()
    config.option.numprocesses = requested
    drive_cmdline_main(config)
    assert config.option.numprocesses == requested


def test_no_workers_are_forced_without_sources(monkeypatch):
    monkeypatch.setattr(_scheduling, "resolve", lambda config: [])
    config = fake_config()
    drive_cmdline_main(config)
    assert config.option.numprocesses is None


def test_one_worker_per_source(submissions):
    result = submissions.runpytest("--sources", "submissions/*", "-n", "3", "-v")
    result.assert_outcomes(passed=6)
    assignments = worker_assignments(result)
    assert len(assignments) == 3
    assert all(len(sources) == 1 for sources in assignments.values())


def test_fewer_workers_than_sources_still_pins_each_source(submissions):
    result = submissions.runpytest("--sources", "submissions/*", "-n", "2", "-v")
    result.assert_outcomes(passed=6)
    assignments = worker_assignments(result)
    assert len(assignments) == 2
    # No source may be split across workers.
    seen = [source for sources in assignments.values() for source in sources]
    assert sorted(seen) == [
        "submissions/alice",
        "submissions/bob",
        "submissions/carol",
    ]


def test_single_worker_runs_every_source(submissions):
    result = submissions.runpytest("--sources", "submissions/*", "-n", "1")
    result.assert_outcomes(passed=6)


def test_auto_starts_one_worker_per_source(submissions):
    """Assert on workers started, not on workers that reported.

    xdist's own answer to -n auto is the CPU count. Counting the workers that
    ran tests cannot tell the two apart, because the scheduler only ever hands
    out one group per source and the surplus workers stay idle.
    """
    result = submissions.runpytest("--sources", "submissions/*", "-n", "auto", "-v")
    result.assert_outcomes(passed=6)
    result.stdout.fnmatch_lines(["*created: 3/3 workers*"])


def test_auto_num_workers_is_the_source_count(submissions):
    config = submissions.parseconfigure("--sources", "submissions/*")
    assert _scheduling.pytest_xdist_auto_num_workers(config) == 3


def test_auto_num_workers_defers_to_xdist_without_sources(pytester):
    config = pytester.parseconfigure()
    assert _scheduling.pytest_xdist_auto_num_workers(config) is None


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
