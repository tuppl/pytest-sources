import sys

import pytest

from pytest_sources._core import source as source_module


@pytest.fixture(autouse=True)
def isolate_imports():
    original_path = list(sys.path)
    original_modules = set(sys.modules)
    yield
    source_module._active = None
    sys.path[:] = original_path
    for name in set(sys.modules) - original_modules:
        del sys.modules[name]


@pytest.fixture
def submissions(pytester):
    for name, value in (("alice", 1), ("bob", 2)):
        directory = pytester.path / "submissions" / name
        directory.mkdir(parents=True)
        (directory / "solution.py").write_text(f"VALUE = {value}\n")
    return pytester


class TestDeactivationAtSessionEnd:
    """Taking the last active source off sys.path when the run ends."""

    def test_the_run_leaves_sys_path_as_it_found_it(self, submissions):
        """pytester runs in-process, so a source left active would follow us out."""
        before = list(sys.path)

        submissions.makepyfile("def test_x(): pass")
        submissions.runpytest("--sources", "submissions/*", "-n", "0").assert_outcomes(passed=2)

        assert sys.path == before
