import types

import pytest

from pytest_sources._core import dist
from pytest_sources._core.dist import Dist, request_dist


class TestRequestedDist:
    """Recovering what the user asked --dist for, before xdist rewrites it."""

    def test_nothing_asked_for_reads_as_unset(self, pytester):
        assert request_dist(pytester.parseconfig()) is None

    @pytest.mark.parametrize("spelling", [("--dist", "no"), ("--dist=no",)])
    def test_an_explicit_no_is_not_the_default(self, pytester, spelling):
        """xdist defaults dist to "no", so option alone cannot tell these apart.

        Both spellings matter: only the argument scan can see an explicit "no",
        and it has to match the separated and joined forms separately.
        """
        assert request_dist(pytester.parseconfig(*spelling)) is Dist.NO

    @pytest.mark.parametrize("mode", ["loadfile", "loadscope", "loadgroup", "each", "worksteal"])
    def test_a_named_mode_is_returned(self, pytester, mode):
        assert request_dist(pytester.parseconfig(f"--dist={mode}")) is Dist(mode)

    def test_the_load_shortcut_is_recognised(self, pytester):
        assert request_dist(pytester.parseconfig("-d")) is Dist.LOAD

    def test_a_mode_set_in_addopts_is_seen(self, pytester):
        """addopts never reaches invocation_params, which holds the command line."""
        pytester.makeini(
            """
            [pytest]
            addopts = --dist no
            """
        )
        assert request_dist(pytester.parseconfig()) is Dist.NO

    def test_a_missing_dist_option_reads_as_unset(self, pytester):
        """--dist does not exist when xdist is disabled with -p no:xdist."""
        assert request_dist(pytester.parseconfig("-p", "no:xdist")) is None


def fake_config(**attributes):
    config = types.SimpleNamespace(option=types.SimpleNamespace(numprocesses=None))
    config.__dict__.update(attributes)
    return config


@pytest.fixture
def three_sources(monkeypatch):
    monkeypatch.delenv("PYTEST_XDIST_WORKER", raising=False)
    monkeypatch.setattr(dist, "resolve", lambda config: ["a", "b", "c"])


class TestImpliedWorkerCount:
    """Deciding whether to distribute, and refusing to inside a worker."""

    def test_sources_imply_one_worker_each(self, three_sources):
        config = fake_config()
        dist.imply_worker_count(config)
        assert config.option.numprocesses == "auto"

    @pytest.mark.parametrize("requested", [0, 2])
    def test_an_explicit_worker_count_is_left_alone(self, three_sources, requested):
        config = fake_config()
        config.option.numprocesses = requested
        dist.imply_worker_count(config)
        assert config.option.numprocesses == requested

    def test_no_workers_are_forced_without_sources(self, monkeypatch):
        monkeypatch.setattr(dist, "resolve", lambda config: [])
        config = fake_config()
        dist.imply_worker_count(config)
        assert config.option.numprocesses is None

    def test_a_missing_numprocesses_option_is_not_an_error(self, three_sources):
        """The option does not exist when xdist is disabled with -p no:xdist.

        Reading it must not raise; what is then written is inert, because
        without xdist nothing reads it back.
        """
        config = fake_config()
        del config.option.numprocesses

        dist.imply_worker_count(config)

    def test_a_worker_never_starts_workers_of_its_own(self, three_sources):
        """An xdist worker re-enters this code with numprocesses reset to None.

        Treating that as "unset" made every worker spawn a full set of its own,
        which multiplies until the machine runs out of memory.
        """
        config = fake_config(workerinput={"workerid": "gw0"})
        dist.imply_worker_count(config)
        assert config.option.numprocesses is None

    def test_a_descendant_of_a_worker_never_starts_workers_either(self, three_sources, monkeypatch):
        """PYTEST_XDIST_WORKER is inherited, so the guard holds at any depth.

        config.workerinput marks only the worker itself; a process it starts would
        not carry it.
        """
        monkeypatch.setenv("PYTEST_XDIST_WORKER", "gw0")
        config = fake_config()
        dist.imply_worker_count(config)
        assert config.option.numprocesses is None
