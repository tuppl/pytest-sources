from collections import Counter

import pytest


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


class TestWorkerAssignment:
    """Which worker each source's tests are given to."""

    def test_one_worker_per_source(self, submissions):
        result = submissions.runpytest("--sources", "submissions/*", "-n", "3", "-v")
        result.assert_outcomes(passed=6)
        assignments = worker_assignments(result)
        assert len(assignments) == 3
        assert all(len(sources) == 1 for sources in assignments.values())

    def test_spare_workers_are_split_within_a_source(self, submissions):
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

    def test_a_worker_is_replaced_rather_than_reused(self, submissions):
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

    def test_single_worker_runs_every_source(self, submissions):
        result = submissions.runpytest("--sources", "submissions/*", "-n", "1")
        result.assert_outcomes(passed=6)

    def test_sources_sharing_a_basename_stay_separate(self, pytester):
        """submissions/alice and other/alice are different sources with distinct ids."""
        for parent in ("submissions", "other"):
            directory = pytester.path / parent / "alice"
            directory.mkdir(parents=True)
            (directory / "solution.py").write_text(f"WHERE = {parent!r}\n")
        pytester.makepyfile(
            """
            def test_which(source):
                assert source.import_module("solution").WHERE == source.id.split("/")[0]
            """
        )

        result = pytester.runpytest("--sources", "submissions/*", "--sources", "other/*", "-n", "2", "-v")

        result.assert_outcomes(passed=2)
        assignments = worker_assignments(result)
        assert sorted(source for sources in assignments.values() for source in sources) == [
            "other/alice",
            "submissions/alice",
        ]

    def test_unfanned_tests_still_run_under_xdist(self, submissions):
        submissions.makepyfile(
            test_helper="""
            import pytest

            @pytest.mark.no_sources
            def test_helper(): pass
            """
        )
        result = submissions.runpytest("--sources", "submissions/*", "-n", "3")
        result.assert_outcomes(passed=7)


class TestProcessIsolation:
    """The guarantee the scheduler exists for."""

    @pytest.mark.parametrize("workers", ["1", "2", "3"])
    def test_each_source_gets_its_own_process(self, pytester, tmp_path, monkeypatch, workers):
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

    def test_a_crashing_source_does_not_take_the_others_down(self, pytester):
        """A worker killed mid-test is replaced by xdist, and the run carries on.

        --max-worker-restart=0 bounds it: the crash is reported once rather than
        retried, since LoadScopeScheduling returns the whole work item to the queue
        and the next worker crashes on it again.
        """
        for name in ("alice", "bob"):
            (pytester.path / "submissions" / name).mkdir(parents=True)
        pytester.makepyfile(
            """
            import os

            def test_crashes(source):
                if source.name == "alice":
                    os._exit(1)

            def test_survives(source):
                assert True
            """
        )

        result = pytester.runpytest("--sources", "submissions/*", "-n", "2", "--max-worker-restart=0")

        result.assert_outcomes(passed=2, failed=1)
        result.stdout.fnmatch_lines(["*crashed while running*submissions/alice*"])
