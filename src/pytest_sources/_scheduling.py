from collections.abc import Container, Sequence

import pytest
from xdist.remote import Producer
from xdist.report import report_collection_diff
from xdist.workermanage import WorkerController, parse_tx_spec_config

from pytest_sources._nodeid import DELIMITER
from pytest_sources._option import resolve
from pytest_sources._stash import SOURCES

UNFANNED = ""


def source_of(nodeid: str, source_ids: Container[str]) -> str:
    """
    Recover the source a test belongs to from its nodeid.

    The source is always the first part of the nodeid up until the DELIMITER.
    """
    start = nodeid.find("[", nodeid.rfind("::") + 1)
    if start == -1:
        return UNFANNED
    candidate = nodeid[start + 1 :].removesuffix("]").split(DELIMITER)[0]
    return candidate if candidate in source_ids else UNFANNED


class SourceScheduling:
    """
    Assign every test of a source to a single worker.

    Each source is pinned to one worker so that its sys.path entry and imported
    modules never have to be swapped out mid-run. When there are fewer workers
    than sources a worker takes several sources, one after another.
    """

    def __init__(self, config: pytest.Config, log: Producer | None = None) -> None:
        self.config = config
        self.numnodes = len(parse_tx_spec_config(config))
        self.node2collection: dict[WorkerController, list[str]] = {}
        self.node2pending: dict[WorkerController, list[int]] = {}
        self.collection: list[str] | None = None
        self.log = Producer("sourcesched") if log is None else log.sourcesched
        self._source_ids = {source.id for source in config.stash[SOURCES]}
        self._started: list[WorkerController] = []

    @property
    def nodes(self) -> list[WorkerController]:
        return list(self.node2pending)

    @property
    def collection_is_completed(self) -> bool:
        return len(self.node2collection) >= self.numnodes

    @property
    def tests_finished(self) -> bool:
        if not self.collection_is_completed:
            return False
        return not self.has_pending

    @property
    def has_pending(self) -> bool:
        return any(self.node2pending.values())

    def add_node(self, node: WorkerController) -> None:
        assert node not in self.node2pending
        self.node2pending[node] = []

    def add_node_collection(self, node: WorkerController, collection: Sequence[str]) -> None:
        assert node in self.node2pending
        self.node2collection[node] = list(collection)

    def mark_test_complete(self, node: WorkerController, item_index: int, duration: float = 0) -> None:
        self.node2pending[node].remove(item_index)

    def mark_test_pending(self, item: str) -> None:
        raise NotImplementedError()

    def remove_pending_tests_from_node(self, node: WorkerController, indices: Sequence[int]) -> None:
        raise NotImplementedError()

    def remove_node(self, node: WorkerController) -> str | None:
        pending = self.node2pending.pop(node)
        if not pending:
            return None
        assert self.collection is not None
        return self.collection[pending.pop(0)]

    def schedule(self) -> None:
        assert self.collection_is_completed

        if self.collection is None:
            if not self._check_nodes_have_same_collection():
                self.log("**Different tests collected, aborting run**")
                return
            self.collection = next(iter(self.node2collection.values()))
            self._assign()

        for node, pending in self.node2pending.items():
            if node in self._started:
                continue
            self._started.append(node)
            if pending:
                node.send_runtest_some(pending)
            # The partition is static, so a node gets no further work. Shutting
            # down now lets it exit once its queue drains.
            node.shutdown()

    def _assign(self) -> None:
        assert self.collection is not None
        groups: dict[str, list[int]] = {}
        for index, nodeid in enumerate(self.collection):
            groups.setdefault(self._source_of(nodeid), []).append(index)

        nodes = self.nodes
        for position, source_id in enumerate(sorted(groups)):
            node = nodes[position % len(nodes)]
            self.node2pending[node].extend(groups[source_id])

    def _source_of(self, nodeid: str) -> str:
        return source_of(nodeid, self._source_ids)

    def _check_nodes_have_same_collection(self) -> bool:
        node_collections = list(self.node2collection.items())
        first_node, reference = node_collections[0]
        same_collection = True
        for node, collection in node_collections[1:]:
            if collection != reference:
                self.log(report_collection_diff(reference, collection, first_node.gateway.id, node.gateway.id))
                same_collection = False
        return same_collection


@pytest.hookimpl
def pytest_xdist_make_scheduler(config: pytest.Config, log: Producer) -> SourceScheduling | None:
    if not resolve(config):
        return None
    return SourceScheduling(config, log)


@pytest.hookimpl(tryfirst=True)
def pytest_xdist_auto_num_workers(config: pytest.Config) -> int | None:
    """
    One worker per source. tryfirst so this beats xdist's CPU-count default.
    """
    sources = resolve(config)
    return len(sources) if sources else None
