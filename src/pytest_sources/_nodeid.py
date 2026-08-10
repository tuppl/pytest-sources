import warnings
from collections.abc import Container

import pytest

DELIMITER = "+"
UNFANNED = ""

_original_id: object | None = None


def source_of(nodeid: str, source_ids: Container[str]) -> str:
    """
    Recover the source (directory) a test belongs to from its nodeid.

    The source is always the first part of the nodeid up until the DELIMITER.
    """
    start = nodeid.find("[", nodeid.rfind("::") + 1)
    if start == -1:
        return UNFANNED
    candidate = nodeid[start + 1 :].removesuffix("]").split(DELIMITER)[0]
    return candidate if candidate in source_ids else UNFANNED


@pytest.hookimpl
def pytest_configure(config: pytest.Config) -> None:
    if config.getoption("sources") or config.getini("sources"):
        _patch()


@pytest.hookimpl
def pytest_unconfigure(config: pytest.Config) -> None:
    _unpatch()


def _patch() -> None:
    """
    Join parameter ids with DELIMITER instead of "-".

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

    _original_id = call_spec.id
    call_spec.id = property(lambda self: DELIMITER.join(self._idlist))


def _unpatch() -> None:
    global _original_id
    if _original_id is None:
        return

    call_spec = _call_spec_class()
    if call_spec is not None:
        call_spec.id = _original_id
    _original_id = None


def _call_spec_class() -> type | None:
    """
    Locate pytest's private CallSpec2, warning rather than failing if it moved.
    """
    try:
        from _pytest.python import CallSpec2
    except ImportError:  # pragma: no cover - depends on the pytest version
        CallSpec2 = None

    if CallSpec2 is None or not isinstance(getattr(CallSpec2, "id", None), property):
        warnings.warn(
            f"pytest-sources could not set the parameter id delimiter to "
            f"{DELIMITER!r}. Sources whose name contains '-' may be assigned to "
            f"the wrong worker.",
            pytest.PytestWarning,
            stacklevel=2,
        )
        return None
    return CallSpec2
