import math
import warnings
from collections.abc import Sequence

import pytest
from xdist.remote import Producer
from xdist.scheduler.loadscope import LoadScopeScheduling
from xdist.workermanage import WorkerController

from pytest_sources._core.discover import SOURCES
from pytest_sources._core.dist import REQUESTED_DIST, WITHIN, Dist
from pytest_sources._core.nodeid import delimiter, source_of


class SourceScheduling(LoadScopeScheduling):
    """
    Scheduler allocates each worker a work item. A work item may contain an entire
    or subset of a testing suite for a source. Each work item is run in its own
    process, therefore when a work item is exhausted the worker will spin up a new
    process.
    """

    def __init__(self, config: pytest.Config, log: Producer | None = None) -> None:
        super().__init__(config, log)
        self.log = Producer("sourcesched") if log is None else log.sourcesched
        self._source_ids = {source.id for source in config.stash[SOURCES]}
        self._scopes: dict[str, str] | None = None
        self._served: set[WorkerController] = set()

        mode = config.stash.get(REQUESTED_DIST, None)
        within = WITHIN.get(mode) if mode is not None else None
        self._within = within.__get__(self) if within is not None else None
        self._chunks_wanted = self._within is None or mode is Dist.LOADGROUP

    def schedule(self) -> None:
        if self._scopes is None and self._chunks_wanted and self.collection_is_completed:
            self._scopes = self._chunk(next(iter(self.registered_collections.values())))
        super().schedule()

    def _split_scope(self, nodeid: str) -> str:
        if self._within is not None:
            within = self._within(nodeid)
            if within != nodeid:
                return f"{source_of(nodeid, self._source_ids)}{delimiter()}{within}"

        if self._scopes is not None and nodeid in self._scopes:
            return self._scopes[nodeid]
        return source_of(nodeid, self._source_ids)

    def _assign_work_unit(self, node: WorkerController) -> None:
        self._served.add(node)
        super()._assign_work_unit(node)

        # Shut down immediately so the worker's queue holds its tests followed by
        # the stop marker. A worker reads the next index before running the test
        # it already has, so one that is never sent more work would block on the
        # last of it forever.
        node.shutdown()

    def _reschedule(self, node: WorkerController) -> None:
        """
        Give a node one work item, and nothing after it.

        A second item would mean a second source in the same process, so a node
        that has had its turn is left to exit. pytest_testnodedown starts a
        replacement, which arrives here as a node that has not been served.
        """
        if node.shutting_down or node in self._served:
            return

        if not self.workqueue:
            node.shutdown()
            return

        # A replacement whose collection was rejected has nothing to index into.
        if node in self.registered_collections:
            self._assign_work_unit(node)

    def _chunk(self, collection: Sequence[str]) -> dict[str, str]:
        """
        Map each test to a work item, splitting a source's tests when workers spare.

        A chunk is a work item of its own, so a split source occupies one process per
        chunk. That is safe because every one of them activates that source alone.
        """
        sources: dict[str, list[str]] = {}
        for nodeid in collection:
            sources.setdefault(source_of(nodeid, self._source_ids), []).append(nodeid)

        # Each chunk is counted separately by --sources-maxfail, so splitting
        # would turn a budget per source into a budget per chunk.
        splittable = not self.config.getoption("sources_maxfail")

        scopes: dict[str, str] = {}
        for source_id, nodeids in sources.items():
            chunks = min(max(1, self.numnodes // len(sources)), len(nodeids)) if splittable else 1
            size = math.ceil(len(nodeids) / chunks)
            for position, nodeid in enumerate(nodeids):
                scopes[nodeid] = f"{source_id}{delimiter()}{position // size}"
        return scopes


def start_replacement(node: WorkerController, error: object | None) -> None:
    """
    Start a fresh process for the next work item.

    Fires before the scheduler is told the node has gone, so the replacement joins
    the run before the old node leaves it and xdist never sees zero active nodes.
    """
    if error is not None:
        return

    dsession = node.config.pluginmanager.getplugin("dsession")
    scheduler = getattr(dsession, "sched", None)
    if not isinstance(scheduler, SourceScheduling):
        return

    if dsession.shuttingdown or not scheduler.workqueue:
        return

    clone = getattr(dsession, "_clone_node", None)
    if clone is None:
        warnings.warn(
            "pytest-sources cannot restart workers, so a worker may run more than "
            "one source and what one leaves behind can reach the next.",
            pytest.PytestWarning,
            stacklevel=2,
        )
        return
    clone(node)
