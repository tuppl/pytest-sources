import contextlib
import importlib
import os
import sys
from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from types import ModuleType

import pytest


class SourceImportError(ImportError):
    """A source does not provide the requested module."""


_active: "Source | None" = None


@dataclass(frozen=True)
class Source:
    """A single source directory that tests are run against."""

    path: Path
    id: str

    @property
    def name(self) -> str:
        return self.path.name

    def __fspath__(self) -> str:
        return str(self.path)

    def __truediv__(self, other: str) -> Path:
        return self.path / other

    def __str__(self) -> str:
        return self.id

    def chdir(self) -> contextlib.chdir:
        return contextlib.chdir(self.path)

    def activate(self) -> None:
        global _active
        if _active is self:
            return
        if _active is not None:
            _active.deactivate()
        sys.path.insert(0, str(self.path))
        importlib.invalidate_caches()
        _active = self

    def deactivate(self) -> None:
        global _active
        entry = str(self.path)
        while entry in sys.path:
            sys.path.remove(entry)
        for name, module in list(sys.modules.items()):
            file = getattr(module, "__file__", None)
            if file and Path(file).is_relative_to(self.path):
                del sys.modules[name]
        if _active is self:
            _active = None

    def import_module(self, name: str) -> ModuleType:
        __tracebackhide__ = True
        self.activate()
        try:
            return importlib.import_module(name)
        except ModuleNotFoundError as exc:
            if exc.name and (exc.name == name or name.startswith(f"{exc.name}.")):
                raise SourceImportError(f"{self.id} has no module {name!r}") from None
            raise


def make_sources(paths: Sequence[Path], root: Path) -> list[Source]:
    sources = [Source(path=path, id=_relative_id(path, root)) for path in paths]
    _validate(sources)
    return sources


def _validate(sources: Sequence[Source]) -> None:
    """Reject ids that a nodeid could not be traced back to a single source."""
    from pytest_sources._nodeid import DELIMITER

    reserved = [source.id for source in sources if DELIMITER in source.id]
    if reserved:
        raise pytest.UsageError(
            f"{DELIMITER!r} separates parameters in a test id and may not appear "
            f"in a source path: {', '.join(reserved)}"
        )

    counts = Counter(source.id for source in sources)
    duplicates = sorted(id for id, count in counts.items() if count > 1)
    if duplicates:
        raise pytest.UsageError(
            f"sources must have distinct ids, but these are shared by more than one source: {', '.join(duplicates)}"
        )


def _relative_id(path: Path, root: Path) -> str:
    if path.is_relative_to(root):
        return path.relative_to(root).as_posix()
    if path.anchor == root.anchor:
        return Path(os.path.relpath(path, root)).as_posix()
    return path.as_posix()
