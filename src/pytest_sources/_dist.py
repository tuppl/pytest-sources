from collections.abc import Callable, Generator, Iterator
from enum import StrEnum

import pytest
from xdist.scheduler import LoadFileScheduling, LoadGroupScheduling, LoadScopeScheduling

from pytest_sources._workers import _is_worker


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


# tryfirst so the mode is settled and checked before _workers reads the worker count.
@pytest.hookimpl(wrapper=True, tryfirst=True)
def pytest_cmdline_main(config: pytest.Config) -> Generator[None, object, object]:
    """
    Settle what the user asked --dist for, while the answer is still legible.

    xdist's own pytest_cmdline_main rewrites "no" to "load" as soon as a worker
    count exists, and nothing downstream can tell the two apart afterwards.
    """
    # The globs rather than the resolved sources, because resolving validates them
    # against the delimiter and _nodeid has not settled that yet.
    if not _is_worker(config) and (config.getoption("sources") or config.getini("sources")):
        mode = request_dist(config)
        config.stash[REQUESTED_DIST] = mode
        _reject_conflicts(config, mode)

        # Do not distribute.
        if mode is Dist.NO and getattr(config.option, "numprocesses", None) is None:
            config.option.numprocesses = 0
    return (yield)


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
