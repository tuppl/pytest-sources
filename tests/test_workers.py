import contextlib
import types

import pytest

from pytest_sources import _workers


def drive_cmdline_main(config):
    """Run the hook wrapper's pre-yield half without starting a session."""
    generator = _workers.pytest_cmdline_main(config)
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
    monkeypatch.setattr(_workers, "resolve", lambda config: ["a", "b", "c"])


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
    monkeypatch.setattr(_workers, "resolve", lambda config: [])
    config = fake_config()
    drive_cmdline_main(config)
    assert config.option.numprocesses is None


def test_auto_num_workers_is_the_source_count(submissions):
    config = submissions.parseconfigure("--sources", "submissions/*")
    assert _workers.pytest_xdist_auto_num_workers(config) == 3


def test_auto_num_workers_defers_to_xdist_without_sources(pytester):
    config = pytester.parseconfigure()
    assert _workers.pytest_xdist_auto_num_workers(config) is None


def test_auto_starts_one_worker_per_source(submissions):
    """Assert on workers started, not on workers that reported.

    xdist's own answer to -n auto is the CPU count. Counting the workers that
    ran tests cannot tell the two apart: with more workers than sources the
    surplus is split within each source, so every worker reports either way.
    """
    result = submissions.runpytest("--sources", "submissions/*", "-n", "auto", "-v")
    result.assert_outcomes(passed=6)
    result.stdout.fnmatch_lines(["*created: 3/3 workers*"])
