import warnings
from collections.abc import Container

import pytest

DEFAULT = "+"
UNFANNED = ""
FORBIDDEN = "[]"

_delimiter = DEFAULT
_original_id: object | None = None


def delimiter() -> str:
    return _delimiter


def source_of(nodeid: str, source_ids: Container[str]) -> str:
    """
    Recover the source (directory) a test belongs to from its nodeid.
    """
    nodeid = drop_group(nodeid)
    start = nodeid.find("[", nodeid.rfind("::") + 1)
    if start == -1:
        return UNFANNED
    tokens = nodeid[start + 1 :].removesuffix("]").split(delimiter())
    return next((token for token in tokens if token in source_ids), UNFANNED)


def drop_group(nodeid: str) -> str:
    """
    Drop the "@group" xdist appends under --dist loadgroup.
    """
    at = nodeid.find("@", nodeid.rfind("]") + 1)
    return nodeid[:at] if at != -1 else nodeid


def update_delimiter(config: pytest.Config) -> None:
    global _delimiter
    chosen = config.getoption("sources_delimiter")
    if chosen is None:
        chosen = config.getini("sources_delimiter")
    _delimiter = _validate_delimiter(chosen)


def reset() -> None:
    """Restore CallSpec2.id and the default delimiter for the next in-process run."""
    global _delimiter
    _unpatch()
    _delimiter = DEFAULT


def _validate_delimiter(candidate: str) -> str:
    if len(candidate) != 1:
        raise pytest.UsageError(f"the sources delimiter must be a single character, not {candidate!r}")
    if not candidate.isascii() or not candidate.isprintable():
        raise pytest.UsageError(
            f"the sources delimiter must be printable ASCII, pytest escapes the rest out of test ids: {candidate!r}"
        )
    if candidate in FORBIDDEN:
        raise pytest.UsageError(f"{candidate!r} delimits the parameters of a test id and cannot also separate them")
    return candidate


def _patch() -> None:
    """
    Join parameter ids with the delimiter instead of pytest's default "-".

    A source id is a path and "-" is legal in a directory name, so the "-" that
    pytest puts between parameters is indistinguishable from one that was
    already part of the source id.
    """
    global _original_id
    if _original_id is not None:
        return

    call_spec = _call_spec_class()
    if call_spec is None:
        return

    _original_id = call_spec.id  # type: ignore[attr-defined]
    call_spec.id = property(lambda self: delimiter().join(self._idlist))  # type: ignore[attr-defined]


def _unpatch() -> None:
    global _original_id
    if _original_id is None:
        return

    call_spec = _call_spec_class()
    if call_spec is not None:
        call_spec.id = _original_id  # type: ignore[attr-defined]
    _original_id = None


def _call_spec_class() -> type | None:
    """
    Locate pytest's private CallSpec2, warning rather than failing if it moved.
    """
    try:
        from _pytest.python import CallSpec2
    except ImportError:  # pragma: no cover - depends on the pytest version
        CallSpec2 = None  # type: ignore[assignment, misc]

    if CallSpec2 is None or not isinstance(getattr(CallSpec2, "id", None), property):
        warnings.warn(
            f"pytest-sources could not set the parameter id delimiter to "
            f"{delimiter()!r}. Sources whose name contains '{delimiter()!r}' may be assigned to "
            f"the wrong worker.",
            pytest.PytestWarning,
            stacklevel=2,
        )
        return None
    return CallSpec2
