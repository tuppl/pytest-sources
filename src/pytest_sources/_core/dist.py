import os
from collections.abc import Callable, Iterator
from enum import StrEnum

import pytest
from xdist.scheduler import LoadFileScheduling, LoadGroupScheduling, LoadScopeScheduling


class Dist(StrEnum):
    EACH = "each"
    LOAD = "load"
    LOADSCOPE = "loadscope"
    LOADFILE = "loadfile"
    LOADGROUP = "loadgroup"
    WORKSTEAL = "worksteal"
    NO = "no"


WITHIN: dict[Dist, Callable[[object, str], str]] = {
    Dist.LOADSCOPE: LoadScopeScheduling._split_scope,
    Dist.LOADFILE: LoadFileScheduling._split_scope,
    Dist.LOADGROUP: LoadGroupScheduling._split_scope,
}

INCOMPATIBLE = (Dist.EACH, Dist.WORKSTEAL)

REQUESTED_DIST = pytest.StashKey[Dist | None]()


def settle(config: pytest.Config) -> None:
    """
    Settle what the user asked --dist for, while the answer is still legible.

    xdist's own pytest_cmdline_main rewrites "no" to "load" as soon as a worker
    count exists, and nothing downstream can tell the two apart afterwards.
    """
    # The globs rather than the resolved sources: a --dist conflict should be
    # reported even when the globs are bad, and resolving changes nothing here.
    if not _is_worker(config) and (config.getoption("sources") or config.getini("sources")):
        mode = request_dist(config)
        config.stash[REQUESTED_DIST] = mode
        _reject_conflicts(config, mode)


def _reject_conflicts(config: pytest.Config, mode: Dist | None) -> None:
    if mode in INCOMPATIBLE:
        raise pytest.UsageError(
            f"--dist {mode} cannot give each source its own process, so it does not "
            f"combine with --sources. Use loadfile, loadscope, loadgroup or no."
        )

    if mode in WITHIN and config.getoption("sources_maxfail", 0):
        raise pytest.UsageError(
            f"--sources-maxfail counts failures per source, which --dist {mode} splits "
            f"across processes. Drop one of the two."
        )


def request_dist(config: pytest.Config) -> Dist | None:
    """
    The mode the user asked for, or None if they did not ask.

    Only readable before xdist's pytest_cmdline_main, which rewrites "no" to "load"
    as soon as a worker count is set.
    """
    if getattr(config.option, "distload", False):
        return Dist.LOAD

    mode = getattr(config.option, "dist", Dist.NO)
    if mode != Dist.NO:
        return Dist(mode)

    if any(argument == "--dist" or argument.startswith("--dist=") for argument in _given(config)):
        return Dist.NO
    return None


def _given(config: pytest.Config) -> Iterator[str]:
    yield from config.invocation_params.args
    yield from config.getini("addopts")


def _is_worker(config: pytest.Config) -> bool:
    """
    Whether this process is running tests on behalf of a controller.

    Not xdist.is_xdist_worker, which takes a request or session and only looks at
    config.workerinput. PYTEST_XDIST_WORKER is exported before a worker builds its
    config and is inherited by anything it starts, so this holds at any depth.
    """
    return "PYTEST_XDIST_WORKER" in os.environ or hasattr(config, "workerinput")
