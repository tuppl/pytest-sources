import types
from collections import Counter

import pytest

from pytest_sources._schedule import SourceScheduling, pytest_testnodedown


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


def worker_scopes(result):
    """Map each worker id to the set of (scope, source) pairs it ran tests for.

    The scope is the nodeid up to the last "::", so it is the file for a plain
    function and the file plus class for a method.
    """
    scopes = {}
    for line in result.outlines:
        if "[gw" not in line or "PASSED" not in line:
            continue
        worker = line[line.index("[gw") + 1 : line.index("]")]
        nodeid = line.rsplit("PASSED ", 1)[-1].strip()
        source = nodeid[nodeid.rindex("[") + 1 : nodeid.rindex("]")].split("+")[0]
        scopes.setdefault(worker, set()).add((nodeid.rsplit("::", 1)[0], source))
    return scopes


def read_pids(directory):
    """Map each pid file written by a test back to its contents."""
    return {path.name: path.read_text() for path in directory.iterdir()}


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


class TestDistComposition:
    """An explicit --dist groups within a source instead of replacing the source."""

    def test_loadfile_keeps_a_file_whole_inside_a_source(self, pytester):
        """Six work items from three sources and two files, none of them shared.

        Chunking is what would otherwise cut a file in half here, since six workers
        over three sources is two chunks each.
        """
        for name in ("alice", "bob", "carol"):
            (pytester.path / "submissions" / name).mkdir(parents=True)
        pytester.makepyfile(
            test_alpha="def test_a(source): pass\ndef test_b(source): pass\n",
            test_beta="def test_c(source): pass\ndef test_d(source): pass\n",
        )

        result = pytester.runpytest("--sources", "submissions/*", "--dist", "loadfile", "-n", "6", "-v")

        result.assert_outcomes(passed=12)
        scopes = worker_scopes(result)
        assert len(scopes) == 6
        assert all(len(pairs) == 1 for pairs in scopes.values())
        assert {pair for pairs in scopes.values() for pair in pairs} == {
            (file, f"submissions/{name}")
            for file in ("test_alpha.py", "test_beta.py")
            for name in ("alice", "bob", "carol")
        }

    def test_loadscope_keeps_a_class_whole_inside_a_source(self, pytester):
        """The classes are interleaved so chunking alone would cut TestOne in half."""
        for name in ("alice", "bob"):
            (pytester.path / "submissions" / name).mkdir(parents=True)
        pytester.makepyfile(
            test_scoped="""
            class TestOne:
                def test_a(self, source): pass

            class TestTwo:
                def test_c(self, source): pass

            class TestOneAgain:
                def test_b(self, source): pass
            """
        )

        result = pytester.runpytest("--sources", "submissions/*", "--dist", "loadscope", "-n", "4", "-v")

        result.assert_outcomes(passed=6)
        scopes = worker_scopes(result)
        assert all(len(pairs) == 1 for pairs in scopes.values())
        assert {pair for pairs in scopes.values() for pair in pairs} == {
            (f"test_scoped.py::{klass}", f"submissions/{name}")
            for klass in ("TestOne", "TestTwo", "TestOneAgain")
            for name in ("alice", "bob")
        }

    def test_load_is_chunked_like_the_default(self, submissions):
        """--dist load names no grouping, so chunking stays the answer."""
        result = submissions.runpytest("--sources", "submissions/*", "--dist", "load", "-n", "6", "-v")

        result.assert_outcomes(passed=6)
        assignments = worker_assignments(result)
        assert len(assignments) == 6
        assert all(len(sources) == 1 for sources in assignments.values())

    def test_an_unfanned_test_still_runs_under_a_grouping_mode(self, pytester):
        """It belongs to no source, so its scope is the mode's key alone."""
        for name in ("alice", "bob"):
            (pytester.path / "submissions" / name).mkdir(parents=True)
        pytester.makepyfile(
            test_alpha="def test_a(source): pass",
            test_helper="""
            import pytest

            @pytest.mark.no_sources
            def test_helper(): pass
            """,
        )

        result = pytester.runpytest("--sources", "submissions/*", "--dist", "loadfile", "-n", "3")

        result.assert_outcomes(passed=3)


