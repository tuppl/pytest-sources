import types

import pytest

from pytest_sources import _xdist
from pytest_sources._core.schedule import SourceScheduling
from pytest_sources._xdist import pytest_testnodedown


class TestAutoWorkerCount:
    """Answering -n auto with the number of sources, bounded by the CPU count."""

    def test_auto_num_workers_is_the_source_count(self, submissions, monkeypatch):
        monkeypatch.setattr(_xdist.os, "cpu_count", lambda: 8)
        config = submissions.parseconfigure("--sources", "submissions/*")
        assert _xdist.pytest_xdist_auto_num_workers(config) == 3

    def test_auto_num_workers_defers_to_xdist_without_sources(self, pytester):
        config = pytester.parseconfigure()
        assert _xdist.pytest_xdist_auto_num_workers(config) is None

    def test_auto_num_workers_is_capped_at_the_cpu_count(self, submissions, monkeypatch):
        """A hundred submissions must not mean a hundred interpreters at once."""
        monkeypatch.setattr(_xdist.os, "cpu_count", lambda: 2)
        config = submissions.parseconfigure("--sources", "submissions/*")
        assert _xdist.pytest_xdist_auto_num_workers(config) == 2

    def test_an_unknown_cpu_count_still_starts_a_worker(self, submissions, monkeypatch):
        """os.cpu_count() is documented to return None when it cannot tell."""
        monkeypatch.setattr(_xdist.os, "cpu_count", lambda: None)
        config = submissions.parseconfigure("--sources", "submissions/*")
        assert _xdist.pytest_xdist_auto_num_workers(config) == 1

    def test_the_cap_costs_no_isolation(self, pytester, tmp_path, monkeypatch):
        """Fewer workers than sources still gives each source its own process,
        because a worker is replaced rather than reused between them."""
        monkeypatch.setenv("PIDDIR", str(tmp_path))
        for name in ("alice", "bob", "carol", "dave"):
            (pytester.path / "submissions" / name).mkdir(parents=True)
        pytester.makepyfile(
            """
            import os, pathlib

            def test_pid(source):
                pathlib.Path(os.environ["PIDDIR"], source.name).write_text(str(os.getpid()))
            """
        )

        result = pytester.runpytest("--sources", "submissions/*", "-n", "2")

        result.assert_outcomes(passed=4)
        assert len({path.read_text() for path in tmp_path.iterdir()}) == 4

    def test_auto_starts_one_worker_per_source(self, submissions):
        """Assert on workers started, not on workers that reported.

        xdist's own answer to -n auto is the CPU count. Counting the workers that
        ran tests cannot tell the two apart: with more workers than sources the
        surplus is split within each source, so every worker reports either way.
        """
        result = submissions.runpytest("--sources", "submissions/*", "-n", "auto", "-v")
        result.assert_outcomes(passed=6)
        result.stdout.fnmatch_lines(["*created: 3/3 workers*"])


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
