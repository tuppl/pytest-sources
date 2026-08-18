from collections.abc import Callable, Iterator
from enum import StrEnum

import execnet
import pytest
from xdist.scheduler import LoadFileScheduling, LoadGroupScheduling, LoadScopeScheduling

from pytest_sources._core.discover import is_worker


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
    """
    if not is_worker(config) and (config.getoption("sources") or config.getini("sources")):
        mode = request_dist(config)
        config.stash[REQUESTED_DIST] = mode
        _reject_conflicts(config, mode)


def _reject_conflicts(config: pytest.Config, mode: Dist | None) -> None:
    if mode in INCOMPATIBLE:
        raise pytest.UsageError(
            f"--dist {mode} cannot give each source its own process, so it does not "
            f"combine with --sources. Use loadfile, loadscope, loadgroup or no."
        )

    remote = _remote_tx(config) if config.getoption("sources_maxfail", 0) else []
    if remote:
        raise pytest.UsageError(
            f"--sources-maxfail shares a source's budget through a file on this machine, "
            f"which --tx {', '.join(remote)} cannot reach. Drop one of the two."
        )


def _remote_tx(config: pytest.Config) -> list[str]:
    """
    The --tx specs placing workers off this machine.

    Only readable before xdist's pytest_cmdline_main, which fills tx with a popen
    spec per worker.
    """
    return [spec for spec in getattr(config.option, "tx", []) or [] if not _is_local(spec)]


def _is_local(spec: str) -> bool:
    count, star, rest = spec.partition("*")
    try:
        parsed = execnet.XSpec(rest if star and count.isdigit() else spec)
    except (AttributeError, ValueError):
        # Unparseable, and xdist says so itself once it gets this far.
        return True
    return bool(parsed.popen) and not parsed.via


def request_dist(config: pytest.Config) -> Dist | None:
    """
    The mode the user asked for, or None if they did not ask.
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