class TestLoadGroup:
    """--dist loadgroup, where only the marked tests are given a key."""

    @pytest.fixture
    def grouped(self, pytester, tmp_path, monkeypatch):
        """Two sources, two tests sharing a group and two carrying none.

        The group is interleaved with the ungrouped tests on purpose. Chunking
        slices a source in collection order, so at four workers the two marked
        tests fall either side of a chunk boundary and only the group key can
        bring them back together.
        """
        monkeypatch.setenv("PIDDIR", str(tmp_path))
        for name in ("alice", "bob"):
            (pytester.path / "submissions" / name).mkdir(parents=True)
        pytester.makepyfile(
            """
            import os, pathlib
            import pytest

            def record(source, label):
                pathlib.Path(os.environ["PIDDIR"], f"{source.name}-{label}").write_text(str(os.getpid()))

            @pytest.mark.xdist_group("db")
            def test_grouped_one(source): record(source, "grouped_one")

            def test_plain_one(source): record(source, "plain_one")

            @pytest.mark.xdist_group("db")
            def test_grouped_two(source): record(source, "grouped_two")

            def test_plain_two(source): record(source, "plain_two")
            """
        )
        return pytester

    def test_a_group_shares_a_process_within_a_source(self, grouped, tmp_path):
        result = grouped.runpytest("--sources", "submissions/*", "--dist", "loadgroup", "-n", "4")
        result.assert_outcomes(passed=8)

        pids = read_pids(tmp_path)
        for name in ("alice", "bob"):
            assert pids[f"{name}-grouped_one"] == pids[f"{name}-grouped_two"]

    def test_a_group_never_spans_two_sources(self, grouped, tmp_path):
        """The source is still a prefix of the scope, so the guarantee survives."""
        result = grouped.runpytest("--sources", "submissions/*", "--dist", "loadgroup", "-n", "4")
        result.assert_outcomes(passed=8)

        pids = read_pids(tmp_path)
        assert pids["alice-grouped_one"] != pids["bob-grouped_one"]

    def test_ungrouped_tests_are_chunked_rather_than_given_a_process_each(self, grouped, tmp_path):
        """loadgroup keys the marked tests only; taking it literally costs a process per test.

        Two sources give four work items, a group and a chunk each, not six.
        """
        result = grouped.runpytest("--sources", "submissions/*", "--dist", "loadgroup", "-n", "2")
        result.assert_outcomes(passed=8)

        pids = read_pids(tmp_path)
        for name in ("alice", "bob"):
            assert pids[f"{name}-plain_one"] == pids[f"{name}-plain_two"]
            assert pids[f"{name}-plain_one"] != pids[f"{name}-grouped_one"]
        assert len(set(pids.values())) == 4

    def test_the_summary_still_recognises_a_grouped_test(self, grouped):
        """The @group suffix xdist appends used to make source_of read them as unfanned."""
        result = grouped.runpytest("--sources", "submissions/*", "--dist", "loadgroup", "-n", "2")

        result.stdout.fnmatch_lines(["submissions/alice*4*0*0*"])


def fake_node(dsession):
    plugin_manager = types.SimpleNamespace(getplugin=lambda name: dsession)
    return types.SimpleNamespace(config=types.SimpleNamespace(pluginmanager=plugin_manager))


def fake_dsession(*, queued=True, shuttingdown=False, clone=None):
    scheduler = SourceScheduling.__new__(SourceScheduling)
    scheduler.workqueue = {"submissions/bob": {}} if queued else {}
    dsession = types.SimpleNamespace(sched=scheduler, shuttingdown=shuttingdown)
    if clone is not None:
        dsession._clone_node = clone
    return dsession


class TestWorkerReplacement:
    """Starting a fresh process for the next work item, and coping without one.

    _clone_node is private to xdist. Losing it means a worker runs more than one
    source, which is worth a warning rather than an aborted run.
    """

    def test_a_finished_node_is_replaced(self):
        cloned = []
        node = fake_node(fake_dsession(clone=cloned.append))

        pytest_testnodedown(node, None)

        assert cloned == [node]

    def test_a_missing_clone_warns_instead_of_failing(self):
        node = fake_node(fake_dsession())

        with pytest.warns(pytest.PytestWarning, match="cannot restart workers"):
            pytest_testnodedown(node, None)

    def test_a_crashed_node_is_left_to_xdist(self):
        """xdist replaces it against --max-worker-restart; cloning too gives it two."""
        cloned = []
        node = fake_node(fake_dsession(clone=cloned.append))

        pytest_testnodedown(node, RuntimeError("boom"))

        assert cloned == []

    def test_nothing_is_started_once_the_session_is_shutting_down(self):
        cloned = []
        node = fake_node(fake_dsession(clone=cloned.append, shuttingdown=True))

        pytest_testnodedown(node, None)

        assert cloned == []

    def test_nothing_is_started_with_an_empty_queue(self):
        cloned = []
        node = fake_node(fake_dsession(clone=cloned.append, queued=False))

        pytest_testnodedown(node, None)

        assert cloned == []
